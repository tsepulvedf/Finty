"""Parametros de las reglas de recomendacion, configurables (ARCHITECTURE.md §6.6).

`app.py` los lee del entorno con el prefijo `RECOMMENDATION_`, por ejemplo
`RECOMMENDATION_RATE_MODERATE=0.09`.
"""
from dataclasses import dataclass
from decimal import Decimal

from domain.value_objects import RiskProfileType


@dataclass(frozen=True)
class RecommendationSettings:
    # Meses completos anteriores al actual con que se promedia el excedente.
    surplus_months: int = 3

    # Tasas anuales ILUSTRATIVAS de la proyeccion de un plan, por perfil. No son
    # rentabilidades de ningun producto: la respuesta las marca como tales.
    rate_conservative: Decimal = Decimal("0.08")
    rate_moderate: Decimal = Decimal("0.10")
    rate_aggressive: Decimal = Decimal("0.12")

    # Horizonte maximo de un plan: 50 años.
    max_horizon_months: int = 600

    def illustrative_rate(self, profile_type):
        return {
            RiskProfileType.CONSERVATIVE: self.rate_conservative,
            RiskProfileType.MODERATE: self.rate_moderate,
            RiskProfileType.AGGRESSIVE: self.rate_aggressive,
        }[RiskProfileType(profile_type)]
