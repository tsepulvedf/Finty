"""Stream de Redis: implementa el puerto `EventStream` (ADR-15).

Se usa Redis **Streams** (`XADD`) y no Pub/Sub: Pub/Sub entrega solo a quien
este conectado en ese instante y descarta el mensaje si no hay nadie, mientras
que un stream lo conserva hasta que cada grupo de consumidores lo procese. Es lo
que permite publicar hoy, sin consumidores (E2-M4a), y consumir despues.

No se recorta el stream (`MAXLEN`): `analytics` necesitara la historia completa
la primera vez que lo lea.
"""
import redis

from domain.interfaces import EventStream, EventStreamUnavailable

FINANCE_EVENTS_STREAM = "finty.finance.events"
SOCKET_TIMEOUT_SECONDS = 2.0


class RedisEventStream(EventStream):
    """Publica mensajes en un stream de Redis con `XADD`."""

    def __init__(self, client, stream=FINANCE_EVENTS_STREAM):
        self._client = client
        self._stream = stream

    @classmethod
    def from_url(cls, url, stream=FINANCE_EVENTS_STREAM):
        client = redis.Redis.from_url(
            url,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
            decode_responses=True,
        )
        return cls(client, stream)

    def publish(self, message):
        try:
            return self._client.xadd(self._stream, message)
        except redis.exceptions.RedisError as exc:
            raise EventStreamUnavailable(f"{type(exc).__name__}: {exc}") from exc
