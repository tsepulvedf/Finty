"""Cache de tasas en Redis: implementa `ExchangeRateCache` (ADR-12).

Dos claves por par:
- `finty:fx:USD-COP:day:<AAAA-MM-DD>`, con TTL hasta la medianoche local: evita
  consultar la API mas de una vez al dia.
- `finty:fx:USD-COP:last`, sin TTL: la ultima tasa conocida, para cuando la API
  falle otro dia.

Si Redis no responde, el cache se comporta como vacio y no rompe la consulta: la
cadena sigue con la API o con la tasa fija.
"""
import json
import logging
from datetime import date
from decimal import Decimal

import redis

from domain.exchange import ExchangeRate
from domain.interfaces import ExchangeRateCache
from domain.value_objects import ExchangeRateSource

logger = logging.getLogger(__name__)

PREFIX = "finty:fx"
SOCKET_TIMEOUT_SECONDS = 0.5


def _date(text):
    return date.fromisoformat(text) if text else None


def _dump(rate):
    return json.dumps({
        "base": rate.base,
        "target": rate.target,
        "rate": str(rate.rate),
        "valid_from": rate.valid_from.isoformat() if rate.valid_from else None,
        "valid_until": rate.valid_until.isoformat() if rate.valid_until else None,
        "fetched_on": rate.fetched_on.isoformat() if rate.fetched_on else None,
    })


def _load(raw):
    data = json.loads(raw)
    return ExchangeRate(
        base=data["base"],
        target=data["target"],
        rate=Decimal(data["rate"]),
        # Lo que sale del cache se reporta como tal, aunque haya entrado `live`.
        source=ExchangeRateSource.CACHED,
        valid_from=_date(data["valid_from"]),
        valid_until=_date(data["valid_until"]),
        fetched_on=_date(data["fetched_on"]),
    )


def day_key(base, target, on):
    return f"{PREFIX}:{base}-{target}:day:{on.isoformat()}"


def last_key(base, target):
    return f"{PREFIX}:{base}-{target}:last"


class RedisExchangeRateCache(ExchangeRateCache):
    def __init__(self, client):
        self._client = client

    @classmethod
    def from_url(cls, url):
        return cls(redis.Redis.from_url(
            url, decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT_SECONDS, socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        ))

    def today(self, base, target, on):
        return self._read(day_key(base, target, on))

    def last_known(self, base, target):
        return self._read(last_key(base, target))

    def store(self, exchange_rate, on, expires_in):
        raw = _dump(exchange_rate)
        try:
            pipe = self._client.pipeline()
            pipe.set(day_key(exchange_rate.base, exchange_rate.target, on), raw, ex=expires_in)
            pipe.set(last_key(exchange_rate.base, exchange_rate.target), raw)
            pipe.execute()
        except redis.RedisError as exc:
            logger.warning("no se pudo guardar la tasa en Redis (%s)", exc)

    def _read(self, key):
        try:
            raw = self._client.get(key)
            return _load(raw) if raw else None
        except (redis.RedisError, ValueError, KeyError) as exc:
            logger.warning("cache de tasas no disponible (%s)", exc)
            return None
