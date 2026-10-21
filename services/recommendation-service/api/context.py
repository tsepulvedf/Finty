"""Estado por peticion y armado de los servicios (anillo externo).

La identidad sale solo de `X-User-Id`, que pone el Gateway tras `auth_request`
(ADR-09). Los adaptadores concretos los construye `app.py` y quedan en
`app.extensions`; los tests los reemplazan por dobles con las mismas claves.
"""
from uuid import UUID

from flask import current_app, g, request
from werkzeug.exceptions import MethodNotAllowed

from api.errors import NotAuthenticated
from services import (
    ExchangeRateService,
    InvestmentPlanService,
    RecommendationService,
    RiskProfileService,
)

SESSION_FACTORY_KEY = "finty.session_factory"
ANALYTICS_READER_KEY = "finty.analytics_reader"
RATE_PROVIDER_KEY = "finty.exchange_rate_provider"
RATE_CACHE_KEY = "finty.exchange_rate_cache"
RATE_FALLBACK_KEY = "finty.exchange_rate_fallback"
CLOCK_KEY = "finty.clock"
USER_ID_HEADER = "X-User-Id"
PUBLIC_ENDPOINTS = {"health"}


def db_session():
    if "db_session" not in g:
        g.db_session = current_app.extensions[SESSION_FACTORY_KEY]()
    return g.db_session


def close_db_session(_exc=None):
    session = g.pop("db_session", None)
    if session is not None:
        session.close()


def current_user_id():
    return g.user_id


def identify_user():
    """Exige `X-User-Id` en las rutas autenticadas, antes del despacho (como DRF)."""
    routing_error = request.routing_exception
    if routing_error is not None and not isinstance(routing_error, MethodNotAllowed):
        return
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    try:
        g.user_id = UUID(request.headers.get(USER_ID_HEADER, "").strip())
    except ValueError as exc:
        raise NotAuthenticated() from exc


def _extension(key):
    return current_app.extensions[key]


def exchange_rate_service():
    return ExchangeRateService(
        _extension(RATE_PROVIDER_KEY),
        _extension(RATE_CACHE_KEY),
        _extension(RATE_FALLBACK_KEY),
        _extension(CLOCK_KEY),
    )


def risk_profile_service():
    return RiskProfileService(db_session())


def recommendation_service():
    return RecommendationService(
        db_session(),
        _extension(ANALYTICS_READER_KEY),
        exchange_rate_service(),
        current_app.config["RECOMMENDATION_SETTINGS"],
        _extension(CLOCK_KEY),
    )


def investment_plan_service():
    return InvestmentPlanService(db_session(), current_app.config["RECOMMENDATION_SETTINGS"])
