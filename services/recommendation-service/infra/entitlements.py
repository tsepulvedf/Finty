"""Cliente del endpoint interno de derechos de subscription-service (INV-06, D-14).

- `HttpEntitlementsReader`: `GET /internal/entitlements/<user_id>` por la red
  interna, con timeout corto. Cualquier fallo es `EntitlementsUnavailable`.
- `CachedEntitlementsReader`: cache corta en Redis **solo de los derechos
  premium**, con TTL `min(ENTITLEMENTS_CACHE_SECONDS, hasta el fin del periodo)`.
  Un "no premium" nunca se cachea: quien acaba de pagar ve el cambio en la
  siguiente peticion. Un "si" cacheado no puede durar mas que el periodo pagado,
  y en esta entrega nada revoca un periodo antes de su fin (cancelar mantiene el
  acceso hasta el final), asi que la cache no extiende ningun acceso.
  Si Redis falla, se consulta directo.
"""
import json
import logging
import urllib.request
from datetime import datetime, timezone

import redis

from domain.entitlements import Entitlement
from domain.interfaces import EntitlementsReader, EntitlementsUnavailable

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 1.0
DEFAULT_CACHE_SECONDS = 30
CACHE_PREFIX = "finty:entitlements"
SOCKET_TIMEOUT_SECONDS = 0.5


def _utcnow():
    return datetime.now(timezone.utc)


def _parse(body):
    premium = body["premium"]
    if not isinstance(premium, bool):
        raise ValueError(f"premium no es booleano: {premium!r}")
    until = datetime.fromisoformat(body["until"]) if body.get("until") else None
    if premium and until is None:
        raise ValueError("premium sin fin de periodo")
    return Entitlement(premium, until)


class HttpEntitlementsReader(EntitlementsReader):
    def __init__(self, base_url, timeout=DEFAULT_TIMEOUT_SECONDS):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def entitlement(self, user_id):
        url = f"{self._base_url}/internal/entitlements/{user_id}"
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as response:
                return _parse(json.loads(response.read().decode("utf-8")))
        except Exception as exc:  # noqa: BLE001 — red, HTTP o forma: todo niega
            raise EntitlementsUnavailable(f"{type(exc).__name__}: {exc}") from exc


class CachedEntitlementsReader(EntitlementsReader):
    def __init__(self, inner, client, ttl=DEFAULT_CACHE_SECONDS, clock=_utcnow):
        self._inner = inner
        self._client = client
        self._ttl = ttl
        self._clock = clock

    @classmethod
    def from_url(cls, inner, redis_url, ttl=DEFAULT_CACHE_SECONDS):
        client = redis.Redis.from_url(
            redis_url, decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT_SECONDS, socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        )
        return cls(inner, client, ttl)

    def entitlement(self, user_id):
        key = f"{CACHE_PREFIX}:{user_id}"
        cached = self._read(key)
        if cached is not None and cached.is_premium_at(self._clock()):
            return cached
        found = self._inner.entitlement(user_id)
        if found.premium and found.until is not None:
            remaining = int((found.until - self._clock()).total_seconds())
            ttl = min(self._ttl, remaining)
            if ttl > 0:
                self._write(key, found, ttl)
        return found

    def _read(self, key):
        try:
            raw = self._client.get(key)
            return _parse(json.loads(raw)) if raw else None
        except (redis.RedisError, ValueError, KeyError) as exc:
            logger.warning("cache de derechos no disponible (%s)", exc)
            return None

    def _write(self, key, entitlement, ttl):
        try:
            self._client.set(key, json.dumps({"premium": True, "until": entitlement.until.isoformat()}), ex=ttl)
        except redis.RedisError as exc:
            logger.warning("no se pudo cachear el derecho (%s)", exc)
