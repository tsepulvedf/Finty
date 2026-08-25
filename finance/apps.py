"""Configuracion de la app `finance`."""
from django.apps import AppConfig


class FinanceConfig(AppConfig):
    """FinancialDataContext: cuentas, transacciones y categorias."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"
