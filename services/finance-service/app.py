"""Fabrica de la aplicacion Flask de `finance-service`.

    gunicorn "app:create_app()"

Configuracion por entorno:
- `DATABASE_URL` (obligatoria): URL de `finty_finance`, y solo de ella (A-21).
- `CATEGORIZATION_URL` (obligatoria): URL interna de `categorization-service`.
- `CATEGORIZATION_TIMEOUT_SECONDS` (opcional, `1.0`): espera maxima por el remoto
  antes de clasificar con el respaldo local (A-22).
- `REDIS_URL` (opcional, `redis://redis:6379/0`): Redis donde `flask relay-outbox`
  publica los eventos de dominio (ADR-15). El proceso web no lo usa.
- `TIME_ZONE` (opcional, `America/Bogota`): zona de los instantes de salida y
  del proceso (el "hoy" de INV-12), la misma de `settings.py` en el monolito.

Comandos (`commands.py`): `flask verify-invariants`, `flask relay-outbox` y
`flask outbox-backfill`.
"""
import os
import time

from flask import Flask, jsonify

from api.context import (
    SESSION_FACTORY_KEY,
    close_db_session,
    db_session,
    identify_user,
)
from api.converters import CONVERTERS
from api.errors import register_error_handlers
from api.routes import blueprint as finance_blueprint
from commands import outbox_backfill, relay_outbox, verify_invariants
from infra.database import build_engine, build_session_factory, ping
from infra.categorization_client import DEFAULT_TIMEOUT_SECONDS
from infra.configuration import ConfigurationError

DEFAULT_TIME_ZONE = "America/Bogota"
DEFAULT_REDIS_URL = "redis://redis:6379/0"


def health():
    """Sonda de salud para Docker: el proceso responde y la base tambien.

    Fuera de `/api/v1/` y sin identidad: no es parte del contrato y Nginx no la
    enruta.
    """
    ping(db_session())
    return jsonify({"status": "ok"})


def _set_process_time_zone(time_zone):
    """Fija la zona horaria del proceso, como hace Django con `TIME_ZONE`.

    El dominio decide "hoy" con `date.today()` (INV-12: fecha no futura), que usa
    la zona del proceso. El contenedor corre en UTC: sin esto, desde las 19:00 de
    Bogota el servicio aceptaria como de hoy una fecha que alla es de manana, y
    el monolito no lo hacia. `time.tzset` solo existe en POSIX; en Windows el
    proceso conserva la zona del sistema.
    """
    os.environ["TZ"] = time_zone
    if hasattr(time, "tzset"):
        time.tzset()


def _session_factory_from_environment():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ConfigurationError(
            "Falta la variable de entorno obligatoria 'DATABASE_URL' con la URL "
            "de la base finty_finance."
        )
    return build_session_factory(build_engine(database_url))


def create_app(session_factory=None, config=None):
    """Construye la aplicacion.

    `session_factory` permite a los tests inyectar sesiones atadas a una
    transaccion que se revierte al final de cada test, y `config` sobrescribir
    la configuracion que se lee del entorno.
    """
    app = Flask(__name__)
    app.config["TIME_ZONE"] = os.environ.get("TIME_ZONE", DEFAULT_TIME_ZONE)
    app.config["CATEGORIZATION_URL"] = os.environ.get("CATEGORIZATION_URL")
    app.config["CATEGORIZATION_TIMEOUT_SECONDS"] = float(
        os.environ.get("CATEGORIZATION_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    )
    app.config["REDIS_URL"] = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
    app.config.update(config or {})
    if not app.config["CATEGORIZATION_URL"]:
        raise ConfigurationError(
            "Falta la variable de entorno obligatoria 'CATEGORIZATION_URL' con la "
            "URL interna de categorization-service."
        )
    _set_process_time_zone(app.config["TIME_ZONE"])

    # Mismo JSON que el renderer de DRF: compacto, en UTF-8 y sin reordenar los
    # campos (el orden de los serializers es parte del contrato).
    app.json.compact = True
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    app.url_map.converters.update(CONVERTERS)

    app.extensions[SESSION_FACTORY_KEY] = (
        session_factory or _session_factory_from_environment()
    )

    app.before_request(identify_user)
    app.teardown_appcontext(close_db_session)
    register_error_handlers(app)

    app.register_blueprint(finance_blueprint)
    app.add_url_rule("/health/", "health", health)
    app.cli.add_command(verify_invariants)
    app.cli.add_command(relay_outbox)
    app.cli.add_command(outbox_backfill)
    return app
