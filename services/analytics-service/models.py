"""Persistencia de `analytics-service` (anillo externo), en `finty_analytics`.

Modelos anemicos (RULES.md, regla 2): columnas, constraints y `__repr__`.

Es un **modelo de lectura** alimentado solo por los eventos de finance-service
(ADR-15). Nunca consulta `finty_finance` (ADR-10): todo lo que sabe de una
transaccion llego en un evento.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Numeric, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarativa de los modelos del servicio."""


class TransactionFactRecord(Base):
    """Ultimo estado conocido de una transaccion, segun sus eventos.

    `TransactionManuallyAdded` la inserta, `TransactionCategorized` le cambia la
    categoria y `TransactionDeleted` llena `deleted_at`, que la saca de todo
    calculo. La fila borrada se conserva como lapida: un evento atrasado de esa
    transaccion no la resucita. `last_event_at` descarta eventos mas viejos que
    el ultimo aplicado.
    """

    __tablename__ = "transaction_fact"
    __table_args__ = (
        CheckConstraint("transaction_type IN ('income', 'expense')", name="ck_fact_type_valid"),
        CheckConstraint("char_length(currency) = 3", name="ck_fact_currency_length"),
        Index("ix_fact_user_date", "user_id", "occurred_on"),
        Index("ix_fact_date", "occurred_on"),
    )

    transaction_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid)
    account_id: Mapped[UUID] = mapped_column(Uuid)
    # Del texto decimal del evento, nunca de un float.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    transaction_type: Mapped[str] = mapped_column(String(10))
    category_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    categorization_source: Mapped[str | None] = mapped_column(String(10), nullable=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    occurred_on: Mapped[date] = mapped_column(Date)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self):
        return f"<TransactionFactRecord {self.transaction_id}>"


class ProcessedEvent(Base):
    """Evento ya aplicado: la idempotencia del consumidor por `event_id` (ADR-15).

    Se inserta en la misma transaccion que el cambio en `transaction_fact`. Un
    evento repetido (entrega al menos una vez) choca con la clave y no se aplica.
    """

    __tablename__ = "processed_event"

    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    stream_id: Mapped[str] = mapped_column(String(64))
    # `applied`, o `ignored` si llego despues de uno mas reciente o de un borrado.
    outcome: Mapped[str] = mapped_column(String(16))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self):
        return f"<ProcessedEvent {self.event_id} {self.outcome}>"
