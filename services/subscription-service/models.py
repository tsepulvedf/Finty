"""Persistencia de `subscription-service` (anillo externo), en `finty_subscription`.

Modelos anemicos (RULES.md, regla 2). `user_id` es un UUID sin FK (ADR-10).

**Una sola suscripcion vigente por usuario** (invariante implicita de DDD
Stage 1): indice unico parcial sobre `user_id` para los estados que ocupan ese
lugar (PENDING_PAYMENT, ACTIVE y CANCELED). Dos checkouts simultaneos no pueden
crear dos: el segundo choca con el indice.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SUBSCRIPTION_STATUSES = "'PENDING_PAYMENT', 'ACTIVE', 'CANCELED', 'EXPIRED'"
CURRENT_STATUSES = "'PENDING_PAYMENT', 'ACTIVE', 'CANCELED'"
PAYMENT_STATUSES = "'PENDING', 'APPROVED', 'DECLINED', 'ERROR'"


def _utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarativa de los modelos del servicio."""


class SubscriptionRecord(Base):
    __tablename__ = "subscription"
    __table_args__ = (
        CheckConstraint(f"status IN ({SUBSCRIPTION_STATUSES})", name="ck_subscription_status"),
        CheckConstraint("plan IN ('PREMIUM')", name="ck_subscription_plan_paid"),
        CheckConstraint(
            "status = 'PENDING_PAYMENT' OR current_period_end > current_period_start",
            name="ck_subscription_period",
        ),
        Index(
            "uq_subscription_one_current_per_user",
            "user_id",
            unique=True,
            postgresql_where=text(f"status IN ({CURRENT_STATUSES})"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    plan: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self):
        return f"<SubscriptionRecord {self.id} {self.status}>"


class PaymentRecord(Base):
    __tablename__ = "payment"
    __table_args__ = (
        CheckConstraint(f"status IN ({PAYMENT_STATUSES})", name="ck_payment_status"),
        CheckConstraint("amount_in_cents > 0", name="ck_payment_amount_positive"),
        Index("ix_payment_subscription_created", "subscription_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subscription_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("subscription.id", ondelete="RESTRICT"))
    user_id: Mapped[UUID] = mapped_column(Uuid)
    amount_in_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    gateway: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self):
        return f"<PaymentRecord {self.reference} {self.status}>"
