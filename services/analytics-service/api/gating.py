"""INV-06 en analytics-service: las funciones premium exigen suscripcion activa (D-14).

Middleware de la capa de entrada (`before_request`); el dominio no sabe de planes.
Consulta el derecho en subscription-service (`EntitlementsReader`, con cache
corta en Redis) y aplica:

| Ruta | FREE | PREMIUM |
|---|---|---|
| `/analytics/insights/`, `/analytics/spending-patterns/` | 403 `premium_required` | si |
| `/analytics/dashboard/` | solo los ultimos 3 meses (otro periodo: 403), tendencia de 3 meses | todo |
| `POST /analytics/reports/` | solo los ultimos 3 meses (`require_visible_period`) | todo |
| `/public/spending-summary/` | sin gating: es el endpoint del aliado | — |

**Si subscription-service no responde, se niega** lo premium con 503
`entitlements_unavailable`, y lo gratuito sigue funcionando (fail-closed, §7.1).

**Llamadas internas.** `recommendation-service` lee insights, patrones y el
dashboard para calcular recomendaciones de optimizacion, que son gratuitas, y
se identifica con `X-Finty-Caller`. Esa cabecera, como `X-User-Id`, solo puede
llegar desde la red interna: Nginx la borra de toda peticion externa
(`proxy.conf`, ADR-09). Con ella no se aplica el gating: lo que se protege es la
ruta que ve el usuario.
"""
import logging
from dataclasses import replace
from datetime import date, datetime, timezone

from flask import current_app, g, request

import messages
from api.context import current_user_id, requested_period
from api.errors import EntitlementsUnavailableError, PremiumRequired
from domain.interfaces import EntitlementsUnavailable
from domain.period import Period

logger = logging.getLogger(__name__)

ENTITLEMENTS_READER_KEY = "finty.entitlements_reader"
INTERNAL_CALLER_HEADER = "X-Finty-Caller"
FREE_HISTORY_MONTHS = 3

PREMIUM_ENDPOINTS = {"analytics.insights", "analytics.spending_patterns"}
HISTORY_ENDPOINTS = {"analytics.dashboard"}

PREMIUM = "premium"
FREE = "free"
UNAVAILABLE = "unavailable"


def _access():
    """`premium`, `free` o `unavailable` para el usuario de la peticion."""
    if request.headers.get(INTERNAL_CALLER_HEADER):
        return PREMIUM
    try:
        entitlement = current_app.extensions[ENTITLEMENTS_READER_KEY].entitlement(current_user_id())
    except EntitlementsUnavailable as exc:
        logger.warning("derechos premium no verificables (%s); se niega lo premium", exc)
        return UNAVAILABLE
    return PREMIUM if entitlement.is_premium_at(datetime.now(timezone.utc)) else FREE


def _deny(access, message=None):
    if access == UNAVAILABLE:
        raise EntitlementsUnavailableError()
    raise PremiumRequired(message)


def free_history_window():
    """Primer periodo que ve un usuario FREE: los ultimos 3 meses, incluido el actual."""
    return Period.of(date.today()).window(FREE_HISTORY_MONTHS)[0]


def enforce_entitlements():
    endpoint = request.endpoint
    if endpoint in PREMIUM_ENDPOINTS:
        access = _access()
        if access != PREMIUM:
            _deny(access)
    elif endpoint in HISTORY_ENDPOINTS:
        access = _access()
        g.limited_history = access != PREMIUM
        if g.limited_history and requested_period() < free_history_window():
            _deny(access, messages.PREMIUM_HISTORY_REQUIRED.format(months=FREE_HISTORY_MONTHS))


def require_visible_period(period):
    """El reporte mensual sigue la misma ventana que el dashboard (INV-06).

    Se llama desde la ruta porque el periodo viene en el cuerpo del POST, no en
    la consulta. Un periodo dentro de la ventana gratuita no consulta el plan;
    uno fuera de ella exige Premium (403), o responde 503 si no se puede verificar.
    """
    if period >= free_history_window():
        return
    access = _access()
    if access != PREMIUM:
        _deny(access, messages.PREMIUM_HISTORY_REQUIRED.format(months=FREE_HISTORY_MONTHS))


def earliest_visible_period():
    """Primer periodo que ve el usuario: la ventana Free, o `None` con Premium."""
    return free_history_window() if g.get("limited_history") else None


def effective_thresholds():
    """Umbrales de la peticion: sin premium, la tendencia cubre solo 3 meses."""
    thresholds = current_app.config["ANALYTICS_THRESHOLDS"]
    if g.get("limited_history"):
        return replace(thresholds, trend_months=min(thresholds.trend_months, FREE_HISTORY_MONTHS))
    return thresholds
