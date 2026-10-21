"""Eventos de finance-service tal como los recibe analytics (anillo de Dominio).

El contrato es el de `finty.finance.events` (ARCHITECTURE.md §10.5). Aqui son
value objects inmutables; como se leen del stream es asunto de `infra/`.
"""
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from domain.exceptions import InvalidEventError
from domain.shared.value_objects import Money
from domain.value_objects import TransactionType

SUPPORTED_VERSION = 1


class EventType(StrEnum):
    TRANSACTION_MANUALLY_ADDED = "TransactionManuallyAdded"
    TRANSACTION_CATEGORIZED = "TransactionCategorized"
    TRANSACTION_DELETED = "TransactionDeleted"


@dataclass(frozen=True)
class TransactionSnapshot:
    """Foto de la transaccion que trae cada evento."""

    user_id: UUID
    transaction_id: UUID
    account_id: UUID
    amount: Money
    transaction_type: TransactionType
    category_name: str | None
    categorization_source: str | None
    occurred_on: date
    description: str = ""

    def __post_init__(self):
        object.__setattr__(
            self, "transaction_type", TransactionType.from_value(self.transaction_type)
        )


@dataclass(frozen=True)
class FinanceEvent:
    event_id: UUID
    event_type: EventType
    occurred_at: datetime
    version: int
    payload: TransactionSnapshot

    def __post_init__(self):
        if self.version != SUPPORTED_VERSION:
            raise InvalidEventError(f"Version de evento no soportada: {self.version}.")
        if self.occurred_at.tzinfo is None:
            raise InvalidEventError("occurred_at debe llevar zona horaria.")
        object.__setattr__(self, "event_type", EventType(self.event_type))
