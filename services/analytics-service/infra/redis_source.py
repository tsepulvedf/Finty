"""Consumo de `finty.finance.events` con un grupo de consumidores de Redis Streams.

Implementa el puerto `EventSource` (ADR-15):

- **Grupo `analytics`:** se crea la primera vez con `XGROUP CREATE ... 0`, es
  decir, desde el inicio del stream, para recibir la historia completa.
- **Lectura:** `XREADGROUP ... >`, solo mensajes nuevos para el grupo.
- **Confirmacion:** `XACK`, que el worker llama solo despues del commit en la
  base. Un mensaje leido y no confirmado queda en la lista de pendientes.
- **Recuperacion:** `XAUTOCLAIM` reclama los pendientes que llevan mas de
  `claim_min_idle_ms` sin confirmar, de este consumidor o de uno que murio.
"""
import socket

import redis

from domain.interfaces import EventSource, EventSourceUnavailable

FINANCE_EVENTS_STREAM = "finty.finance.events"
ANALYTICS_GROUP = "analytics"
SOCKET_TIMEOUT_SECONDS = 10.0


class RedisEventSource(EventSource):
    def __init__(self, client, stream=FINANCE_EVENTS_STREAM, group=ANALYTICS_GROUP,
                 consumer=None, block_ms=5000, count=100, claim_min_idle_ms=0):
        self._client = client
        self._stream = stream
        self._group = group
        self._consumer = consumer or socket.gethostname()
        self._block_ms = block_ms
        self._count = count
        self._claim_min_idle_ms = claim_min_idle_ms

    @classmethod
    def from_url(cls, url, **kwargs):
        client = redis.Redis.from_url(
            url,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
            decode_responses=True,
        )
        return cls(client, **kwargs)

    def ensure_group(self):
        try:
            self._client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except redis.exceptions.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise EventSourceUnavailable(str(exc)) from exc
        except redis.exceptions.RedisError as exc:
            raise EventSourceUnavailable(f"{type(exc).__name__}: {exc}") from exc

    def claim_pending(self):
        claimed, start = [], "0-0"
        try:
            while True:
                result = self._client.xautoclaim(
                    self._stream, self._group, self._consumer,
                    min_idle_time=self._claim_min_idle_ms, start_id=start, count=self._count,
                )
                start, messages = result[0], result[1]
                claimed.extend((mid, fields) for mid, fields in messages if fields)
                if start in ("0-0", b"0-0"):
                    return claimed
        except redis.exceptions.RedisError as exc:
            raise EventSourceUnavailable(f"{type(exc).__name__}: {exc}") from exc

    def read_new(self):
        try:
            response = self._client.xreadgroup(
                self._group, self._consumer, {self._stream: ">"},
                count=self._count, block=self._block_ms,
            )
        except redis.exceptions.RedisError as exc:
            raise EventSourceUnavailable(f"{type(exc).__name__}: {exc}") from exc
        return [(mid, fields) for _, messages in (response or []) for mid, fields in messages]

    def ack(self, message_id):
        try:
            self._client.xack(self._stream, self._group, message_id)
        except redis.exceptions.RedisError as exc:
            raise EventSourceUnavailable(f"{type(exc).__name__}: {exc}") from exc
