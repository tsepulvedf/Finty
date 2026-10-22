"""Punto de entrada de Celery en analytics-service (E2-M7).

    celery -A celery_app:celery worker -Q analytics      # contenedor analytics-celery
    celery -A celery_app:celery beat                     # contenedor analytics-celery-beat

Un solo beat por servicio: lo garantiza Compose, con un unico contenedor de beat.
La convencion (broker, sin result backend, acks tardios, limites) esta en
`infra/celery_factory.py`.
"""
from app import create_app
from infra.celery_factory import make_celery

REQUEUE_EVERY_SECONDS = 120

flask_app = create_app()
celery = make_celery(flask_app)
celery.conf.beat_schedule = {
    "requeue-pending-reports": {
        "task": "analytics.requeue_pending_reports",
        "schedule": REQUEUE_EVERY_SECONDS,
    },
}

import tasks  # noqa: E402,F401 — registra las tareas en esta aplicacion
