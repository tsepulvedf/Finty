"""Fabrica de la aplicacion Flask de `analytics-service`.

    gunicorn "app:create_app()"        # API
    flask consume-events               # worker de eventos (contenedor analytics-worker)

Configuracion por entorno:
- `DATABASE_URL` (obligatoria): URL de `finty_analytics`, y solo de ella (A-21).
- `REDIS_URL` (opcional, `redis://redis:6379/0`): de donde lee el worker.
- `TIME_ZONE` (opcional, `America/Bogota`): zona del proceso (RULES.md).
- Umbrales de las reglas, `ANALYTICS_<NOMBRE>` (ver `domain/thresholds.py`):
  `ANALYTICS_SPIKE_RATIO`, `ANALYTICS_SPIKE_MIN_AMOUNT`,
  `ANALYTICS_SPIKE_LOOKBACK_MONTHS`, `ANALYTICS_TREND_MONTHS`,
  `ANALYTICS_PATTERN_WINDOW_MONTHS`, `ANALYTICS_PATTERN_MIN_MONTHS`,
  `ANALYTICS_PATTERN_AMOUNT_TOLERANCE` y `ANALYTICS_PUBLIC_MIN_USERS` (k).
"""
import os
import time
from dataclasses import fields
from decimal import Decimal

from flask import Flask, jsonify

from api.context import SESSION_FACTORY_KEY, close_db_session, db_session, identify_user
from api.errors import register_error_handlers
from api.routes import analytics as analytics_blueprint
from api.routes import public as public_blueprint
from commands import consume_events
from domain.thresholds import AnalyticsThresholds
from infra.configuration import ConfigurationError
from infra.database import build_engine, build_session_factory, ping

DEFAULT_TIME_ZONE = "America/Bogota"
DEFAULT_REDIS_URL = "redis://redis:6379/0"
THRESHOLD_PREFIX = "ANALYTICS_"


def health():
    ping(db_session())
    return jsonify({"status": "ok"})


def _set_process_time_zone(time_zone):
    """Zona horaria del proceso, como en todos los servicios Flask (RULES.md)."""
    os.environ["TZ"] = time_zone
    if hasattr(time, "tzset"):
        time.tzset()


def thresholds_from_environment(environ=os.environ):
    """`AnalyticsThresholds` con lo que defina el entorno; el resto, por defecto."""
    values = {}
    for field in fields(AnalyticsThresholds):
        raw = environ.get(THRESHOLD_PREFIX + field.name.upper())
        if raw is not None:
            values[field.name] = Decimal(raw) if field.type in (Decimal, "Decimal") else int(raw)
    return AnalyticsThresholds(**values)


def _session_factory_from_environment():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ConfigurationError(
            "Falta la variable de entorno obligatoria 'DATABASE_URL' con la URL de "
            "la base finty_analytics."
        )
    return build_session_factory(build_engine(database_url))


def create_app(session_factory=None, config=None):
    app = Flask(__name__, static_folder=None)
    app.config["TIME_ZONE"] = os.environ.get("TIME_ZONE", DEFAULT_TIME_ZONE)
    app.config["REDIS_URL"] = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
    app.config["ANALYTICS_THRESHOLDS"] = thresholds_from_environment()
    app.config.update(config or {})
    _set_process_time_zone(app.config["TIME_ZONE"])

    app.json.compact = True
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    app.extensions[SESSION_FACTORY_KEY] = session_factory or _session_factory_from_environment()

    app.before_request(identify_user)
    app.teardown_appcontext(close_db_session)
    register_error_handlers(app)

    app.register_blueprint(analytics_blueprint)
    app.register_blueprint(public_blueprint)
    app.add_url_rule("/health/", "health", health)
    app.cli.add_command(consume_events)
    return app
