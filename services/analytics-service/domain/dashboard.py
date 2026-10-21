"""`Dashboard` de un periodo (anillo de Dominio, Python puro).

Reglas deterministas, sin estado y explicables (Phase 0):
- Ingresos, gastos y neto (`ingresos - gastos`) del periodo.
- Desglose por categoria y por cuenta, con la participacion de cada categoria
  en el total de su tipo.
- Tendencia de los ultimos `trend_months` meses, incluido el pedido.

**Nunca se suman monedas distintas:** el dashboard esta partido por moneda, y
cada `CurrencyDashboard` solo contiene cifras de la suya. La conversion entre
monedas llega en E2-M5. No se persiste: se calcula al leer.
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from domain.period import Period
from domain.shared.value_objects import Money
from domain.value_objects import TransactionType

SHARE_QUANTUM = Decimal("0.0001")


def total_of(amounts, currency):
    """Suma de `Money` de una misma moneda; cero si no hay ninguno."""
    result = Money.zero(currency)
    for amount in amounts:
        result = result.add(amount)
    return result


def share(part, whole):
    """Fraccion `part / whole` con cuatro decimales; cero si `whole` es cero."""
    if whole.is_zero():
        return Decimal("0")
    return (part.amount / whole.amount).quantize(SHARE_QUANTUM)


@dataclass(frozen=True)
class Totals:
    """Ingresos, gastos y neto en una moneda."""

    income: Money
    expense: Money

    @property
    def net(self):
        return self.income.subtract(self.expense)

    @classmethod
    def of(cls, facts, currency):
        income = total_of((f.amount for f in facts if not f.is_expense), currency)
        expense = total_of((f.amount for f in facts if f.is_expense), currency)
        return cls(income, expense)


@dataclass(frozen=True)
class CategoryTotal:
    """Lo movido en una categoria y su participacion en el total de su tipo."""

    category_name: str | None
    transaction_type: TransactionType
    total: Money
    share: Decimal


@dataclass(frozen=True)
class AccountTotal:
    account_id: object
    totals: Totals


@dataclass(frozen=True)
class TrendPoint:
    period: Period
    totals: Totals


@dataclass(frozen=True)
class CurrencyDashboard:
    """Todas las cifras del dashboard en una sola moneda."""

    currency: str
    totals: Totals
    categories: tuple
    accounts: tuple
    trend: tuple


@dataclass(frozen=True)
class Dashboard:
    """Dashboard de un periodo, una seccion por moneda."""

    period: Period
    currencies: tuple

    @classmethod
    def build(cls, period, facts, trend_months=6):
        """Calcula el dashboard de `period` con las transacciones vigentes dadas.

        `facts` puede traer meses de mas: cada cifra filtra los suyos.
        """
        window = period.window(trend_months)
        in_window = [f for f in facts if window[0] <= f.period <= period]
        currencies = sorted({f.currency for f in in_window})
        return cls(
            period,
            tuple(_currency_dashboard(period, window, in_window, c) for c in currencies),
        )


def _currency_dashboard(period, window, facts, currency):
    mine = [f for f in facts if f.currency == currency]
    current = [f for f in mine if f.period == period]
    totals = Totals.of(current, currency)
    return CurrencyDashboard(
        currency=currency,
        totals=totals,
        categories=_categories(current, totals, currency),
        accounts=_accounts(current, currency),
        trend=tuple(
            TrendPoint(month, Totals.of([f for f in mine if f.period == month], currency))
            for month in window
        ),
    )


def _categories(facts, totals, currency):
    groups = defaultdict(list)
    for fact in facts:
        groups[(fact.transaction_type, fact.category_name)].append(fact.amount)

    rows = []
    for (kind, name), amounts in groups.items():
        total = total_of(amounts, currency)
        whole = totals.expense if kind is TransactionType.EXPENSE else totals.income
        rows.append(CategoryTotal(name, kind, total, share(total, whole)))
    # Gastos primero; dentro de cada tipo, de mayor a menor; empate por nombre.
    rows.sort(key=lambda r: (r.transaction_type is not TransactionType.EXPENSE, -r.total.amount, r.category_name or ""))
    return tuple(rows)


def _accounts(facts, currency):
    by_account = defaultdict(list)
    for fact in facts:
        by_account[fact.account_id].append(fact)
    return tuple(
        AccountTotal(account_id, Totals.of(rows, currency))
        for account_id, rows in sorted(by_account.items(), key=lambda item: str(item[0]))
    )
