"""`SubscriptionPlan`: value object de los planes FREE y PREMIUM (ARCHITECTURE.md §6.7)."""
from dataclasses import dataclass

from domain.value_objects import Benefit, PlanCode

DEFAULT_PREMIUM_PRICE_IN_CENTS = 2_990_000  # 29 900 COP al mes
DEFAULT_CURRENCY = "COP"
PERIOD_MONTHS = 1
FREE_HISTORY_MONTHS = 3

FREE_BENEFITS = (
    Benefit.TRANSACTION_TRACKING,
    Benefit.STANDARD_DASHBOARD,
    Benefit.HISTORY_3_MONTHS,
    Benefit.OPTIMIZATION_RECOMMENDATIONS,
)
PREMIUM_BENEFITS = (
    Benefit.TRANSACTION_TRACKING,
    Benefit.STANDARD_DASHBOARD,
    Benefit.OPTIMIZATION_RECOMMENDATIONS,
    Benefit.INSIGHTS,
    Benefit.SPENDING_PATTERNS,
    Benefit.UNLIMITED_HISTORY,
    Benefit.INVESTMENT_RECOMMENDATIONS,
    Benefit.INVESTMENT_PLANS,
)


@dataclass(frozen=True)
class SubscriptionPlan:
    code: PlanCode
    price_in_cents: int
    currency: str
    period_months: int
    history_months: int | None   # None: historial ilimitado
    benefits: tuple

    @property
    def is_paid(self):
        return self.price_in_cents > 0


def plan_catalog(premium_price_in_cents=DEFAULT_PREMIUM_PRICE_IN_CENTS, currency=DEFAULT_CURRENCY):
    """Los dos planes, en orden. El precio del premium es configurable."""
    return {
        PlanCode.FREE: SubscriptionPlan(PlanCode.FREE, 0, currency, PERIOD_MONTHS, FREE_HISTORY_MONTHS, FREE_BENEFITS),
        PlanCode.PREMIUM: SubscriptionPlan(
            PlanCode.PREMIUM, int(premium_price_in_cents), currency, PERIOD_MONTHS, None, PREMIUM_BENEFITS
        ),
    }
