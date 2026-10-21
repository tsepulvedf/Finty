"""Adaptadores del puerto `ExchangeRateProvider` (ADR-12).

**`TrmExchangeRateProvider`** consulta la TRM oficial del Banco de la Republica
publicada en datos.gov.co (conjunto `32sa-8pi3`, API Socrata). Forma real de la
respuesta, verificada el 2026-10-21:

    [{"valor": "3163.76", "unidad": "COP",
      "vigenciadesde": "2026-10-21T00:00:00.000",
      "vigenciahasta": "2026-10-21T00:00:00.000"}]

`valor` son pesos por dolar. Una misma TRM cubre varios dias en fines de semana y
festivos (por ejemplo, del 17 al 19), asi que se pide la mas reciente cuya
vigencia empezo a mas tardar el dia consultado. El adaptador traduce esa fila a
un `ExchangeRate` y ningun campo de la API sale de este modulo.

**`FixedExchangeRateProvider`** es el respaldo: una tasa fija configurable que
nunca falla y se reporta como `fallback`.
"""
import json
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal

from domain.exceptions import UnsupportedCurrencyPairError
from domain.exchange import COP, USD, ExchangeRate
from domain.interfaces import ExchangeRateProvider, ExchangeRateUnavailable
from domain.value_objects import ExchangeRateSource

DEFAULT_TRM_URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"
DEFAULT_TIMEOUT_SECONDS = 3.0


def _require_usd_cop(base, target):
    if (base, target) != (USD, COP):
        raise UnsupportedCurrencyPairError(f"Este adaptador solo publica USD→COP, no {base}→{target}.")


def _day(text):
    return date.fromisoformat(text[:10])


class TrmExchangeRateProvider(ExchangeRateProvider):
    def __init__(self, url=DEFAULT_TRM_URL, timeout=DEFAULT_TIMEOUT_SECONDS):
        self._url = url
        self._timeout = timeout

    def rate(self, base, target, on):
        _require_usd_cop(base, target)
        try:
            row = self._latest_row(on)
            if row.get("unidad") != COP:
                raise ExchangeRateUnavailable(f"unidad inesperada: {row.get('unidad')!r}")
            value = Decimal(str(row["valor"]))
            if not value.is_finite() or value <= 0:
                raise ExchangeRateUnavailable(f"valor invalido: {row['valor']!r}")
            return ExchangeRate(
                base=USD,
                target=COP,
                rate=value,
                source=ExchangeRateSource.LIVE,
                valid_from=_day(row["vigenciadesde"]),
                valid_until=_day(row["vigenciahasta"]),
                fetched_on=on,
            )
        except ExchangeRateUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — red, HTTP o una forma inesperada
            raise ExchangeRateUnavailable(f"{type(exc).__name__}: {exc}") from exc

    def _latest_row(self, on):
        query = urllib.parse.urlencode({
            "$where": f"vigenciadesde <= '{on.isoformat()}T00:00:00'",
            "$order": "vigenciadesde DESC",
            "$limit": "1",
        })
        request = urllib.request.Request(f"{self._url}?{query}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            rows = json.loads(response.read().decode("utf-8"))
        if not isinstance(rows, list) or not rows:
            raise ExchangeRateUnavailable("la API no devolvio ninguna TRM")
        return rows[0]


class FixedExchangeRateProvider(ExchangeRateProvider):
    """Ultimo recurso: nunca falla, y lo dice (`fallback`)."""

    def __init__(self, usd_cop):
        self._rate = Decimal(str(usd_cop))

    def rate(self, base, target, on):
        _require_usd_cop(base, target)
        return ExchangeRate(USD, COP, self._rate, ExchangeRateSource.FALLBACK)
