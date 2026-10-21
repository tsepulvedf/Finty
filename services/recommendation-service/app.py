"""Fabrica de la aplicacion Flask de `recommendation-service`.

    gunicorn "app:create_app()"

Configuracion por entorno:
- `DATABASE_URL` (obligatoria): URL de `finty_recommendation`, y solo de ella (A-21).
- `ANALYTICS_URL` (opcional, `http://analytics-service:8000`) y `ANALYTICS_TIMEOUT`
  (segundos, `1`): cliente de analytics por la red interna.
- `REDIS_URL` (opcional, `redis://redis:6379/0`): cache de tasas.
- `EXCHANGE_RATE_API_URL` (opcional, la TRM de datos.gov.co), `EXCHANGE_RATE_TIMEOUT`
  (segundos, `3`) y `EXCHANGE_RATE_FALLBACK_USD_COP` (tasa fija, `3200`).
- `TIME_ZONE` (opcional, `America/Bogota`): zona del proceso (RULES.md).
- `ENTITLEMENTS_URL` (opcional, `http://subscription-service:8000`),
  `ENTITLEMENTS_TIMEOUT` (`1` s) y `ENTITLEMENTS_CACHE_SECONDS` (`30`): gating
  premium de INV-06 (`api/gating.py`).
- Parametros de las reglas, `RECOMMENDATION_<NOMBRE>` (ver `domain/settings.py`):
  `RECOMMENDATION_SURPLUS_MONTHS`, `RECOMMENDATION_RATE_CONSERVATIVE`,
  `RECOMMENDATION_RATE_MODERATE`, `RECOMMENDATION_RATE_AGGRESSIVE` y
  `RECOMMENDATION_MAX_HORIZON_MONTHS`.
"""
import os
import time
from dataclasses import fields
from datetime import datetime
from decimal import Decimal

from flask import Flask, jsonify

from api.context import (
    ANALYTICS_READER_KEY,
    CLOCK_KEY,
    RATE_CACHE_KEY,
    RATE_FALLBACK_KEY,
    RATE_PROVIDER_KEY,
    SESSION_FACTORY_KEY,
    close_db_session,
    db_session,
    identify_user,
)
from api.errors import register_error_handlers
from api.gating import ENTITLEMENTS_READER_KEY, enforce_entitlements
from api.routes import exchange_rates, investment_plans, recommendations
from domain.settings import RecommendationSettings
from infra.analytics_client import HttpAnalyticsReader
from infra.configuration import ConfigurationError
from infra.database import build_engine, build_session_factory, ping
from infra.entitlements import CachedEntitlementsReader, HttpEntitlementsReader
from infra.exchange_rates import DEFAULT_TRM_URL, FixedExchangeRateProvider, TrmExchangeRateProvider
from infra.rate_cache import RedisExchangeRateCache

DEFAULT_TIME_ZONE = "America/Bogota"
DEFAULT_REDIS_URL = "redis://redis:6379/0"
DEFAULT_ANALYTICS_URL = "http://analytics-service:8000"
DEFAULT_ANALYTICS_TIMEOUT = "1"
DEFAULT_EXCHANGE_RATE_TIMEOUT = "3"
# Ultimo recurso de la cadena de tasas (ADR-12). Referencia: la TRM oficial del
# 2026-10-21 fue 3163,76 COP por dolar; 3200 es ese valor redondeado. Revisar si
# la TRM se aleja mucho: una tasa fija desactualizada distorsiona las cifras.
DEFAULT_FALLBACK_USD_COP = "3200"
DEFAULT_ENTITLEMENTS_URL = "http://subscription-service:8000"
DEFAULT_ENTITLEMENTS_TIMEOUT = "1"
DEFAULT_ENTITLEMENTS_CACHE_SECONDS = "30"
SETTINGS_PREFIX = "RECOMMENDATION_"


def health():
    ping(db_session())
    return jsonify({"status": "ok"})


