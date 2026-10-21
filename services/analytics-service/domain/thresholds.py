"""Umbrales de las reglas de analytics, configurables (ARCHITECTURE.md §6.5).

Los defaults son los acordados para E2-M4b. `app.py` los lee del entorno con el
prefijo `ANALYTICS_` (por ejemplo `ANALYTICS_SPIKE_RATIO=0.5`).
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class AnalyticsThresholds:
    """Todos los numeros que gobiernan Dashboard, Insight, SpendingPattern y el resumen."""

    # Dashboard: meses de la tendencia, incluido el periodo pedido.
    trend_months: int = 6

    # CATEGORY_SPIKE: el gasto del periodo supera el promedio de los meses
    # anteriores en `spike_ratio` (0.30 = 30%) o mas, y vale al menos
    # `spike_min_amount` en la moneda de la categoria.
    spike_ratio: Decimal = Decimal("0.30")
    spike_min_amount: Decimal = Decimal("50000")
    spike_lookback_months: int = 3

    # SpendingPattern: aparece en `pattern_min_months` de los ultimos
    # `pattern_window_months`, con montos a `pattern_amount_tolerance` (0.10 =
    # +/-10%) de la mediana.
    pattern_window_months: int = 6
    pattern_min_months: int = 3
    pattern_amount_tolerance: Decimal = Decimal("0.10")

    # Resumen publico: una categoria solo aparece si la tienen al menos
    # `public_min_users` usuarios distintos (k-anonimato).
    public_min_users: int = 3
