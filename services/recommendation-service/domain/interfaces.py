"""Puertos de recommendation-service (ABC). `infra/` los implementa.

Los servicios dependen solo de estas abstracciones (RULES.md, regla 6).
"""
from abc import ABC, abstractmethod


class AnalyticsUnavailable(Exception):
    """analytics-service no respondio, respondio con error o fuera de contrato."""


class ExchangeRateUnavailable(Exception):
    """La API de tasas no respondio o respondio algo inutilizable."""


class AnalyticsReader(ABC):
    """Lee de analytics-service lo que necesitan las recomendaciones."""

    @abstractmethod
    def snapshot(self, user_id, period):
        """`AnalyticsSnapshot` del usuario para `period`, o `AnalyticsUnavailable`."""


class ExchangeRateProvider(ABC):
    """Puerto del Adapter de tasas de cambio (ADR-12)."""

    @abstractmethod
    def rate(self, base, target, on):
        """`ExchangeRate` vigente el dia `on`, o `ExchangeRateUnavailable`."""


class ExchangeRateCache(ABC):
    """Cache de tasas. Un fallo del cache nunca rompe una consulta."""

    @abstractmethod
    def today(self, base, target, on):
        """La tasa guardada hoy (`on`), o `None`."""

    @abstractmethod
    def last_known(self, base, target):
        """La ultima tasa conocida, de cualquier dia, o `None`."""

    @abstractmethod
    def store(self, exchange_rate, on, expires_in):
        """Guarda la tasa del dia (con TTL `expires_in` s) y la ultima conocida."""
