"""Tareas de Celery de analytics-service (E2-M7, ADR-15).

Son un mecanismo de entrega, como `commands.py` o un blueprint: reciben el
mensaje, arman el caso de uso y lo llaman. No consultan la base ni tocan el
dominio (lo verifica `tests/test_architecture.py`).

- `analytics.generate_monthly_report`: genera un reporte PENDING. Idempotente.
- `analytics.requeue_pending_reports`: periodica (beat, cada
  `REPORT_REQUEUE_EVERY_SECONDS`); vuelve a encolar los PENDING con mas de
  `REPORT_STALE_AFTER_SECONDS` que quedaron sin tarea.
- `analytics.purge_expired_reports`: diaria (beat); borra los reportes de mas
  de `REPORT_RETENTION_DAYS` dias (D-33).

Ante un error transitorio (la base no responde) reintentan con espera creciente;
el reporte sigue PENDING mientras tanto.
"""
from uuid import UUID

from celery import shared_task

from api.context import report_service
from services import TRANSIENT_ERRORS

RETRY_POLICY = {
    "autoretry_for": TRANSIENT_ERRORS,
    "retry_backoff": 2,
    "retry_backoff_max": 60,
    "retry_jitter": True,
    "max_retries": 6,
}


@shared_task(name="analytics.generate_monthly_report", acks_late=True, **RETRY_POLICY)
def generate_monthly_report(report_id):
    return report_service().generate(UUID(report_id))


@shared_task(name="analytics.requeue_pending_reports", acks_late=True, **RETRY_POLICY)
def requeue_pending_reports():
    return report_service().requeue_stale()


@shared_task(name="analytics.purge_expired_reports", acks_late=True, **RETRY_POLICY)
def purge_expired_reports():
    return report_service().purge_expired()
