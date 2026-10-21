"""Casos de uso de subscription-service (anillo medio).

Dependen del puerto `PaymentGateway`, nunca de una pasarela concreta (RULES.md,
regla 6): la elige `PaymentGatewayFactory` y la inyecta `api/context.py`.
"""
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from domain.exceptions import (
    NoActiveSubscriptionError,
    PaymentInProgressError,
    PaymentNotFoundError,
    PlanNotPurchasableError,
    SubscriptionAlreadyActiveError,
)
from domain.interfaces import PaymentOutcome, PaymentRequest
from domain.subscription import Entitlement, Payment, Subscription
from domain.value_objects import (
    CURRENT_STATUSES,
    GRANTING_STATUSES,
    PaymentStatus,
    PlanCode,
    SubscriptionStatus,
)
from models import PaymentRecord, SubscriptionRecord

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


@contextmanager
def atomic(session):
    """Confirma al salir; revierte ante cualquier excepcion (igual que finance)."""
    try:
        yield
        session.commit()
    except BaseException:
        session.rollback()
        raise


def _subscription(record):
    return Subscription(
        plan=PlanCode(record.plan),
        status=SubscriptionStatus(record.status),
        current_period_start=record.current_period_start,
        current_period_end=record.current_period_end,
        canceled_at=record.canceled_at,
    )


def _store_subscription(record, subscription):
    record.status = subscription.status.value
    record.current_period_start = subscription.current_period_start
    record.current_period_end = subscription.current_period_end
    record.canceled_at = subscription.canceled_at


def _payment(record):
    return Payment(record.amount_in_cents, record.currency, record.reference, PaymentStatus(record.status))


@dataclass(frozen=True)
class SubscriptionView:
    """La suscripcion de un usuario a una hora dada, lista para responder."""

    plan: object               # SubscriptionPlan vigente (FREE si no hay derecho)
    status: object             # estado efectivo, o None sin suscripcion
    record: object             # SubscriptionRecord o None
    last_payment: object       # PaymentRecord o None
    entitlement: Entitlement


@dataclass(frozen=True)
class CheckoutResult:
    subscription: SubscriptionRecord
    payment: PaymentRecord
    view: SubscriptionView


