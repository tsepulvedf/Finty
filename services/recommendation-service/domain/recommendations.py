"""`Recommendation`: value object calculado al leer (ARCHITECTURE.md §6.6).

Reglas deterministas y explicables (Phase 0): cada recomendacion lleva un `code`
estable, los `params` con que el frontend la traduce, la `evidence` numerica que
la justifica y su `source`, que dice de que salio.

**De optimizacion** (de los insights y patrones de analytics):
- `category_spike`  → `reduce_category`
- `negative_savings` → `build_budget`
- un `SpendingPattern` → `review_recurring_expense`

**De inversion** (del excedente mensual promedio y del perfil de riesgo):
- excedente <= 0 → solo `build_emergency_fund`
- excedente > 0  → `invest_by_risk_profile`, con tipos de instrumento genericos

Toda recomendacion de inversion lleva el aviso de que no constituye asesoria
financiera (`has_disclaimer`).
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from domain.shared.value_objects import Money
from domain.value_objects import (
    InstrumentType,
    RecommendationKind,
    RecommendationSource,
    RiskProfileType,
)

# Moneda por defecto de una cuenta (§5.2): la del excedente cuando no hay datos.
DEFAULT_CURRENCY = "COP"
MONTHS_PER_YEAR = 12
FREQUENCY_QUANTUM = Decimal("0.01")

INSTRUMENTS_BY_PROFILE = {
    RiskProfileType.CONSERVATIVE: (InstrumentType.CDT, InstrumentType.LIQUIDITY_FUND),
    RiskProfileType.MODERATE: (InstrumentType.COLLECTIVE_INVESTMENT_FUND,),
    RiskProfileType.AGGRESSIVE: (InstrumentType.ETF, InstrumentType.STOCKS),
}


@dataclass(frozen=True)
class Recommendation:
    code: str
    kind: RecommendationKind
    source: RecommendationSource
    params: tuple = ()    # ((clave, valor), ...)
    evidence: tuple = ()  # ((clave, valor), ...)

    @property
    def has_disclaimer(self):
        return self.kind is RecommendationKind.INVESTMENT

    def money_entries(self):
        """`(clave, Money)` de primer nivel en params y evidencia (para convertir)."""
        return tuple(
            (key, value) for key, value in self.params + self.evidence if isinstance(value, Money)
        )


@dataclass(frozen=True)
class Surplus:
    """Excedente mensual promedio de una moneda y los meses de los que sale."""

    average: Money
    months: tuple  # ((Period, Money neto), ...)

    @property
    def currency(self):
        return self.average.currency


def instruments_for(profile_type):
    return INSTRUMENTS_BY_PROFILE[RiskProfileType(profile_type)]


# --- Optimizacion -------------------------------------------------------------


def _reduce_category(spike):
    return Recommendation(
        code="reduce_category",
        kind=RecommendationKind.OPTIMIZATION,
        source=RecommendationSource.INSIGHT,
        params=(
            ("category_name", spike.category_name),
            ("currency", spike.current.currency),
            ("increase_pct", spike.increase_pct),
        ),
        evidence=(
            ("current", spike.current),
            ("previous_average", spike.previous_average),
            # Volver al promedio liberaria esta cantidad en el mes.
            ("potential_saving", spike.current - spike.previous_average),
        ),
    )


def _build_budget(negative):
    return Recommendation(
        code="build_budget",
        kind=RecommendationKind.OPTIMIZATION,
        source=RecommendationSource.INSIGHT,
        params=(("currency", negative.deficit.currency), ("deficit", negative.deficit)),
        evidence=(("income", negative.income), ("expense", negative.expense)),
    )


def _review_recurring(pattern):
    annual = pattern.average_amount.amount * pattern.monthly_frequency * MONTHS_PER_YEAR
    return Recommendation(
        code="review_recurring_expense",
        kind=RecommendationKind.OPTIMIZATION,
        source=RecommendationSource.PATTERN,
        params=(
            ("description", pattern.description),
            ("category_name", pattern.category_name),
            ("currency", pattern.average_amount.currency),
            ("average_amount", pattern.average_amount),
        ),
        evidence=(
            ("months_present", pattern.months_present),
            ("window_months", pattern.window_months),
            ("monthly_frequency", pattern.monthly_frequency),
            ("last_seen", pattern.last_seen),
            # Costo de un año al ritmo observado: lo que pesa ese gasto fijo.
            ("annualized_cost", Money(annual, pattern.average_amount.currency)),
        ),
    )


def optimization_recommendations(snapshot):
    """Una recomendacion por insight o patron relevante, en orden estable."""
    return (
        tuple(_build_budget(n) for n in snapshot.negative_savings)
        + tuple(_reduce_category(s) for s in snapshot.spikes)
        + tuple(_review_recurring(p) for p in snapshot.recurring)
    )


# --- Excedente e inversion ----------------------------------------------------


def monthly_surpluses(reference, monthly_nets, months):
    """Excedente promedio de los `months` meses completos anteriores a `reference`.

    Por moneda: nunca se suman COP y USD. Un mes sin movimientos cuenta como
    cero. Sin ningun dato, un excedente de cero en la moneda por defecto.
    """
    considered = reference.previous(months)
    by_currency = {}
    for item in monthly_nets:
        by_currency.setdefault(item.net.currency, {})[item.period] = item.net
    if not by_currency:
        by_currency = {DEFAULT_CURRENCY: {}}

    surpluses = []
    for currency in sorted(by_currency):
        nets = tuple((p, by_currency[currency].get(p, Money.zero(currency))) for p in considered)
        total = sum((net.amount for _, net in nets), Decimal("0"))
        average = (total / len(nets)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        surpluses.append(Surplus(Money(average, currency), nets))
    return tuple(surpluses)


def _emergency_fund(surplus):
    return Recommendation(
        code="build_emergency_fund",
        kind=RecommendationKind.INVESTMENT,
        source=RecommendationSource.RISK_PROFILE,
        params=(("currency", surplus.currency), ("monthly_surplus", surplus.average)),
        evidence=(("surplus_months", surplus.months),),
    )


def _invest(profile_type, surplus):
    params = (
        ("risk_profile_type", RiskProfileType(profile_type)),
        ("instrument_types", instruments_for(profile_type)),
        ("currency", surplus.currency if surplus else None),
        ("monthly_surplus", surplus.average if surplus else None),
    )
    evidence = (("surplus_months", surplus.months),) if surplus else ()
    return Recommendation(
        code="invest_by_risk_profile",
        kind=RecommendationKind.INVESTMENT,
        source=RecommendationSource.RISK_PROFILE,
        params=params,
        evidence=evidence,
    )


def investment_recommendations(profile_type, surpluses):
    """Recomendaciones de inversion.

    - Sin perfil de riesgo: ninguna (su `source` seria falso).
    - `surpluses is None` (analytics no respondio): solo con el perfil.
    - Por moneda: excedente <= 0 → solo fondo de emergencia; > 0 → instrumento.
    """
    if profile_type is None:
        return ()
    if surpluses is None:
        return (_invest(profile_type, None),)
    return tuple(
        _emergency_fund(s) if s.average.amount <= 0 else _invest(profile_type, s)
        for s in surpluses
    )
