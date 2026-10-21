"""`InvestmentPlan`: una recomendacion de inversion guardada por el usuario.

El plan fija el tipo de instrumento, el aporte mensual y el horizonte, y guarda el
tipo de perfil con que se creo, para que su proyeccion no cambie si el usuario
responde de nuevo el cuestionario.

**Proyeccion.** Aportes al final de cada mes, con capitalizacion mensual a la tasa
anual ILUSTRATIVA del perfil dividida entre 12:

    valor = aporte * ((1 + r) ** n - 1) / r,    r = tasa_anual / 12

Con r = 0, valor = aporte * n. Es un calculo didactico, no una promesa de
rentabilidad: la respuesta lo marca como ilustrativo y lleva el aviso.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from domain.exceptions import (
    InstrumentNotRecommendedError,
    InvalidHorizonError,
    InvalidMonthlyContributionError,
)
from domain.recommendations import MONTHS_PER_YEAR, instruments_for
from domain.shared.value_objects import Money
from domain.value_objects import InstrumentType, RiskProfileType

MIN_HORIZON_MONTHS = 1


@dataclass(frozen=True)
class InvestmentPlanDraft:
    """Plan validado, listo para persistir."""

    instrument_type: InstrumentType
    risk_profile_type: RiskProfileType
    monthly_contribution: Money
    horizon_months: int


@dataclass(frozen=True)
class Projection:
    annual_rate: Decimal
    total_contributed: Money
    projected_value: Money

    @property
    def projected_gain(self):
        return self.projected_value - self.total_contributed


def build_plan(instrument_type, profile_type, monthly_contribution, horizon_months, max_horizon):
    """Valida las reglas del plan y devuelve el borrador."""
    if monthly_contribution.amount <= 0:
        raise InvalidMonthlyContributionError()
    if not MIN_HORIZON_MONTHS <= horizon_months <= max_horizon:
        raise InvalidHorizonError(
            f"El horizonte debe estar entre {MIN_HORIZON_MONTHS} y {max_horizon} meses."
        )
    instrument = InstrumentType(instrument_type)
    profile = RiskProfileType(profile_type)
    if instrument not in instruments_for(profile):
        raise InstrumentNotRecommendedError(
            f"'{instrument.value}' no es un instrumento recomendado para el perfil "
            f"'{profile.value}'."
        )
    return InvestmentPlanDraft(instrument, profile, monthly_contribution, horizon_months)


def project(monthly_contribution, horizon_months, annual_rate):
    """Proyeccion del plan con la tasa ilustrativa (formula en el docstring)."""
    currency = monthly_contribution.currency
    amount = monthly_contribution.amount
    total = Money(amount * horizon_months, currency)
    monthly_rate = Decimal(annual_rate) / MONTHS_PER_YEAR
    if monthly_rate == 0:
        value = amount * horizon_months
    else:
        value = amount * ((1 + monthly_rate) ** horizon_months - 1) / monthly_rate
    return Projection(
        annual_rate=Decimal(annual_rate),
        total_contributed=total,
        projected_value=Money(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), currency),
    )
