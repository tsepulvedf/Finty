"""Tareas de Celery de analytics (E2-M7): convencion de ADR-15 y ejecucion.

Las tareas corren en modo eager, dentro del contexto de la aplicacion de
pruebas, con la misma base que los demas tests. La convencion (sin result
backend, acks tardios, limites, cola propia, broker en otra base de Redis) se
verifica sobre la configuracion real.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import OperationalError

from domain.period import Period
from infra.celery_factory import QUEUE, celery_settings, make_celery
from models import MonthlyReportRecord

REPORTS = "/api/v1/analytics/reports/"
CURRENT = Period.of(date.today())


@pytest.fixture
def worker(app):
    celery = make_celery(app, {"task_always_eager": True, "task_eager_propagates": True, "broker_url": "memory://"})
    import tasks  # noqa: F401 — registra las tareas compartidas

    celery.finalize()
    return celery


class TestConvencion:
    def test_broker_en_la_base_1_y_sin_result_backend(self):
        settings = celery_settings(environ={})
        assert settings["broker_url"] == "redis://redis:6379/1"
        assert settings["result_backend"] is None and settings["task_ignore_result"] is True

    def test_entrega_tardia_y_de_a_una(self):
        settings = celery_settings(environ={})
        assert settings["task_acks_late"] and settings["task_reject_on_worker_lost"]
        assert settings["worker_prefetch_multiplier"] == 1

    def test_tiempo_limite(self):
        settings = celery_settings(environ={})
        assert 0 < settings["task_soft_time_limit"] < settings["task_time_limit"]

    def test_cola_propia(self):
        assert celery_settings(environ={})["task_default_queue"] == QUEUE == "analytics"

    def test_cada_tarea_reintenta_lo_transitorio_con_espera_creciente(self, worker):
        for name in ("analytics.generate_monthly_report", "analytics.requeue_pending_reports",
                     "analytics.purge_expired_reports"):
            task = worker.tasks[name]
            assert OperationalError in task.autoretry_for
            assert task.retry_backoff and task.retry_jitter and task.max_retries
            assert task.acks_late


class TestEjecucion:
    def test_la_tarea_genera_el_reporte(self, ana, worker, session):
        report_id = ana.post(REPORTS, {"period": str(CURRENT)}).json["id"]

        result = worker.tasks["analytics.generate_monthly_report"].apply(args=[report_id])

        assert result.get() == "READY"
        assert session.get(MonthlyReportRecord, report_id).status == "READY"
        assert ana.get(f"{REPORTS}{report_id}/").json["status"] == "READY"

    def test_entregar_dos_veces_es_idempotente(self, ana, worker):
        report_id = ana.post(REPORTS, {"period": str(CURRENT)}).json["id"]
        task = worker.tasks["analytics.generate_monthly_report"]
        assert task.apply(args=[report_id]).get() == "READY"
        assert task.apply(args=[report_id]).get() == "READY"

    def test_reencolar_por_la_tarea_periodica(self, worker):
        assert worker.tasks["analytics.requeue_pending_reports"].apply().get() == 0

    def test_limpieza_por_la_tarea_periodica(self, ana, worker, session):
        report_id = ana.post(REPORTS, {"period": str(CURRENT)}).json["id"]
        record = session.get(MonthlyReportRecord, report_id)
        record.created_at = record.created_at - timedelta(days=8)
        session.commit()

        assert worker.tasks["analytics.purge_expired_reports"].apply().get() == 1
        assert ana.get(f"{REPORTS}{report_id}/").status_code == 404


class TestBeat:
    def test_programa_el_reencolado_y_la_limpieza_diaria(self, monkeypatch):
        """`celery_app` arma la aplicacion real: se le da una base cualquiera."""
        import importlib
        import sys

        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://x:y@localhost:5432/nada")
        sys.modules.pop("celery_app", None)
        celery_app = importlib.import_module("celery_app")
        schedule = celery_app.celery.conf.beat_schedule
        sys.modules.pop("celery_app", None)
        assert schedule["requeue-pending-reports"]["task"] == "analytics.requeue_pending_reports"
        purge = schedule["purge-expired-reports"]
        assert purge["task"] == "analytics.purge_expired_reports"
        assert (purge["schedule"].hour, purge["schedule"].minute) == ({3}, {30})
