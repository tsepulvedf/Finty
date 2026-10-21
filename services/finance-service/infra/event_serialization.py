"""Serializacion de los eventos de dominio para el stream (ARCHITECTURE.md §10.5).

Unico lugar que decide como viaja un evento. Un mensaje de Redis Streams es un
mapa plano de cadenas, asi que el evento se publica con cinco campos:

    event_id      UUID del evento (clave de idempotencia del consumidor)
    event_type    TransactionManuallyAdded | TransactionCategorized | TransactionDeleted
    version       "1"
    occurred_at   ISO 8601 en UTC, con "Z"
    payload       JSON con la foto de la transaccion (abajo)

    payload = {
      "user_id": "...", "transaction_id": "...", "account_id": "...",
      "amount": "120000.00", "currency": "COP", "transaction_type": "expense",
      "category_name": "Alimentación" | null,
      "categorization_source": "rule" | "mock" | "ai" | "manual" | null,
      "occurred_on": "2026-10-19"
    }

El monto viaja como texto decimal con dos cifras, nunca como float.
"""
import json
from datetime import timezone

UTC_SUFFIX = "+00:00"


def _instant(value):
    text = value.astimezone(timezone.utc).isoformat()
    return text[: -len(UTC_SUFFIX)] + "Z" if text.endswith(UTC_SUFFIX) else text


def payload_to_dict(facts):
    """Payload JSON de un `TransactionFacts`."""
    source = facts.categorization_source
    return {
        "user_id": str(facts.user_id),
        "transaction_id": str(facts.transaction_id),
        "account_id": str(facts.account_id),
        "amount": f"{facts.amount.amount:f}",
        "currency": facts.amount.currency,
        "transaction_type": facts.transaction_type.value,
        "category_name": facts.category_name,
        "categorization_source": source.value if source is not None else None,
        "occurred_on": facts.occurred_on.isoformat(),
    }


def to_stream_message(event):
    """Mensaje plano de cadenas, listo para `XADD`."""
    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type.value,
        "version": str(event.version),
        "occurred_at": _instant(event.occurred_at),
        "payload": json.dumps(payload_to_dict(event.payload), ensure_ascii=False, sort_keys=True),
    }
