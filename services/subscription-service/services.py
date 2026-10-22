"""Casos de uso de subscription-service (anillo medio).

Dependen de puertos, nunca de implementaciones concretas (RULES.md, regla 6):
`PaymentGateway` (la elige `PaymentGatewayFactory`), y desde E2-M7
`NotificationQueue`, `ContactDirectory`, `EmailComposer` y `EmailSender`. Los
inyecta `api/context.py`.

- `SubscriptionService`: planes, checkout, confirmacion del pago, cancelacion y,
  desde E2-M7, el vencimiento periodico (`expire_all`).
- `NotificationService` (E2-M7): la bienvenida y el aviso de vencimiento, cada
  uno una sola vez por usuario, tipo y periodo.
"""
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from domain.exceptions import (
    NoActiveSubscriptionError,
    PaymentInProgressError,
    PaymentNotFoundError,
    PlanNotPurchasableError,
    SubscriptionAlreadyActiveError,
)
from domain.interfaces import ContactNotFound, ContactUnavailable, PaymentOutcome, PaymentRequest
from domain.notifications import (
    DEFAULT_DAYS_BEFORE_EXPIRY,
    DEFAULT_WELCOME_RECOVERY_HOURS,
    NotificationKind,
    deserves_welcome,
    expiring_window,
    is_expiring,
    welcome_recovery_start,
)
from domain.subscription import Entitlement, Payment, Subscription
from domain.value_objects import (
    CURRENT_STATUSES,
    GRANTING_STATUSES,
    PaymentStatus,
    PlanCode,
    SubscriptionStatus,
)
from models import PaymentRecord, SentNotificationRecord, SubscriptionRecord

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
    def __init__(self, session, gateway, plans, clock=utcnow, notifications=None):
        self._session = session
        self._gateway = gateway
        self._plans = plans
        self._clock = clock
        self._notifications = notifications

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
        activated = False
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
                activated = subscription.activate(payment, now, plan.period_months)
                if activated:
                    _store_subscription(record, subscription)
            else:
                logger.info("pago %s resuelto como %s: %s", payment.reference, payment.status.value, outcome.detail)
        if activated:
            self._announce_activation(payment_record.subscription_id)
        return payment_record

    def _announce_activation(self, subscription_id):
        """Encola la bienvenida despues del commit (E2-M7).

        Nunca bloquea la activacion: si el broker no responde, la suscripcion ya
        esta activa y el fallo solo se registra. La tarea consulta a identity, asi
        que una caida de identity tampoco toca el checkout.
        """
        if self._notifications is None:
            return
        try:
            self._notifications.premium_activated(subscription_id)
        except Exception as exc:  # noqa: BLE001 — el correo es secundario al pago
            logger.warning("no se pudo encolar la bienvenida de %s (%s)", subscription_id, exc)

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

    # --- Vencimiento (E2-M7) ----------------------------------------------------

    def expire_all(self):
        """Persiste EXPIRED en toda suscripcion ACTIVE o CANCELED cuyo periodo
        termino (tarea periodica `expire_subscriptions`). Idempotente: una ya
        vencida no vuelve a cambiar. Devuelve cuantas vencio."""
        with atomic(self._session):
            result = self._session.execute(
                update(SubscriptionRecord)
                .where(
                    SubscriptionRecord.status.in_([s.value for s in GRANTING_STATUSES]),
                    SubscriptionRecord.current_period_end <= self._clock(),
                )
                .values(status=SubscriptionStatus.EXPIRED.value)
            )
        return result.rowcount

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


# --- Notificaciones (E2-M7) ------------------------------------------------------

# Errores que pasan solos: la tarea reintenta con espera creciente.
TRANSIENT_ERRORS = (ContactUnavailable, OperationalError, DBAPIError, ConnectionError, TimeoutError)

SENT = "sent"
ALREADY_SENT = "already_sent"
SKIPPED = "skipped"
NO_CONTACT = "no_contact"


