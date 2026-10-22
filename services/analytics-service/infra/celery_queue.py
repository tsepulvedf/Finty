"""Adaptador de `ReportQueue` sobre Celery: encola por nombre de tarea.

`send_task` no importa el modulo de tareas, asi el proceso web no carga nada del
worker. `retry=False`: si el broker no responde, la peticion no se queda
esperando; el reporte sigue PENDING y la tarea periodica lo vuelve a encolar.
"""
from domain.interfaces import ReportQueue
from infra.celery_factory import QUEUE

GENERATE_REPORT_TASK = "analytics.generate_monthly_report"


class CeleryReportQueue(ReportQueue):
    def __init__(self, celery_app):
        self._celery = celery_app

    def enqueue(self, report_id):
        self._celery.send_task(GENERATE_REPORT_TASK, args=[str(report_id)], queue=QUEUE, retry=False)
