"""Tareas de Celery de subscription-service (E2-M7, ADR-15).

Son un mecanismo de entrega, como un blueprint: reciben el mensaje, arman el
caso de uso y lo llaman. No consultan la base ni tocan el dominio (lo verifica
`tests/test_architecture.py`).

- `subscription.send_premium_welcome`: se encola al activar una suscripcion.
- `subscription.send_missing_welcomes`: periodica (beat, cada 15 minutos); red
  de seguridad para la bienvenida que no se pudo encolar (D-32).
- `subscription.notify_expiring_subscriptions`: diaria (beat); avisa 3 dias
  antes del fin del periodo.
- `subscription.expire_subscriptions`: periodica (beat); persiste EXPIRED.

Todas son idempotentes. Si identity o la base no responden, reintentan con
espera creciente.
"""
from uuid import UUID

from celery import shared_task

from api.context import notification_service, subscription_service
from services import TRANSIENT_ERRORS

RETRY_POLICY = {
    "autoretry_for": TRANSIENT_ERRORS,
    "retry_backoff": 5,
    "retry_backoff_max": 300,
    "retry_jitter": True,
    "max_retries": 8,
}


@shared_task(name="subscription.send_premium_welcome", acks_late=True, **RETRY_POLICY)
def send_premium_welcome(subscription_id):
    return notification_service().send_premium_welcome(UUID(subscription_id))


@shared_task(name="subscription.send_missing_welcomes", acks_late=True, **RETRY_POLICY)
def send_missing_welcomes():
    return notification_service().send_missing_welcomes()


@shared_task(name="subscription.notify_expiring_subscriptions", acks_late=True, **RETRY_POLICY)
def notify_expiring_subscriptions():
    return notification_service().notify_expiring()


@shared_task(name="subscription.expire_subscriptions", acks_late=True, **RETRY_POLICY)
def expire_subscriptions():
    return subscription_service().expire_all()
