"""`SpendingPattern`: gasto recurrente (anillo de Dominio, Python puro).

Un gasto es recurrente si, en los ultimos `pattern_window_months` meses
(incluido el de referencia), hay al menos `pattern_min_months` meses distintos
con un gasto de:

- la misma descripcion normalizada (`normalize_description`; una descripcion
  vacia nunca forma patron),
- la misma categoria y la misma moneda,
- y un monto a `pattern_amount_tolerance` (+/-10%) de la mediana del grupo.

Reporta el monto promedio, en cuantos meses aparece, cuantas veces por mes en
promedio y la ultima aparicion. No se persiste: se calcula al leer.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from domain.facts import normalize_description
from domain.period import Period
from domain.shared.value_objects import Money

FREQUENCY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class SpendingPattern:
    description: str
    category_name: str | None
    average_amount: Money
    months_present: int
    window_months: int
    occurrences: int
    monthly_frequency: Decimal
    last_seen: date

    @property
    def currency(self):
        return self.average_amount.currency


def detect_patterns(reference, facts, thresholds):
    """Gastos recurrentes en la ventana que termina en `reference`."""
    window = reference.window(thresholds.pattern_window_months)
    groups = defaultdict(list)
    for fact in facts:
        key = normalize_description(fact.description)
        if fact.is_expense and key and window[0] <= fact.period <= reference:
            groups[(key, fact.category_name, fact.currency)].append(fact)

    patterns = []
    for (description, category, currency), members in groups.items():
        center = median(f.amount.amount for f in members)
        tolerance = center * thresholds.pattern_amount_tolerance
        close = [f for f in members if abs(f.amount.amount - center) <= tolerance]
        months = {Period.of(f.occurred_on) for f in close}
        if len(months) < thresholds.pattern_min_months:
            continue
        average = sum((f.amount.amount for f in close), Decimal("0")) / len(close)
        patterns.append(
            SpendingPattern(
                description=description,
                category_name=category,
                average_amount=Money(average.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), currency),
                months_present=len(months),
                window_months=thresholds.pattern_window_months,
                occurrences=len(close),
                monthly_frequency=(Decimal(len(close)) / len(months)).quantize(FREQUENCY_QUANTUM),
                last_seen=max(f.occurred_on for f in close),
            )
        )
    patterns.sort(key=lambda p: (-p.months_present, p.description, p.currency))
    return tuple(patterns)
