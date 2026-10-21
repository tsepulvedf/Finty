"""Enumeraciones del dominio de suscripciones (`StrEnum`, C-15)."""
from enum import StrEnum


class PlanCode(StrEnum):
    FREE = "FREE"
    PREMIUM = "PREMIUM"


class SubscriptionStatus(StrEnum):
    """PENDING_PAYMENT → ACTIVE → CANCELED → EXPIRED (§6.7)."""

    PENDING_PAYMENT = "PENDING_PAYMENT"
    ACTIVE = "ACTIVE"
    CANCELED = "CANCELED"   # sigue dando acceso hasta el fin del periodo
    EXPIRED = "EXPIRED"


# Estados que ocupan el lugar unico de un usuario (constraint en la base).
CURRENT_STATUSES = (
    SubscriptionStatus.PENDING_PAYMENT,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.CANCELED,
)
# Estados que dan acceso premium mientras no termine el periodo.
GRANTING_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED)


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    ERROR = "ERROR"


FINAL_PAYMENT_STATUSES = (PaymentStatus.APPROVED, PaymentStatus.DECLINED, PaymentStatus.ERROR)


class Benefit(StrEnum):
    """Beneficios de un plan, como `code` estables que traduce el frontend (Phase 0)."""

    TRANSACTION_TRACKING = "transaction_tracking"
    STANDARD_DASHBOARD = "standard_dashboard"
    HISTORY_3_MONTHS = "history_3_months"
    INSIGHTS = "insights"
    SPENDING_PATTERNS = "spending_patterns"
    UNLIMITED_HISTORY = "unlimited_history"
    INVESTMENT_RECOMMENDATIONS = "investment_recommendations"
    INVESTMENT_PLANS = "investment_plans"
