"""Resumen publico de gasto por categoria, con k-anonimato (ADR-13).

Gasto agregado de **todos** los usuarios en un periodo, por categoria y moneda:
cuantos usuarios gastaron en ella, el total y el promedio por usuario.

**Privacidad:** una categoria solo aparece si la tienen al menos `min_users`
usuarios distintos (k = 3 por defecto). Con menos, el total o el promedio
dejarian inferir el gasto de una persona. Tampoco se publica un total general:
restandole las categorias visibles se obtendria la suma de las ocultas.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from domain.period import Period
from domain.shared.value_objects import Money

CENTS = Decimal("0.01")


@dataclass(frozen=True)
class CategorySpending:
    category_name: str | None
    users: int
    total: Money
    average_per_user: Money

    @property
    def currency(self):
        return self.total.currency


@dataclass(frozen=True)
class SpendingSummary:
    period: Period
    min_users: int
    categories: tuple

    @classmethod
    def build(cls, period, aggregates, min_users):
        """`aggregates`: tuplas `(category_name, currency, users, total)` del periodo."""
        rows = []
        for name, currency, users, total in aggregates:
            if users < min_users:
                continue
            average = (Decimal(total) / users).quantize(CENTS, rounding=ROUND_HALF_UP)
            rows.append(CategorySpending(name, users, Money(total, currency), Money(average, currency)))
        rows.sort(key=lambda r: (r.currency, -r.total.amount, r.category_name or ""))
        return cls(period, min_users, tuple(rows))
