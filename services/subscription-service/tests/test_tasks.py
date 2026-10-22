"""Tareas de Celery de subscription-service (E2-M7): convencion y ejecucion.

Corren en modo eager dentro del contexto de la aplicacion de pruebas. La
convencion de ADR-15 se verifica sobre la configuracion real.
"""
from datetime import timedelta

import pytest
from sqlalchemy.exc import OperationalError

from domain.interfaces import ContactUnavailable
from infra.celery_factory import QUEUE, celery_settings, make_celery
from models import SubscriptionRecord

CHECKOUT = "/api/v1/subscriptions/checkout/"
TASKS = (
    "subscription.send_premium_welcome",
    "subscription.send_missing_welcomes",
    "subscription.notify_expiring_subscriptions",
    "subscription.expire_subscriptions",
)


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

    def test_entrega_tardia_limites_y_cola_propia(self):
        settings = celery_settings(environ={})
        assert settings["task_acks_late"] and settings["task_reject_on_worker_lost"]
        assert settings["worker_prefetch_multiplier"] == 1
        assert 0 < settings["task_soft_time_limit"] < settings["task_time_limit"]
        assert settings["task_default_queue"] == QUEUE == "subscription"

    @pytest.mark.parametrize("name", TASKS)
    def test_reintentan_lo_transitorio_con_espera_creciente(self, worker, name):
        task = worker.tasks[name]
        assert {ContactUnavailable, OperationalError} <= set(task.autoretry_for)
        assert task.retry_backoff and task.retry_jitter and task.max_retries and task.acks_late

    def test_el_beat_programa_el_aviso_diario_y_el_vencimiento(self, monkeypatch):
        """`celery_app` arma la aplicacion real: se le da una base cualquiera."""
        import importlib
        import sys

        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://x:y@localhost:5432/nada")
        sys.modules.pop("celery_app", None)
        celery_app = importlib.import_module("celery_app")
        schedule = celery_app.celery.conf.beat_schedule
        assert schedule["notify-expiring-subscriptions"]["task"] == "subscription.notify_expiring_subscriptions"
        assert schedule["expire-subscriptions"]["task"] == "subscription.expire_subscriptions"
        assert schedule["send-missing-welcomes"] == {
            "task": "subscription.send_missing_welcomes", "schedule": 15 * 60,
        }
        sys.modules.pop("celery_app", None)


class TestEjecucion:
    def test_bienvenida_por_la_tarea(self, ana, worker, adapters, session):
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        [subscription_id] = adapters["queue"].welcomes

        result = worker.tasks["subscription.send_premium_welcome"].apply(args=[str(subscription_id)])

        assert result.get() == "sent"
        assert len(adapters["sender"].sent) == 1
        assert worker.tasks["subscription.send_premium_welcome"].apply(args=[str(subscription_id)]).get() == "already_sent"

    def test_aviso_y_vencimiento_por_las_tareas(self, ana, worker, adapters, session):
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        end = session.query(SubscriptionRecord).filter_by(user_id=ana.user_id).one().current_period_end

        adapters["clock"].now = end - timedelta(days=3)
        assert worker.tasks["subscription.notify_expiring_subscriptions"].apply().get() == 1
        assert worker.tasks["subscription.notify_expiring_subscriptions"].apply().get() == 0

        adapters["clock"].now = end + timedelta(minutes=1)
        assert worker.tasks["subscription.expire_subscriptions"].apply().get() == 1
        session.expire_all()
        assert session.query(SubscriptionRecord).filter_by(user_id=ana.user_id).one().status == "EXPIRED"
