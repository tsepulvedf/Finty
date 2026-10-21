"""Eventos de dominio de `finance-service` (anillo de Dominio, Python puro).

Lo que este servicio le cuenta al resto del sistema cuando cambia una
transaccion (ADR-15). Los nombres salen del Event Storming de DDD Stage 1, salvo
`TransactionDeleted`, que se agrega para que `analytics` no cuente
transacciones borradas (§12).

Son value objects inmutables. Cada evento lleva una **foto completa** de la
transaccion en ese momento, para que el consumidor no tenga que consultar a
`finance-service` (ADR-10): con el ultimo evento de una transaccion sabe todo lo
que necesita, y `TransactionDeleted` le dice que la olvide.

Como se serializan para viajar por Redis es asunto de `infra/`, no de aqui.
"""
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from domain.shared.exceptions import ValidationError
from domain.shared.value_objects import Money
from domain.value_objects import CategorizationSource, TransactionType

# Version del esquema del evento. Sube cuando cambia la forma del payload de
# modo incompatible; los consumidores la leen para decidir como interpretarlo.
EVENT_SCHEMA_VERSION = 1


class EventType(StrEnum):
    """Tipos de evento que publica `finance-service`."""

    TRANSACTION_MANUALLY_ADDED = "TransactionManuallyAdded"
    TRANSACTION_CATEGORIZED = "TransactionCategorized"
    TRANSACTION_DELETED = "TransactionDeleted"


@dataclass(frozen=True)
class TransactionFacts:
    """Foto de una transaccion: el payload de todos los eventos de transaccion."""

    user_id: UUID
    transaction_id: UUID
    account_id: UUID
    amount: Money
    transaction_type: TransactionType
    category_name: str | None
    categorization_source: CategorizationSource | None
    occurred_on: date
    # Agregado en E2-M4b: `analytics` detecta gastos recurrentes por descripcion.
    description: str = ""

    def __post_init__(self):
        if not isinstance(self.amount, Money):
            raise ValidationError("El monto de un evento debe ser un Money.")
        object.__setattr__(
            self, "transaction_type", TransactionType.from_value(self.transaction_type)
        )
        if self.categorization_source is not None:
            object.__setattr__(
                self, "categorization_source", CategorizationSource(self.categorization_source)
            )


@dataclass(frozen=True)
class DomainEvent:
    """Un hecho del dominio, con identidad propia.

    `event_id` es lo que hace idempotente al consumidor: la entrega es al menos
    una vez (ADR-15), y un evento repetido se reconoce por su id.
    `occurred_at` debe traer zona horaria.
    """

    event_id: UUID
    event_type: EventType
    occurred_at: datetime
    version: int
    payload: TransactionFacts

    def __post_init__(self):
        object.__setattr__(self, "event_type", EventType(self.event_type))
        if self.occurred_at.tzinfo is None:
            raise ValidationError("occurred_at debe llevar zona horaria.")
        if not isinstance(self.payload, TransactionFacts):
            raise ValidationError("El payload de un evento de transaccion es TransactionFacts.")


def _event(event_type, facts, occurred_at, event_id=None):
    return DomainEvent(
        event_id=event_id or uuid4(),
        event_type=event_type,
        occurred_at=occurred_at,
        version=EVENT_SCHEMA_VERSION,
        payload=facts,
    )


def transaction_manually_added(facts, occurred_at, event_id=None):
    """Se registro una transaccion."""
    return _event(EventType.TRANSACTION_MANUALLY_ADDED, facts, occurred_at, event_id)


def transaction_categorized(facts, occurred_at, event_id=None):
    """Se reclasifico manualmente una transaccion; `facts` trae la categoria nueva."""
    return _event(EventType.TRANSACTION_CATEGORIZED, facts, occurred_at, event_id)


def transaction_deleted(facts, occurred_at, event_id=None):
    """Se elimino una transaccion; `facts` es como estaba antes de borrarla."""
    return _event(EventType.TRANSACTION_DELETED, facts, occurred_at, event_id)
