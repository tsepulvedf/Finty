"""`Subscription` y `Payment`: entidades con su maquina de estados (§6.7).

    Subscription: PENDING_PAYMENT → ACTIVE → CANCELED → EXPIRED
    Payment:      PENDING → APPROVED | DECLINED | ERROR

**INV-05:** la suscripcion solo pasa a ACTIVE cuando su `Payment` esta APPROVED.
**Idempotencia:** un pago ya resuelto no cambia; confirmarlo otra vez no extiende
el periodo.

El periodo es de un mes calendario, sin renovacion automatica (D-26). EXPIRED se
deriva al leer cuando termina el periodo, y se persiste antes de un checkout
nuevo, para liberar el lugar unico del usuario.
"""
import calendar
from dataclasses import dataclass
from datetime import datetime

from domain.exceptions import InvalidTransitionError
from domain.value_objects import (
    FINAL_PAYMENT_STATUSES,
    GRANTING_STATUSES,
    PaymentStatus,
    PlanCode,
    SubscriptionStatus,
)


def add_months(moment, months):
    """El mismo dia `months` meses despues; el 31 cae en el ultimo dia del mes."""
    month_index = moment.month - 1 + months
    year, month = moment.year + month_index // 12, month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


@dataclass
class Payment:
    amount_in_cents: int
    currency: str
    reference: str
    status: PaymentStatus = PaymentStatus.PENDING

    def resolve(self, outcome):
        """Aplica el resultado del gateway. Devuelve `False` si ya estaba resuelto."""
        outcome = PaymentStatus(outcome)
        if outcome is PaymentStatus.PENDING:
            return False
        if self.status in FINAL_PAYMENT_STATUSES:
            return False
        self.status = outcome
        return True

    @property
    def is_approved(self):
        return self.status is PaymentStatus.APPROVED


@dataclass
class Subscription:
    plan: PlanCode
    status: SubscriptionStatus = SubscriptionStatus.PENDING_PAYMENT
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    canceled_at: datetime | None = None

    def activate(self, payment, now, period_months):
        """INV-05: solo con el pago aprobado, y solo desde PENDING_PAYMENT."""
        if not payment.is_approved:
            raise InvalidTransitionError("La suscripción solo se activa con un pago aprobado (INV-05).")
        if self.status is not SubscriptionStatus.PENDING_PAYMENT:
            return False  # ya activada: no se extiende el periodo dos veces
        self.status = SubscriptionStatus.ACTIVE
        self.current_period_start = now
        self.current_period_end = add_months(now, period_months)
        return True

    def cancel(self, now):
        """ACTIVE → CANCELED; el acceso sigue hasta el fin del periodo."""
        status = self.effective_status(now)
        if status is SubscriptionStatus.CANCELED:
            return False
        if status is not SubscriptionStatus.ACTIVE:
            raise InvalidTransitionError()
        self.status = SubscriptionStatus.CANCELED
        self.canceled_at = now
        return True

    def effective_status(self, now):
        """El estado a `now`: ACTIVE o CANCELED con el periodo vencido son EXPIRED."""
        if self.status in GRANTING_STATUSES and self.current_period_end and now >= self.current_period_end:
            return SubscriptionStatus.EXPIRED
        return self.status

    def grants_premium(self, now):
        return self.effective_status(now) in GRANTING_STATUSES


@dataclass(frozen=True)
class Entitlement:
    """Derecho premium de un usuario: lo que consultan los servicios que hacen gating."""

    premium: bool
    until: datetime | None

    @classmethod
    def of(cls, subscription, now):
        if subscription is not None and subscription.grants_premium(now):
            return cls(True, subscription.current_period_end)
        return cls(False, None)
