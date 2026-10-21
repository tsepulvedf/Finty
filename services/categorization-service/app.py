"""Fabrica de la aplicacion Flask de `categorization-service`.

    gunicorn "app:create_app()"

Configuracion por entorno, sin secretos (por eso Compose la pasa con
`environment:` y no con un `env_file`):
- `CATEGORIZER_PROVIDER` (opcional, `RULE` por defecto): ver `infra/factories.py`.
- `TIME_ZONE` (opcional, `America/Bogota`): zona del proceso, como en todos los
  servicios Flask (RULES.md).
"""
import os
import time

from flask import Flask, jsonify

from api.errors import register_error_handlers
from api.routes import blueprint as categorization_blueprint

DEFAULT_TIME_ZONE = "America/Bogota"


def health():
    """Sonda de salud para Docker. Sin base de datos, basta con que responda."""
    return jsonify({"status": "ok"})


def _set_process_time_zone(time_zone):
    """Fija la zona horaria del proceso, como hace Django con `TIME_ZONE`.

    Regla comun a los servicios Flask (RULES.md): cualquier "hoy" del dominio
    usa la zona del proceso, y el contenedor corre en UTC. `time.tzset` solo
    existe en POSIX.
    """
    os.environ["TZ"] = time_zone
    if hasattr(time, "tzset"):
        time.tzset()


def create_app():
    """Construye la aplicacion."""
    app = Flask(__name__)
    app.config["TIME_ZONE"] = os.environ.get("TIME_ZONE", DEFAULT_TIME_ZONE)
    _set_process_time_zone(app.config["TIME_ZONE"])

    app.json.compact = True
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    register_error_handlers(app)
    app.register_blueprint(categorization_blueprint)
    app.add_url_rule("/health/", "health", health)
    return app