class NotificationService:
    """Bienvenida y aviso de vencimiento, a lo sumo una vez por periodo.

    Cada aviso se registra en `sent_notification` dentro de la misma transaccion
    en que se envia: el `INSERT ... ON CONFLICT DO NOTHING` sobre la restriccion
    unica decide si ya salio. Si identity no responde, la transaccion se revierte
    (no queda registro) y la tarea reintenta despues.
    """

    def __init__(self, session, contacts, composer, sender, clock=utcnow, days_before=DEFAULT_DAYS_BEFORE_EXPIRY,
                 welcome_recovery_hours=DEFAULT_WELCOME_RECOVERY_HOURS):
        self._session = session
        self._contacts = contacts
        self._composer = composer
        self._sender = sender
        self._clock = clock
        self._days_before = days_before
        self._welcome_recovery_hours = welcome_recovery_hours

    def send_premium_welcome(self, subscription_id):
        record = self._session.get(SubscriptionRecord, subscription_id)
        if record is None or not deserves_welcome(_subscription(record), self._clock()):
            self._session.rollback()
            return SKIPPED
        return self._notify(NotificationKind.PREMIUM_WELCOME, record)

    def send_missing_welcomes(self):
        """Red de seguridad de la bienvenida (D-32).

        El camino rapido es la tarea que el checkout encola despues del commit;
        si el broker no respondio en ese momento, la bienvenida no salio. Esta
        pasada busca las suscripciones ACTIVE en periodo, activadas dentro de la
        ventana de recuperacion (24 horas por defecto), sin la bienvenida
        registrada para ese periodo, y la envia. La ventana evita enviar una
        bienvenida dias despues, por ejemplo a las suscripciones anteriores a esta
        tarea. La restriccion unica de `sent_notification` evita el duplicado si
        el camino rapido llega a la vez. Devuelve cuantas salieron.
        """
        now = self._clock()
        since = welcome_recovery_start(now, self._welcome_recovery_hours)
        welcomed = (
            select(SentNotificationRecord.id)
            .where(
                SentNotificationRecord.user_id == SubscriptionRecord.user_id,
                SentNotificationRecord.kind == NotificationKind.PREMIUM_WELCOME.value,
                SentNotificationRecord.period_end == SubscriptionRecord.current_period_end,
            )
            .exists()
        )
        records = self._session.scalars(
            select(SubscriptionRecord).where(
                SubscriptionRecord.status == SubscriptionStatus.ACTIVE.value,
                SubscriptionRecord.current_period_end > now,
                SubscriptionRecord.current_period_start >= since,
                ~welcomed,
            )
        ).all()
        self._session.rollback()
        sent = 0
        for record in records:
            if deserves_welcome(_subscription(record), now):
                sent += self._notify(NotificationKind.PREMIUM_WELCOME, record) == SENT
        return sent

    def notify_expiring(self):
        """Avisa a las suscripciones que terminan en los proximos dias. Devuelve
        cuantos avisos salieron en esta pasada."""
        now = self._clock()
        start, end = expiring_window(now, self._days_before)
        records = self._session.scalars(
            select(SubscriptionRecord).where(
                SubscriptionRecord.status.in_([s.value for s in GRANTING_STATUSES]),
                SubscriptionRecord.current_period_end > start,
                SubscriptionRecord.current_period_end <= end,
            )
        ).all()
        self._session.rollback()
        sent = 0
        for record in records:
            if is_expiring(_subscription(record), now, self._days_before):
                sent += self._notify(NotificationKind.SUBSCRIPTION_EXPIRING, record) == SENT
        return sent

    def _notify(self, kind, record):
        with atomic(self._session):
            claimed = self._session.execute(
                insert(SentNotificationRecord)
                .values(
                    id=uuid4(),
                    user_id=record.user_id,
                    subscription_id=record.id,
                    kind=kind.value,
                    period_end=record.current_period_end,
                    sent_at=self._clock(),
                )
                .on_conflict_do_nothing(constraint="uq_notification_once_per_period")
                .returning(SentNotificationRecord.id)
            ).scalar_one_or_none()
            if claimed is None:
                return ALREADY_SENT
            try:
                contact = self._contacts.contact(record.user_id)
            except ContactNotFound:
                # No hay a quien escribirle: queda registrado para no reintentar.
                logger.warning("sin contacto para %s; el aviso %s no se envia", record.user_id, kind.value)
                return NO_CONTACT
            message = self._composer.compose(kind, contact, record.current_period_end)
            self._sender.send(message)
            notification = self._session.get(SentNotificationRecord, claimed)
            notification.recipient = contact.email
            notification.language = contact.language
        logger.info("aviso %s enviado a %s", kind.value, record.user_id)
        return SENT