class SubscriptionService:
    def __init__(self, session, gateway, plans, clock=utcnow):
        self._session = session
        self._gateway = gateway
        self._plans = plans
        self._clock = clock

    # --- Lectura ----------------------------------------------------------------

    def plans(self):
        return tuple(self._plans.values())

    def current(self, user_id):
        now = self._clock()
        record = self._current_record(user_id)
        subscription = _subscription(record) if record else None
        entitlement = Entitlement.of(subscription, now)
        plan = self._plans[PlanCode.PREMIUM if entitlement.premium else PlanCode.FREE]
        return SubscriptionView(
            plan=plan,
            status=subscription.effective_status(now) if subscription else None,
            record=record,
            last_payment=self._last_payment(record.id) if record else None,
            entitlement=entitlement,
        )

    def entitlement(self, user_id):
        """`{premium, until}` para el gating de INV-06 en los demas servicios."""
        record = self._current_record(user_id)
        return Entitlement.of(_subscription(record) if record else None, self._clock())

    # --- Checkout ---------------------------------------------------------------

    def checkout(self, user_id, plan_code):
        """Crea (o reutiliza) la suscripcion pendiente, registra el pago y llama al gateway."""
        plan = self._plans[PlanCode(plan_code)]
        if not plan.is_paid:
            raise PlanNotPurchasableError()

        with atomic(self._session):
            self._expire_finished(user_id)
            record = self._current_record(user_id, lock=True)
            if record is not None:
                if SubscriptionStatus(record.status) in GRANTING_STATUSES:
                    raise SubscriptionAlreadyActiveError()
                last = self._last_payment(record.id)
                if last is not None and PaymentStatus(last.status) is PaymentStatus.PENDING:
                    raise PaymentInProgressError()
            else:
                record = SubscriptionRecord(
                    user_id=user_id, plan=plan.code.value, status=SubscriptionStatus.PENDING_PAYMENT.value
                )
                self._session.add(record)
                try:
                    self._session.flush()
                except IntegrityError as exc:
                    # Otro checkout simultaneo gano el lugar unico del usuario.
                    raise SubscriptionAlreadyActiveError() from exc
            payment = PaymentRecord(
                subscription_id=record.id,
                user_id=user_id,
                amount_in_cents=plan.price_in_cents,
                currency=plan.currency,
                reference=f"finty-{uuid4().hex}",
                gateway=self._gateway.name,
                status=PaymentStatus.PENDING.value,
            )
            self._session.add(payment)

        # El pago queda registrado como PENDING antes de llamar al gateway: si el
        # proceso muere en la llamada, el registro existe para conciliarlo.
        outcome = self._submit(PaymentRequest(payment.reference, payment.amount_in_cents, payment.currency, user_id))
        self.confirm_payment(payment.id, outcome)
        return CheckoutResult(record, payment, self.current(user_id))

    def _submit(self, request):
        try:
            return self._gateway.submit(request)
        except Exception as exc:  # noqa: BLE001 — un gateway que falla deja el pago en ERROR
            logger.warning("la pasarela fallo con %s: %s", type(exc).__name__, exc)
            return PaymentOutcome(PaymentStatus.ERROR, f"{type(exc).__name__}: {exc}")

    def confirm_payment(self, payment_id, outcome):
        """Aplica el resultado de un pago. Idempotente (INV-05).

        Un pago ya resuelto no cambia, y una suscripcion ya activa no extiende su
        periodo: confirmar dos veces el mismo pago aprobado no regala otro mes.
        """
        now = self._clock()
        with atomic(self._session):
            payment_record = self._session.get(PaymentRecord, payment_id, with_for_update=True)
            if payment_record is None:
                raise PaymentNotFoundError()
            payment = _payment(payment_record)
            if not payment.resolve(outcome.status):
                return payment_record
            payment_record.status = payment.status.value
            payment_record.resolved_at = now
            if payment.is_approved:
                record = self._session.get(SubscriptionRecord, payment_record.subscription_id, with_for_update=True)
                subscription = _subscription(record)
                plan = self._plans[subscription.plan]
                if subscription.activate(payment, now, plan.period_months):
                    _store_subscription(record, subscription)
            else:
                logger.info("pago %s resuelto como %s: %s", payment.reference, payment.status.value, outcome.detail)
        return payment_record

    # --- Cancelacion ------------------------------------------------------------

    def cancel(self, user_id):
        """ACTIVE → CANCELED. El acceso sigue hasta el fin del periodo. Idempotente."""
        now = self._clock()
        with atomic(self._session):
            record = self._current_record(user_id, lock=True)
            subscription = _subscription(record) if record else None
            if subscription is None or not subscription.grants_premium(now):
                raise NoActiveSubscriptionError()
            if subscription.cancel(now):
                _store_subscription(record, subscription)
        return self.current(user_id)

    # --- Apoyo ------------------------------------------------------------------

    def _current_record(self, user_id, lock=False):
        query = select(SubscriptionRecord).where(
            SubscriptionRecord.user_id == user_id,
            SubscriptionRecord.status.in_([s.value for s in CURRENT_STATUSES]),
        )
        if lock:
            query = query.with_for_update()
        return self._session.scalars(query).one_or_none()

    def _last_payment(self, subscription_id):
        return self._session.scalars(
            select(PaymentRecord)
            .where(PaymentRecord.subscription_id == subscription_id)
            .order_by(PaymentRecord.created_at.desc())
            .limit(1)
        ).one_or_none()

    def _expire_finished(self, user_id):
        """Persiste EXPIRED en las suscripciones cuyo periodo termino.

        Al leer, EXPIRED se deriva sin escribir; aqui se persiste para liberar el
        lugar unico del usuario antes de un checkout nuevo (renovacion, D-26).
        """
        self._session.execute(
            update(SubscriptionRecord)
            .where(
                SubscriptionRecord.user_id == user_id,
                SubscriptionRecord.status.in_([s.value for s in GRANTING_STATUSES]),
                SubscriptionRecord.current_period_end <= self._clock(),
            )
            .values(status=SubscriptionStatus.EXPIRED.value)
        )
