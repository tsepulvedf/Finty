"""Mensajes del stream con la forma exacta de §10.5, y un origen en memoria."""
import json
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from domain.interfaces import EventSource, EventSourceUnavailable
from infra.event_deserialization import from_stream_fields

BASE_TIME = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


class Transaction:
    """Una transaccion de finance-service vista desde sus eventos."""

    def __init__(self, user_id=None, amount="120000.00", kind="expense", category="Alimentación",
                 on=date(2026, 10, 10), currency="COP", description="", account_id=None):
        self.transaction_id = uuid4()
        self.user_id = user_id or uuid4()
        self.account_id = account_id or uuid4()
        self.payload = {
            "user_id": str(self.user_id),
            "transaction_id": str(self.transaction_id),
            "account_id": str(self.account_id),
            "amount": amount,
            "currency": currency,
            "transaction_type": kind,
            "category_name": category,
            "categorization_source": "rule",
            "occurred_on": on.isoformat(),
            "description": description,
        }
        self._clock = 0

    def message(self, event_type, seconds=None, event_id=None, **changes):
        """Campos de una entrada del stream para este evento."""
        self._clock += 1
        self.payload.update(changes)
        moment = BASE_TIME + timedelta(seconds=self._clock if seconds is None else seconds)
        return {
            "event_id": str(event_id or uuid4()),
            "event_type": event_type,
            "version": "1",
            "occurred_at": moment.isoformat().replace("+00:00", "Z"),
            "payload": json.dumps(self.payload, ensure_ascii=False),
        }

    def added(self, **kwargs):
        return self.message("TransactionManuallyAdded", **kwargs)

    def categorized(self, category, **kwargs):
        return self.message("TransactionCategorized", category_name=category,
                            categorization_source="manual", **kwargs)

    def deleted(self, **kwargs):
        return self.message("TransactionDeleted", **kwargs)


def event(fields):
    return from_stream_fields(fields)


class MemorySource(EventSource):
    """Grupo de consumidores en memoria: entrega, pendientes y confirmaciones."""

    def __init__(self, messages=()):
        self.queue = [(f"{i + 1}-0", m) for i, m in enumerate(messages)]
        self.pending = {}
        self.acked = []
        self.down = False

    def _check(self):
        if self.down:
            raise EventSourceUnavailable("caido")

    def ensure_group(self):
        self._check()

    def claim_pending(self):
        self._check()
        return list(self.pending.items())

    def read_new(self):
        self._check()
        batch, self.queue = self.queue, []
        self.pending.update(batch)
        return batch

    def ack(self, message_id):
        self._check()
        self.pending.pop(message_id, None)
        self.acked.append(message_id)
