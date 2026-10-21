"""Enumeraciones del dominio de recomendaciones (`StrEnum`, C-15)."""
from enum import StrEnum


class RiskProfileType(StrEnum):
    """Resultado del cuestionario de `RiskProfile`."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class InstrumentType(StrEnum):
    """Tipos de instrumento genericos. Nunca un producto ni una entidad concreta."""

    CDT = "cdt"
    LIQUIDITY_FUND = "liquidity_fund"
    COLLECTIVE_INVESTMENT_FUND = "collective_investment_fund"
    ETF = "etf"
    STOCKS = "stocks"


class RecommendationKind(StrEnum):
    OPTIMIZATION = "optimization"
    INVESTMENT = "investment"


class RecommendationSource(StrEnum):
    """De que sale una recomendacion. Veraz, como la procedencia de A-14."""

    INSIGHT = "insight"
    PATTERN = "pattern"
    RISK_PROFILE = "risk_profile"


class ExchangeRateSource(StrEnum):
    """Procedencia de una tasa (ADR-12), con el criterio de veracidad de A-14.

    - `live`: la respondio la API oficial en esta misma consulta.
    - `cached`: salio del cache de Redis (la del dia o la ultima conocida).
    - `fallback`: la tasa fija configurada; ni la API ni el cache la tenian.
    """

    LIVE = "live"
    CACHED = "cached"
    FALLBACK = "fallback"
