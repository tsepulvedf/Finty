"""Fabrica de la aplicacion Flask de `subscription-service`.

    gunicorn "app:create_app()"

Configuracion por entorno:
- `DATABASE_URL` (obligatoria): URL de `finty_subscription`, y solo de ella (A-21).
- `PAYMENT_GATEWAY` (opcional, `MOCK`): pasarela de `PaymentGatewayFactory`. Un
  valor desconocido impide arrancar (ADR-14).
- `SUBSCRIPTION_PREMIUM_PRICE_IN_CENTS` (opcional, `2990000`: 29 900 COP al mes).
- `TIME_ZONE` (opcional, `America/Bogota`): zona del proceso (RULES.md).
- E2-M7 (correos y Celery): `CELERY_BROKER_URL` (`redis://redis:6379/1`),
  `IDENTITY_URL` (`http://django:8000`, de donde sale el contacto),
  `EMAIL_BACKEND` (`console` o `file`; con `file`, `EMAIL_FILE_DIR`) y
  `NOTIFY_DAYS_BEFORE_EXPIRY` (`3`).

    celery -A celery_app:celery worker -Q subscription   # contenedor subscription-worker
    celery -A celery_app:celery beat                     # contenedor subscription-beat
"""
import os
import time
from datetime import datetime, timezone

from flask import Flask, jsonify

from api.context import (
    CLOCK_KEY,
    CONTACTS_KEY,
    EMAIL_COMPOSER_KEY,
    EMAIL_SENDER_KEY,
    GATEWAY_KEY,
    NOTIFICATION_QUEUE_KEY,
    SESSION_FACTORY_KEY,
    close_db_session,
    db_session,
    identify_user,
)
from api.errors import register_error_handlers
from api.routes import internal, subscriptions
from domain.notifications import DEFAULT_DAYS_BEFORE_EXPIRY
from domain.plans import DEFAULT_PREMIUM_PRICE_IN_CENTS, plan_catalog
from infra.celery_factory import make_celery
from infra.celery_queue import CeleryNotificationQueue
from infra.configuration import ConfigurationError
from infra.contacts import HttpContactDirectory
from infra.database import build_engine, build_session_factory, ping
from infra.email import email_sender_from_environment
from infra.email_templates import TemplateEmailComposer
from infra.factories import PaymentGatewayFactory

DEFAULT_TIME_ZONE = "America/Bogota"
DEFAULT_IDENTITY_URL = "http://django:8000"


def health():
    ping(db_session())
    return jsonify({"status": "ok"})


def _set_process_time_zone(time_zone):
    """Zona horaria del proceso, como en todos los servicios Flask (RULES.md)."""
    os.environ["TZ"] = time_zone
    if hasattr(time, "tzset"):
        time.tzset()


def _utcnow():
    return datetime.now(timezone.utc)


def _session_factory_from_environment():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ConfigurationError(
            "Falta la variable de entorno obligatoria 'DATABASE_URL' con la URL de "
            "la base finty_subscription."
        )
    return build_session_factory(build_engine(database_url))


def create_app(session_factory=None, config=None, adapters=None):
    app = Flask(__name__, static_folder=None)
    app.config["TIME_ZONE"] = os.environ.get("TIME_ZONE", DEFAULT_TIME_ZONE)
    price = int(os.environ.get("SUBSCRIPTION_PREMIUM_PRICE_IN_CENTS", DEFAULT_PREMIUM_PRICE_IN_CENTS))
    app.config["SUBSCRIPTION_PLANS"] = plan_catalog(price)
    app.config["NOTIFY_DAYS_BEFORE_EXPIRY"] = int(
        os.environ.get("NOTIFY_DAYS_BEFORE_EXPIRY", DEFAULT_DAYS_BEFORE_EXPIRY)
    )
    app.config.update(config or {})
    _set_process_time_zone(app.config["TIME_ZONE"])

    app.json.compact = True
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    app.extensions[SESSION_FACTORY_KEY] = session_factory or _session_factory_from_environment()
    app.extensions.update(adapters or {})
    if GATEWAY_KEY not in app.extensions:
        # Falla aqui, al arrancar, si PAYMENT_GATEWAY no es valido.
        app.extensions[GATEWAY_KEY] = PaymentGatewayFactory.get_gateway()
    app.extensions.setdefault(CLOCK_KEY, _utcnow)
    if NOTIFICATION_QUEUE_KEY not in app.extensions:
        # Solo encola: el proceso web no ejecuta tareas (lo hace celery_app.py).
        app.extensions[NOTIFICATION_QUEUE_KEY] = CeleryNotificationQueue(make_celery())
    if CONTACTS_KEY not in app.extensions:
        app.extensions[CONTACTS_KEY] = HttpContactDirectory(os.environ.get("IDENTITY_URL", DEFAULT_IDENTITY_URL))
    app.extensions.setdefault(EMAIL_COMPOSER_KEY, TemplateEmailComposer())
    if EMAIL_SENDER_KEY not in app.extensions:
        # Falla aqui, al arrancar, si EMAIL_BACKEND no es valido.
        app.extensions[EMAIL_SENDER_KEY] = email_sender_from_environment()

    app.before_request(identify_user)
    app.teardown_appcontext(close_db_session)
    register_error_handlers(app)

    app.register_blueprint(subscriptions)
    app.register_blueprint(internal)
    app.add_url_rule("/health/", "health", health)
    return app
