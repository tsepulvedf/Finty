"""Dobles de los puertos de recommendation-service, sin red ni Redis."""
from datetime import date, datetime
from decimal import Decimal

from domain.analytics import (
    AnalyticsSnapshot,
    CategorySpike,
    MonthlyNet,
    NegativeSavings,
    RecurringExpense,
)
from domain.exchange import COP, USD, ExchangeRate
from domain.interfaces import (
    AnalyticsReader,
    AnalyticsUnavailable,
    ExchangeRateCache,
    ExchangeRateProvider,
    ExchangeRateUnavailable,
)
from domain.period import Period
from domain.shared.value_objects import Money
from domain.value_objects import ExchangeRateSource

NOW = datetime(2026, 10, 21, 10, 0)
TODAY = NOW.date()
TRM = Decimal("3163.76")


def fixed_clock(now=NOW):
    return lambda: now


def nets(values, currency="COP"):
    """`{"2026-09": "500000", ...}` → tupla de `MonthlyNet`."""
    return tuple(MonthlyNet(Period.parse(p), Money(v, currency)) for p, v in values.items())


def spike(category="Alimentación", current="200000", average="100000", pct="100.0", currency="COP"):
    return CategorySpike(category, Decimal(pct), Money(current, currency), Money(average, currency))


def negative(income="100000", expense="150000", currency="COP"):
    deficit = Money(Decimal(expense) - Decimal(income), currency)
    return NegativeSavings(deficit, Money(income, currency), Money(expense, currency))


def recurring(description="netflix", amount="39900", currency="COP"):
    return RecurringExpense(description, "Entretenimiento", Money(amount, currency), 3, 6, Decimal("1.00"), date(2026, 10, 3))


class FakeAnalytics(AnalyticsReader):
    def __init__(self):
        self.down = False
        self.spikes = ()
        self.negative_savings = ()
        self.recurring = ()
        self.monthly_nets = ()
        self.calls = []

    def snapshot(self, user_id, period):
        self.calls.append((user_id, period))
        if self.down:
            raise AnalyticsUnavailable("analytics caido")
        return AnalyticsSnapshot(period, self.spikes, self.negative_savings, self.recurring, self.monthly_nets)


class FakeRateProvider(ExchangeRateProvider):
    def __init__(self, rate=TRM):
        self.value = rate
        self.down = False
        self.calls = 0

    def rate(self, base, target, on):
        self.calls += 1
        if self.down:
            raise ExchangeRateUnavailable("API caida")
        return ExchangeRate(USD, COP, self.value, ExchangeRateSource.LIVE, on, on, on)


class MemoryRateCache(ExchangeRateCache):
    """Mismo contrato que el cache de Redis: lo que sale, sale como `cached`."""

    def __init__(self):
        self.days = {}
        self.last = None
        self.ttls = []

    def today(self, base, target, on):
        rate = self.days.get(on)
        return rate.with_source(ExchangeRateSource.CACHED) if rate else None

    def last_known(self, base, target):
        return self.last.with_source(ExchangeRateSource.CACHED) if self.last else None

    def store(self, exchange_rate, on, expires_in):
        self.days[on] = exchange_rate
        self.last = exchange_rate
        self.ttls.append(expires_in)