def _set_process_time_zone(time_zone):
    """Zona horaria del proceso, como en todos los servicios Flask (RULES.md)."""
    os.environ["TZ"] = time_zone
    if hasattr(time, "tzset"):
        time.tzset()


def settings_from_environment(environ=os.environ):
    """`RecommendationSettings` con lo que defina el entorno; el resto, por defecto."""
    values = {}
    for field in fields(RecommendationSettings):
        raw = environ.get(SETTINGS_PREFIX + field.name.upper())
        if raw is not None:
            values[field.name] = Decimal(raw) if field.type in (Decimal, "Decimal") else int(raw)
    return RecommendationSettings(**values)


def _session_factory_from_environment():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ConfigurationError(
            "Falta la variable de entorno obligatoria 'DATABASE_URL' con la URL de "
            "la base finty_recommendation."
        )
    return build_session_factory(build_engine(database_url))


def _install_adapters(app):
    """Adaptadores concretos de cada puerto; los tests ya traen los suyos."""
    env = os.environ
    extensions = app.extensions
    extensions.setdefault(ANALYTICS_READER_KEY, HttpAnalyticsReader(
        env.get("ANALYTICS_URL", DEFAULT_ANALYTICS_URL),
        timeout=float(env.get("ANALYTICS_TIMEOUT", DEFAULT_ANALYTICS_TIMEOUT)),
    ))
    extensions.setdefault(RATE_PROVIDER_KEY, TrmExchangeRateProvider(
        env.get("EXCHANGE_RATE_API_URL", DEFAULT_TRM_URL),
        timeout=float(env.get("EXCHANGE_RATE_TIMEOUT", DEFAULT_EXCHANGE_RATE_TIMEOUT)),
    ))
    extensions.setdefault(RATE_CACHE_KEY, RedisExchangeRateCache.from_url(env.get("REDIS_URL", DEFAULT_REDIS_URL)))
    extensions.setdefault(RATE_FALLBACK_KEY, FixedExchangeRateProvider(
        env.get("EXCHANGE_RATE_FALLBACK_USD_COP", DEFAULT_FALLBACK_USD_COP)
    ))
    extensions.setdefault(CLOCK_KEY, datetime.now)
    if ENTITLEMENTS_READER_KEY not in extensions:
        # Derechos premium de subscription-service, con cache corta de los "si" (INV-06).
        extensions[ENTITLEMENTS_READER_KEY] = CachedEntitlementsReader.from_url(
            HttpEntitlementsReader(
                env.get("ENTITLEMENTS_URL", DEFAULT_ENTITLEMENTS_URL),
                timeout=float(env.get("ENTITLEMENTS_TIMEOUT", DEFAULT_ENTITLEMENTS_TIMEOUT)),
            ),
            env.get("REDIS_URL", DEFAULT_REDIS_URL),
            int(env.get("ENTITLEMENTS_CACHE_SECONDS", DEFAULT_ENTITLEMENTS_CACHE_SECONDS)),
        )


def create_app(session_factory=None, config=None, adapters=None):
    app = Flask(__name__, static_folder=None)
    app.config["TIME_ZONE"] = os.environ.get("TIME_ZONE", DEFAULT_TIME_ZONE)
    app.config["RECOMMENDATION_SETTINGS"] = settings_from_environment()
    app.config.update(config or {})
    _set_process_time_zone(app.config["TIME_ZONE"])

    app.json.compact = True
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    app.extensions[SESSION_FACTORY_KEY] = session_factory or _session_factory_from_environment()
    app.extensions.update(adapters or {})
    _install_adapters(app)

    app.before_request(identify_user)
    app.before_request(enforce_entitlements)
    app.teardown_appcontext(close_db_session)
    register_error_handlers(app)

    app.register_blueprint(recommendations)
    app.register_blueprint(investment_plans)
    app.register_blueprint(exchange_rates)
    app.add_url_rule("/health/", "health", health)
    return app
