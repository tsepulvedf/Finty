"""Lectura de los mensajes de `finty.finance.events` (contrato en ARCHITECTURE.md §10.5).

Es el reflejo de `finance-service/infra/event_serialization.py`. Un mensaje que
no cumple el contrato produce `InvalidEventError`; el worker lo descarta con un
aviso en el log en lugar de bloquearse en el.
"""
import json
from datetime import date, datetime
from uuid import UUID

from domain.events import FinanceEvent, TransactionSnapshot
from domain.exceptions import InvalidEventError
from domain.shared.exceptions import DomainError
from domain.shared.value_objects import Money


def _instant(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def from_stream_fields(fields):
    """`FinanceEvent` a partir de los campos de una entrada del stream."""
    try:
        payload = json.loads(fields["payload"])
        return FinanceEvent(
            event_id=UUID(fields["event_id"]),
            event_type=fields["event_type"],
            occurred_at=_instant(fields["occurred_at"]),
            version=int(fields["version"]),
            payload=TransactionSnapshot(
                user_id=UUID(payload["user_id"]),
                transaction_id=UUID(payload["transaction_id"]),
                account_id=UUID(payload["account_id"]),
                amount=Money(payload["amount"], payload["currency"]),
                transaction_type=payload["transaction_type"],
                category_name=payload.get("category_name"),
                categorization_source=payload.get("categorization_source"),
                occurred_on=date.fromisoformat(payload["occurred_on"]),
                # Los eventos anteriores a E2-M4b no traen descripcion.
                description=payload.get("description") or "",
            ),
        )
    except InvalidEventError:
        raise
    except (KeyError, ValueError, TypeError, DomainError) as exc:
        raise InvalidEventError(f"Mensaje fuera de contrato: {type(exc).__name__}: {exc}") from exc
