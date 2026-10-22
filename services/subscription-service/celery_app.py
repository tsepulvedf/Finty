"""Punto de entrada de Celery en subscription-service (E2-M7).

    celery -A celery_app:celery worker -Q subscription   # contenedor subscription-worker
    celery -A celery_app:celery beat                     # contenedor subscription-beat

Un solo beat por servicio: lo garantiza Compose, con un unico contenedor de beat.
La convencion (broker, sin result backend, acks tardios, limites) esta en
`infra/celery_factory.py`. Los horarios van en la zona del proceso (`TIME_ZONE`).
"""
from celery.schedules import crontab

from app import create_app
from infra.celery_factory import make_celery

EXPIRE_EVERY_SECONDS = 15 * 60
MISSING_WELCOMES_EVERY_SECONDS = 15 * 60

flask_app = create_app()
celery = make_celery(flask_app)
celery.conf.beat_schedule = {
    # Cada dia a las 9:00 de Bogota: avisa las que terminan en 3 dias o menos.
    "notify-expiring-subscriptions": {
        "task": "subscription.notify_expiring_subscriptions",
        "schedule": crontab(hour=9, minute=0),
    },
    # Cada 15 minutos: la bienvenida que no se pudo encolar al activar (D-32).
    "send-missing-welcomes": {
        "task": "subscription.send_missing_welcomes",
        "schedule": MISSING_WELCOMES_EVERY_SECONDS,
    },
    # Cada 15 minutos: persiste EXPIRED en las vencidas (pendiente desde E2-M6b).
    "expire-subscriptions": {
        "task": "subscription.expire_subscriptions",
        "schedule": EXPIRE_EVERY_SECONDS,
    },
}

import tasks  # noqa: E402,F401 — registra las tareas en esta aplicacion
