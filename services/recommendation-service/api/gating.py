"""INV-06 en recommendation-service: las funciones premium exigen suscripcion activa (D-14).

Middleware de la capa de entrada (`before_request`); el dominio no sabe de planes.

| Ruta | FREE | PREMIUM |
|---|---|---|
| `/investment-plans/` (todo) | 403 `premium_required` | si |
| `/recommendations/` | solo las de optimizacion; la inversion sale en `locked` | todo |
| `/recommendations/risk-profile/` | si | si |
| `/exchange-rates/` | si: es una utilidad de presentacion | si |

**Si subscription-service no responde, se niega** lo premium (503
`entitlements_unavailable` en los planes; `locked` con ese code en las
recomendaciones), y lo gratuito sigue funcionando (fail-closed, §7.1).
"""
import logging
from datetime import datetime, timezone

from flask import current_app, g, request

from api.context import current_user_id
from api.errors import EntitlementsUnavailableError, PremiumRequired
from domain.interfaces import EntitlementsUnavailable

logger = logging.getLogger(__name__)

ENTITLEMENTS_READER_KEY = "finty.entitlements_reader"
PREMIUM_BLUEPRINTS = {"investment_plans"}
PARTIAL_ENDPOINTS = {"recommendations.list_recommendations"}

PREMIUM_REQUIRED_CODE = "premium_required"
UNAVAILABLE_CODE = "entitlements_unavailable"


def _lock_code():
    """`None` si el usuario es premium; si no, el `code` que explica por que no."""
    try:
        entitlement = current_app.extensions[ENTITLEMENTS_READER_KEY].entitlement(current_user_id())
    except EntitlementsUnavailable as exc:
        logger.warning("derechos premium no verificables (%s); se niega lo premium", exc)
        return UNAVAILABLE_CODE
    return None if entitlement.is_premium_at(datetime.now(timezone.utc)) else PREMIUM_REQUIRED_CODE


def enforce_entitlements():
    if request.blueprint in PREMIUM_BLUEPRINTS and request.endpoint is not None:
        code = _lock_code()
        if code == UNAVAILABLE_CODE:
            raise EntitlementsUnavailableError()
        if code == PREMIUM_REQUIRED_CODE:
            raise PremiumRequired()
    elif request.endpoint in PARTIAL_ENDPOINTS:
        g.investment_lock = _lock_code()


def investment_lock():
    """`code` por el que las recomendaciones de inversion no salen, o `None`."""
    return g.get("investment_lock")
