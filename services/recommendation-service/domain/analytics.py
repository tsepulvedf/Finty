"""Lo que recommendation-service sabe de analytics, en su propio lenguaje.

El adaptador HTTP (`infra/analytics_client.py`) traduce las respuestas de
analytics-service (§10.6) a estos value objects. Ninguna estructura JSON de
analytics cruza el puerto `AnalyticsReader`.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from domain.period import Period
from domain.shared.value_objects import Money


@dataclass(frozen=True)
class CategorySpike:
    """Insight `category_spike`: una categoria se disparo frente a su promedio."""

    category_name: str
    increase_pct: Decimal
    current: Money
    previous_average: Money


@dataclass(frozen=True)
class NegativeSavings:
    """Insight `negative_savings`: los gastos superaron a los ingresos."""

    deficit: Money
    income: Money
    expense: Money


@dataclass(frozen=True)
class RecurringExpense:
    """Un `SpendingPattern` de analytics: gasto que se repite."""

    description: str
    category_name: str | None
    average_amount: Money
    months_present: int
    window_months: int
    monthly_frequency: Decimal
    last_seen: date


@dataclass(frozen=True)
class MonthlyNet:
    """Neto (ingresos menos gastos) de un mes en una moneda, segun el dashboard."""

    period: Period
    net: Money


@dataclass(frozen=True)
class AnalyticsSnapshot:
    """Todo lo que una recomendacion necesita de analytics para un periodo."""

    period: Period
    spikes: tuple = field(default_factory=tuple)
    negative_savings: tuple = field(default_factory=tuple)
    recurring: tuple = field(default_factory=tuple)
    monthly_nets: tuple = field(default_factory=tuple)
