"""`Insight`: hallazgos explicables sobre un periodo (anillo de Dominio).

Cada insight lleva un `code` estable y sus `params`, para que el frontend lo
traduzca por codigo (igual que D-21), y la `evidence`: los numeros exactos que
lo justifican. Ninguno es una caja negra (Phase 0 exige explicabilidad).

Tres reglas, por moneda y sin mezclar monedas:

- **CATEGORY_SPIKE** (warning): el gasto de una categoria en el periodo supera
  en `spike_ratio` o mas el promedio de los `spike_lookback_months` meses
  anteriores (los meses sin gasto cuentan como cero), y vale al menos
  `spike_min_amount`. Sin gasto en los meses anteriores no hay base para
  comparar, y no se reporta.
- **TOP_CATEGORY** (info): la categoria con mayor participacion en el gasto del
  periodo. Empate: la primera por nombre.
- **NEGATIVE_SAVINGS** (warning): los gastos del periodo superan los ingresos.

Las transacciones sin categoria entran en los totales pero no generan insights
de categoria. No se persisten: se calculan al leer.
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from domain.dashboard import Totals, share, total_of
from domain.period import Period
from domain.shared.value_objects import Money

PERCENT_QUANTUM = Decimal("0.1")
HUNDRED = Decimal("100")


class InsightType(StrEnum):
    CATEGORY_SPIKE = "CATEGORY_SPIKE"
    TOP_CATEGORY = "TOP_CATEGORY"
    NEGATIVE_SAVINGS = "NEGATIVE_SAVINGS"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"


@dataclass(frozen=True)
class Insight:
    """Un hallazgo. `params` y `evidence` son tuplas de pares `(clave, valor)`."""

    type: InsightType
    severity: Severity
    period: Period
    params: tuple
    evidence: tuple

    @property
    def code(self):
        """Codigo estable para traducir: `category_spike`, `top_category`, ..."""
        return self.type.value.lower()


def _percent(value):
    return (value * HUNDRED).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def detect_insights(period, facts, thresholds):
    """Insights de `period`. `facts` debe incluir los meses de comparacion."""
    found = []
    for currency in sorted({f.currency for f in facts if f.period == period}):
        mine = [f for f in facts if f.currency == currency]
        found.extend(_negative_savings(period, mine, currency))
        found.extend(_category_spikes(period, mine, currency, thresholds))
        found.extend(_top_category(period, mine, currency))
    # Primero las advertencias; luego en el orden de las reglas.
    order = list(InsightType)
    found.sort(key=lambda i: (i.severity is not Severity.WARNING, order.index(i.type)))
    return tuple(found)


def _expenses_by_category(facts, period, currency):
    groups = defaultdict(list)
    for fact in facts:
        if fact.is_expense and fact.period == period and fact.category_name is not None:
            groups[fact.category_name].append(fact.amount)
    return {name: total_of(amounts, currency) for name, amounts in groups.items()}


def _negative_savings(period, facts, currency):
    totals = Totals.of([f for f in facts if f.period == period], currency)
    if totals.expense <= totals.income:
        return []
    return [
        Insight(
            InsightType.NEGATIVE_SAVINGS,
            Severity.WARNING,
            period,
            params=(("currency", currency), ("deficit", totals.expense.subtract(totals.income))),
            evidence=(("income", totals.income), ("expense", totals.expense)),
        )
    ]


def _category_spikes(period, facts, currency, thresholds):
    current = _expenses_by_category(facts, period, currency)
    lookback = period.previous(thresholds.spike_lookback_months)
    history = [_expenses_by_category(facts, month, currency) for month in lookback]

    found = []
    for name in sorted(current):
        previous = [month.get(name) for month in history]
        previous_totals = [amount.amount if amount else Decimal("0") for amount in previous]
        average = sum(previous_totals, Decimal("0")) / len(previous_totals)
        amount = current[name].amount
        if average <= 0 or amount < thresholds.spike_min_amount:
            continue
        increase = amount / average - 1
        if increase < thresholds.spike_ratio:
            continue
        average_money = Money(average, currency)
        found.append(
            Insight(
                InsightType.CATEGORY_SPIKE,
                Severity.WARNING,
                period,
                params=(
                    ("category_name", name),
                    ("currency", currency),
                    ("increase_pct", _percent(increase)),
                ),
                evidence=(
                    ("current", current[name]),
                    ("previous_average", average_money),
                    ("previous_months", tuple(
                        (str(month), Money(total, currency))
                        for month, total in zip(lookback, previous_totals)
                    )),
                    ("threshold_pct", _percent(thresholds.spike_ratio)),
                    ("min_amount", Money(thresholds.spike_min_amount, currency)),
                ),
            )
        )
    return found


def _top_category(period, facts, currency):
    by_category = _expenses_by_category(facts, period, currency)
    expense = Totals.of([f for f in facts if f.period == period], currency).expense
    if not by_category or expense.is_zero():
        return []
    name, amount = min(by_category.items(), key=lambda item: (-item[1].amount, item[0]))
    return [
        Insight(
            InsightType.TOP_CATEGORY,
            Severity.INFO,
            period,
            params=(
                ("category_name", name),
                ("currency", currency),
                ("share_pct", _percent(share(amount, expense))),
            ),
            evidence=(("category_total", amount), ("expense_total", expense)),
        )
    ]
