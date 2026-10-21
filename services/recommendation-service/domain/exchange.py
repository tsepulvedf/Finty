"""`ExchangeRate`: value object del Adapter de tasas de cambio (ADR-12).

El adaptador concreto traduce la respuesta de la API oficial a este valor; ningun
campo de la API cruza el puerto `ExchangeRateProvider`.

La conversion es **solo de presentacion** (INV-11, C-28): ningun monto
persistido cambia de moneda.
"""
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from domain.exceptions import UnsupportedCurrencyPairError
from domain.shared.value_objects import Money, validate_currency_code
from domain.value_objects import ExchangeRateSource

# La TRM oficial es pesos por dolar: el unico par que conoce el Adapter.
USD = "USD"
COP = "COP"
SUPPORTED_CURRENCIES = frozenset({USD, COP})
INVERSE_QUANTUM = Decimal("0.0000000001")


def ensure_supported_currency(code):
    """Normaliza una moneda de presentacion o lanza `UnsupportedCurrencyPairError`."""
    currency = validate_currency_code(code)
    if currency not in SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyPairError(
            f"No se puede presentar en {currency}: solo se convierte entre USD y COP."
        )
    return currency


def ensure_supported_pair(base, target):
    """Normaliza el par o lanza `UnsupportedCurrencyPairError`."""
    pair = (validate_currency_code(base), validate_currency_code(target))
    if pair[0] == pair[1] or not set(pair) <= SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyPairError(
            f"No hay tasa para {pair[0]}→{pair[1]}: solo se convierte entre USD y COP."
        )
    return pair


@dataclass(frozen=True)
class ExchangeRate:
    """Cuantas unidades de `target` vale una de `base`, y de donde salio."""

    base: str
    target: str
    rate: Decimal
    source: ExchangeRateSource
    valid_from: date | None = None    # vigencia segun la fuente oficial
    valid_until: date | None = None
    fetched_on: date | None = None    # dia en que se consulto la API

    def with_source(self, source):
        return replace(self, source=ExchangeRateSource(source))

    def inverse(self):
        return replace(
            self,
            base=self.target,
            target=self.base,
            rate=(Decimal(1) / self.rate).quantize(INVERSE_QUANTUM, rounding=ROUND_HALF_UP),
        )

    def convert(self, money):
        """`money` en `base` → su equivalente en `target`, con dos decimales."""
        if money.currency != self.base:
            raise UnsupportedCurrencyPairError(
                f"Esta tasa convierte {self.base}, no {money.currency}."
            )
        return Money(money.amount * self.rate, self.target)


def seconds_until_next_day(now):
    """Segundos hasta la medianoche local: el TTL del cache del dia."""
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    return max(1, int((tomorrow - now).total_seconds()))
