"""La aplicacion de Celery de analytics-service, con la convencion de ADR-15.

- **Broker:** Redis, en la base logica 1 (`CELERY_BROKER_URL`, por defecto
  `redis://redis:6379/1`). La base 0 queda para el stream de eventos y las
  caches de derechos y tasas.
- **Sin result backend:** el estado que consulta el usuario vive en la base del
  servicio (`monthly_report.status`), no en Celery.
- **Cola propia** (`analytics`): el broker lo comparte con subscription-service,
  y cada worker consume solo la cola de su servicio.
- **Entrega:** `acks_late` con `reject_on_worker_lost`, de a una tarea por
  worker (`prefetch_multiplier = 1`): si el worker muere a mitad de una tarea, la
  tarea vuelve a la cola. Por eso toda tarea es idempotente.
- **Tiempo limite:** `soft_time_limit` de 60 s y `time_limit` de 90 s por defecto.
- **Reintentos:** cada tarea declara sus errores transitorios con espera
  creciente (`retry_backoff`), con tope y con jitter.

La aplicacion web usa la misma configuracion solo para encolar
(`infra/celery_queue.py`). El worker ejecuta cada tarea dentro del contexto de la
aplicacion Flask, para que use la misma sesion de base que una peticion.
"""
import os

from celery import Celery, Task

DEFAULT_BROKER_URL = "redis://redis:6379/1"
QUEUE = "analytics"


def celery_settings(environ=os.environ, time_zone="America/Bogota"):
    return {
        "broker_url": environ.get("CELERY_BROKER_URL", DEFAULT_BROKER_URL),
        "result_backend": None,
        "task_ignore_result": True,
        "task_default_queue": QUEUE,
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        "worker_prefetch_multiplier": 1,
        "task_soft_time_limit": int(environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "60")),
        "task_time_limit": int(environ.get("CELERY_TASK_TIME_LIMIT", "90")),
        "timezone": time_zone,
        "enable_utc": True,
        "broker_connection_retry_on_startup": True,
        # Encolar desde la web no espera al broker mas de unos segundos.
        "broker_connection_timeout": 3,
        "broker_transport_options": {"socket_connect_timeout": 3, "socket_timeout": 5},
        "worker_hijack_root_logger": False,
    }


def make_celery(flask_app=None, overrides=None):
    """Celery configurado; con `flask_app`, cada tarea corre en su contexto."""
    time_zone = flask_app.config["TIME_ZONE"] if flask_app is not None else "America/Bogota"
    app = Celery("analytics")
    app.conf.update(celery_settings(time_zone=time_zone))
    app.conf.update(overrides or {})

    if flask_app is not None:
        class FlaskTask(Task):
            def __call__(self, *args, **kwargs):
                with flask_app.app_context():
                    return super().__call__(*args, **kwargs)

        app.Task = FlaskTask
    return app
