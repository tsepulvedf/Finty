"""Errores de dominio de subscription-service (Python puro), con `code` estable."""
from domain.shared.exceptions import BusinessRuleError, NotFoundError, ValidationError


class PlanNotPurchasableError(ValidationError):
    """El plan FREE no se compra."""

    default_code = "plan_not_purchasable"
    default_message = "El plan FREE no requiere pago."


class SubscriptionAlreadyActiveError(BusinessRuleError):
    """El usuario ya tiene una suscripcion vigente (activa o cancelada en periodo)."""

    default_code = "subscription_already_active"
    default_message = "Ya tienes una suscripción vigente. Podrás renovarla cuando termine su período."


class PaymentInProgressError(BusinessRuleError):
    """Hay un pago pendiente de resolver para la suscripcion."""

    default_code = "payment_in_progress"
    default_message = "Tienes un pago en proceso. Espera a que se resuelva."


class NoActiveSubscriptionError(BusinessRuleError):
    """No hay una suscripcion activa que cancelar."""

    default_code = "no_active_subscription"
    default_message = "No tienes una suscripción activa."


class PaymentNotFoundError(NotFoundError):
    default_code = "payment_not_found"
    default_message = "No existe ese pago."


class InvalidTransitionError(BusinessRuleError):
    """Una transicion que la maquina de estados no permite."""

    default_code = "invalid_subscription_transition"
    default_message = "La suscripción no admite ese cambio de estado."
