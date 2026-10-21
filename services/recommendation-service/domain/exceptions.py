"""Errores de dominio de recommendation-service (Python puro).

Cada uno lleva un `code` estable: el frontend traduce por codigo (E2-M8).
"""
from domain.shared.exceptions import BusinessRuleError, NotFoundError, ValidationError


class InvalidPeriodError(ValidationError):
    """Un periodo que no es un mes `AAAA-MM` valido."""

    default_code = "invalid_period"
    default_message = "Periodo invalido. Use el formato AAAA-MM, por ejemplo 2026-10."


class InvalidRiskAnswerError(ValidationError):
    """Una respuesta del cuestionario fuera de 1 a 3."""

    default_code = "invalid_risk_answer"
    default_message = "Cada respuesta del cuestionario de riesgo vale 1, 2 o 3."


class RiskProfileNotFoundError(NotFoundError):
    """El usuario todavia no respondio el cuestionario."""

    default_code = "risk_profile_not_found"
    default_message = "Todavia no has respondido el cuestionario de perfil de riesgo."


class RiskProfileRequiredError(BusinessRuleError):
    """Guardar un plan de inversion exige un perfil de riesgo."""

    default_code = "risk_profile_required"
    default_message = "Responde el cuestionario de perfil de riesgo antes de guardar un plan."


class InstrumentNotRecommendedError(ValidationError):
    """El instrumento no es uno de los recomendados para el perfil."""

    default_code = "instrument_not_recommended"
    default_message = "Ese tipo de instrumento no corresponde a tu perfil de riesgo."


class InvalidMonthlyContributionError(ValidationError):
    """El aporte mensual de un plan debe ser positivo."""

    default_code = "invalid_monthly_contribution"
    default_message = "El aporte mensual debe ser mayor que cero."


class InvalidHorizonError(ValidationError):
    """El horizonte de un plan esta fuera de rango."""

    default_code = "invalid_horizon"
    default_message = "El horizonte del plan esta fuera del rango permitido."


class InvestmentPlanNotFoundError(NotFoundError):
    """No existe el plan, o no es del usuario (D-08: 404, nunca 403)."""

    default_code = "investment_plan_not_found"
    default_message = "No existe ese plan de inversion."


class UnsupportedCurrencyPairError(ValidationError):
    """El Adapter de tasas solo conoce USD↔COP (ADR-12)."""

    default_code = "unsupported_currency_pair"
    default_message = "Solo se convierte entre USD y COP."
