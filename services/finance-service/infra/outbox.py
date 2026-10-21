"""Outbox transaccional sobre SQLAlchemy: implementa el puerto `EventOutbox` (ADR-15).

`record()` solo agrega una fila a la sesion: la escribe el mismo `commit` que el
cambio de negocio, asi que cambio y evento existen juntos o no existen. El
mensaje se guarda ya serializado, para que el relay lo publique tal cual.
"""
from domain.interfaces import EventOutbox
from infra.event_serialization import to_stream_message
from models import OutboxEvent


class SqlAlchemyOutbox(EventOutbox):
    """Escribe los eventos en `outbox_event`, dentro de la sesion recibida."""

    def __init__(self, session):
        self._session = session

    def record(self, event):
        self._session.add(
            OutboxEvent(
                event_id=event.event_id,
                event_type=event.event_type.value,
                aggregate_id=event.payload.transaction_id,
                version=event.version,
                occurred_at=event.occurred_at,
                message=to_stream_message(event),
            )
        )
