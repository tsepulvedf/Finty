"""Fabrica de la aplicacion Flask de `subscription-service`.

    gunicorn "app:create_app()"

Configuracion por entorno:
- `DATABASE_URL` (obligatoria): URL de `finty_subscription`, y solo de ella (A-21).
- `PAYMENT_GATEWAY` (opcional, `MOCK`): pasarela de `PaymentGatewayFactory`. Un
  valor desconocido impide arrancar (ADR-14).
- `SUBSCRIPTION_PREMIUM_PRICE_IN_CENTS` (opcional, `2990000`: 29 900 COP al mes).
- `TIME_ZONE` (opcional, `America/Bogota`): zona del proceso (RULES.md).
"""
import os
import time
from datetime import datetime, timezone

from flask import Flask, jsonify

from api.context import (
    CLOCK_KEY,
    GATEWAY_KEY,
    SESSION_FACTORY_KEY,
    close_db_session,
    db_session,
    identify_user,
)
from api.errors import register_error_handlers
from api.routes import internal, subscriptions
from domain.plans import DEFAULT_PREMIUM_PRICE_IN_CENTS, plan_catalog
from infra.configuration import ConfigurationError
from infra.database import build_engine, build_session_factory, ping
from infra.factories import PaymentGatewayFactory

DEFAULT_TIME_ZONE = "America/Bogota"


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

    app.before_request(identify_user)
    app.teardown_appcontext(close_db_session)
    register_error_handlers(app)

    app.register_blueprint(subscriptions)
    app.register_blueprint(internal)
    app.add_url_rule("/health/", "health", health)
    return app
