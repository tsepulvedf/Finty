"""Fabrica de la aplicacion Flask de `analytics-service`.

    gunicorn "app:create_app()"        # API
    flask consume-events               # worker de eventos (contenedor analytics-worker)
    celery -A celery_app:celery worker # reportes mensuales (contenedor analytics-celery, E2-M7)

Configuracion por entorno:
- `DATABASE_URL` (obligatoria): URL de `finty_analytics`, y solo de ella (A-21).
- `REDIS_URL` (opcional, `redis://redis:6379/0`): de donde lee el worker.
- `TIME_ZONE` (opcional, `America/Bogota`): zona del proceso (RULES.md).
- `CELERY_BROKER_URL` (opcional, `redis://redis:6379/1`): broker de Celery, en
  otra base logica que el stream y las caches (ADR-15).
- `ENTITLEMENTS_URL` (opcional, `http://subscription-service:8000`),
  `ENTITLEMENTS_TIMEOUT` (`1` s) y `ENTITLEMENTS_CACHE_SECONDS` (`30`): gating
  premium de INV-06 (`api/gating.py`).
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

from api.context import (
    REPORT_QUEUE_KEY,
    REPORT_RENDERER_KEY,
    SESSION_FACTORY_KEY,
    close_db_session,
    db_session,
    identify_user,
)
from api.errors import register_error_handlers
from api.gating import ENTITLEMENTS_READER_KEY, enforce_entitlements
from api.routes import analytics as analytics_blueprint
from api.routes import public as public_blueprint
from commands import consume_events
from domain.thresholds import AnalyticsThresholds
from infra.celery_factory import make_celery
from infra.celery_queue import CeleryReportQueue
from infra.configuration import ConfigurationError
from infra.database import build_engine, build_session_factory, ping
from infra.entitlements import CachedEntitlementsReader, HttpEntitlementsReader
from infra.report_csv import CsvReportRenderer

DEFAULT_TIME_ZONE = "America/Bogota"
DEFAULT_REDIS_URL = "redis://redis:6379/0"
DEFAULT_ENTITLEMENTS_URL = "http://subscription-service:8000"
DEFAULT_ENTITLEMENTS_TIMEOUT = "1"
DEFAULT_ENTITLEMENTS_CACHE_SECONDS = "30"
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


def _entitlements_reader(redis_url):
    """Derechos premium de subscription-service, con cache corta de los "si" (INV-06)."""
    inner = HttpEntitlementsReader(
        os.environ.get("ENTITLEMENTS_URL", DEFAULT_ENTITLEMENTS_URL),
        timeout=float(os.environ.get("ENTITLEMENTS_TIMEOUT", DEFAULT_ENTITLEMENTS_TIMEOUT)),
    )
    ttl = int(os.environ.get("ENTITLEMENTS_CACHE_SECONDS", DEFAULT_ENTITLEMENTS_CACHE_SECONDS))
    return CachedEntitlementsReader.from_url(inner, redis_url, ttl)


def create_app(session_factory=None, config=None, adapters=None):
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
    app.extensions.update(adapters or {})
    if ENTITLEMENTS_READER_KEY not in app.extensions:
        app.extensions[ENTITLEMENTS_READER_KEY] = _entitlements_reader(app.config["REDIS_URL"])
    app.extensions.setdefault(REPORT_RENDERER_KEY, CsvReportRenderer())
    if REPORT_QUEUE_KEY not in app.extensions:
        # Solo encola: el proceso web no ejecuta tareas (lo hace celery_app.py).
        app.extensions[REPORT_QUEUE_KEY] = CeleryReportQueue(make_celery())

    app.before_request(identify_user)
    app.before_request(enforce_entitlements)
    app.teardown_appcontext(close_db_session)
    register_error_handlers(app)

    app.register_blueprint(analytics_blueprint)
    app.register_blueprint(public_blueprint)
    app.add_url_rule("/health/", "health", health)
    app.cli.add_command(consume_events)
    return app
