"""Adaptador de `NotificationQueue` sobre Celery: encola por nombre de tarea.

`send_task` no importa el modulo de tareas. `retry=False`: si el broker no
responde, el checkout no se queda esperando (la activacion nunca depende de las
notificaciones); el servicio registra el fallo y sigue.
"""
from domain.interfaces import NotificationQueue
from infra.celery_factory import QUEUE

SEND_PREMIUM_WELCOME_TASK = "subscription.send_premium_welcome"


class CeleryNotificationQueue(NotificationQueue):
    def __init__(self, celery_app):
        self._celery = celery_app

    def premium_activated(self, subscription_id):
        self._celery.send_task(SEND_PREMIUM_WELCOME_TASK, args=[str(subscription_id)], queue=QUEUE, retry=False)
