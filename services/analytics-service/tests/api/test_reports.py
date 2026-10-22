"""Reporte mensual asincrono por la API y por la tarea de Celery (E2-M7)."""
import csv
import io
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from domain.period import Period
from infra.report_csv import CsvReportRenderer
from models import MonthlyReportRecord
from services import EventProjector, ReportService
from tests.report_doubles import BrokenRenderer
from tests.streams import Transaction, event

REPORTS = "/api/v1/analytics/reports/"
CURRENT = Period.of(date.today())


def status_url(report_id):
    return f"{REPORTS}{report_id}/"


def download_url(report_id):
    return f"{REPORTS}{report_id}/download/"


def feed(session, user_id, *transactions):
    projector = EventProjector(session)
    for i, kwargs in enumerate(transactions):
        projector.project(event(Transaction(user_id=user_id, **kwargs).added()), f"{i}-0")


def generate(session, report_id, renderer=None):
    return ReportService(session, renderer or CsvReportRenderer()).generate(report_id)


def csv_rows(content):
    return list(csv.reader(io.StringIO(content.decode("utf-8").lstrip("﻿"))))


class TestPedir:
    def test_responde_202_pending_y_encola(self, ana, report_queue):
        response = ana.post(REPORTS, {"period": str(CURRENT)})

        assert response.status_code == 202
        body = response.json
        assert (body["status"], body["period"], body["language"]) == ("PENDING", str(CURRENT), "es")
        assert body["download_url"] is None and body["filename"] is None
        assert [str(i) for i in report_queue.enqueued] == [body["id"]]

    @pytest.mark.parametrize("header, idioma", [("en-US,en;q=0.9", "en"), ("es-CO", "es"), ("fr", "es"), (None, "es")])
    def test_el_idioma_sale_de_accept_language(self, ana, header, idioma):
        headers = {"Accept-Language": header} if header else {}
        assert ana.post(REPORTS, {"period": str(CURRENT)}, headers=headers).json["language"] == idioma

    @pytest.mark.parametrize("payload", [None, {}, {"period": ""}, {"period": 202610}, ["2026-10"]])
    def test_sin_periodo_400(self, ana, payload):
        response = ana.post(REPORTS, payload)
        assert response.status_code == 400
        assert response.json == {"period": ["Este campo es requerido."]}

    def test_periodo_invalido_400(self, ana):
        response = ana.post(REPORTS, {"period": "2026-13"})
        assert response.status_code == 400 and "period" in response.json

    def test_sin_identidad_401(self, anonimo):
        assert anonimo.post(REPORTS, {"period": str(CURRENT)}).status_code == 401

    def test_broker_caido_no_tumba_la_peticion(self, ana, report_queue, session):
        report_queue.down = True
        response = ana.post(REPORTS, {"period": str(CURRENT)})

        assert response.status_code == 202 and response.json["status"] == "PENDING"
        assert session.get(MonthlyReportRecord, response.json["id"]).status == "PENDING"


class TestVentanaFree:
    @pytest.fixture(autouse=True)
    def free(self, entitlements):
        entitlements.premium = False

    @pytest.mark.parametrize("offset", [0, -1, -2])
    def test_dentro_de_los_3_meses(self, ana, offset):
        assert ana.post(REPORTS, {"period": str(CURRENT.shift(offset))}).status_code == 202

    def test_fuera_de_la_ventana_403(self, ana, report_queue):
        response = ana.post(REPORTS, {"period": str(CURRENT.shift(-3))})
        assert response.status_code == 403
        assert response.json["error"]["code"] == "premium_required"
        assert report_queue.enqueued == []

    def test_premium_pide_cualquier_mes(self, ana, entitlements):
        entitlements.premium = True
        assert ana.post(REPORTS, {"period": str(CURRENT.shift(-12))}).status_code == 202

    def test_sin_subscription_service_dentro_de_la_ventana_sigue(self, ana, entitlements):
        entitlements.down = True
        assert ana.post(REPORTS, {"period": str(CURRENT)}).status_code == 202

    def test_sin_subscription_service_fuera_de_la_ventana_503(self, ana, entitlements):
        entitlements.down = True
        response = ana.post(REPORTS, {"period": str(CURRENT.shift(-3))})
        assert response.status_code == 503
        assert response.json["error"]["code"] == "entitlements_unavailable"


class TestEstadoYDescarga:
    def test_pending_ready_y_descarga(self, ana, session):
        feed(session, ana.user_id,
             {"amount": "38000.00", "on": CURRENT.start, "description": "Almuerzo"},
             {"amount": "3100000.00", "kind": "income", "category": "Salario", "on": CURRENT.start})
        report_id = ana.post(REPORTS, {"period": str(CURRENT)}).json["id"]
        assert ana.get(status_url(report_id)).json["status"] == "PENDING"
        assert ana.get(download_url(report_id)).status_code == 409

        assert generate(session, report_id) == "READY"

        body = ana.get(status_url(report_id)).json
        assert body["status"] == "READY"
        assert body["filename"] == f"finty-reporte-{CURRENT}.csv"
        assert body["download_url"] == f"/api/v1/analytics/reports/{report_id}/download/"
        response = ana.get(download_url(report_id))
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
        assert response.headers["Content-Disposition"] == f'attachment; filename="finty-reporte-{CURRENT}.csv"'
        rows = csv_rows(response.data)
        assert rows[1] == ["Fecha", "Tipo", "Categoría", "Descripción", "Monto", "Moneda"]
        assert len([r for r in rows[2:] if r and r[0].startswith(str(CURRENT))]) == 2

    def test_en_ingles(self, ana, session):
        feed(session, ana.user_id, {"amount": "1000.00", "on": CURRENT.start})
        report_id = ana.post(REPORTS, {"period": str(CURRENT)}, headers={"Accept-Language": "en"}).json["id"]
        generate(session, report_id)

        response = ana.get(download_url(report_id))
        assert csv_rows(response.data)[1] == ["Date", "Type", "Category", "Description", "Amount", "Currency"]
        assert f"finty-report-{CURRENT}.csv" in response.headers["Content-Disposition"]

    def test_solo_movimientos_del_dueno_y_del_periodo(self, ana, juan, session):
        feed(session, ana.user_id, {"amount": "1.00", "on": CURRENT.start}, {"amount": "2.00", "on": CURRENT.shift(-1).start})
        feed(session, juan.user_id, {"amount": "3.00", "on": CURRENT.start})
        report_id = ana.post(REPORTS, {"period": str(CURRENT)}).json["id"]
        generate(session, report_id)

        amounts = [row[4] for row in csv_rows(ana.get(download_url(report_id)).data)[2:] if len(row) == 6]
        assert amounts == ["1.00"]

    def test_el_reporte_de_otro_usuario_es_404(self, ana, juan, session):
        report_id = ana.post(REPORTS, {"period": str(CURRENT)}).json["id"]
        generate(session, report_id)

        for url in (status_url(report_id), download_url(report_id)):
            response = juan.get(url)
            assert response.status_code == 404
            assert response.json["error"]["code"] == "report_not_found"

    def test_id_inexistente_o_mal_formado_404(self, ana):
        assert ana.get(status_url(uuid4())).status_code == 404
        assert ana.get(f"{REPORTS}no-es-un-uuid/").status_code == 404

    def test_un_reporte_que_no_se_puede_armar_queda_failed(self, ana, session):
        report_id = ana.post(REPORTS, {"period": str(CURRENT)}).json["id"]

        assert generate(session, report_id, BrokenRenderer()) == "FAILED"
        assert ana.get(status_url(report_id)).json["status"] == "FAILED"
        response = ana.get(download_url(report_id))
        assert response.status_code == 409 and response.json["error"]["code"] == "report_not_ready"


class TestIdempotencia:
    def test_generar_dos_veces_no_cambia_el_archivo(self, ana, session):
        feed(session, ana.user_id, {"amount": "10.00", "on": CURRENT.start})
        report_id = ana.post(REPORTS, {"period": str(CURRENT)}).json["id"]
        generate(session, report_id)
        first = session.get(MonthlyReportRecord, report_id)
        content, completed = first.content, first.completed_at

        feed(session, ana.user_id, {"amount": "99.00", "on": CURRENT.start})
        assert generate(session, report_id) == "READY"
        again = session.get(MonthlyReportRecord, report_id)
        assert (again.content, again.completed_at) == (content, completed)

    def test_un_id_que_no_existe_no_falla(self, session):
        assert generate(session, uuid4()) is None


class TestReencolar:
    def test_reencola_solo_los_pendientes_viejos(self, session, report_queue):
        now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
        viejo = MonthlyReportRecord(user_id=uuid4(), period="2026-10", language="es", status="PENDING",
                                    created_at=now - timedelta(minutes=5))
        reciente = MonthlyReportRecord(user_id=uuid4(), period="2026-10", language="es", status="PENDING",
                                       created_at=now - timedelta(seconds=30))
        listo = MonthlyReportRecord(user_id=uuid4(), period="2026-10", language="es", status="READY",
                                    content=b"x", created_at=now - timedelta(minutes=5))
        session.add_all([viejo, reciente, listo])
        session.commit()

        service = ReportService(session, CsvReportRenderer(), report_queue, clock=lambda: now)
        assert service.requeue_stale() == 1
        assert report_queue.enqueued == [viejo.id]

    def test_por_defecto_toma_los_de_mas_de_un_minuto(self, session, report_queue):
        now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
        pasado = MonthlyReportRecord(user_id=uuid4(), period="2026-10", language="es", status="PENDING",
                                     created_at=now - timedelta(seconds=61))
        justo = MonthlyReportRecord(user_id=uuid4(), period="2026-10", language="es", status="PENDING",
                                    created_at=now - timedelta(seconds=60))
        session.add_all([pasado, justo])
        session.commit()

        service = ReportService(session, CsvReportRenderer(), report_queue, clock=lambda: now)
        assert service.requeue_stale() == 1
        assert report_queue.enqueued == [pasado.id]

    def test_el_umbral_es_configurable(self, session, report_queue):
        now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
        record = MonthlyReportRecord(user_id=uuid4(), period="2026-10", language="es", status="PENDING",
                                     created_at=now - timedelta(seconds=90))
        session.add(record)
        session.commit()

        tolerante = ReportService(session, CsvReportRenderer(), report_queue, clock=lambda: now,
                                  stale_after_seconds=120)
        assert tolerante.requeue_stale() == 0
        estricto = ReportService(session, CsvReportRenderer(), report_queue, clock=lambda: now,
                                 stale_after_seconds=30)
        assert estricto.requeue_stale() == 1

    def test_la_aplicacion_lee_los_intervalos_del_entorno(self, monkeypatch, connection):
        from app import create_app
        from tests.conftest import _session_on

        app = create_app(session_factory=lambda: _session_on(connection))
        assert (app.config["REPORT_REQUEUE_EVERY_SECONDS"], app.config["REPORT_STALE_AFTER_SECONDS"]) == (60, 60)
        monkeypatch.setenv("REPORT_REQUEUE_EVERY_SECONDS", "30")
        monkeypatch.setenv("REPORT_STALE_AFTER_SECONDS", "45")
        app = create_app(session_factory=lambda: _session_on(connection))
        assert (app.config["REPORT_REQUEUE_EVERY_SECONDS"], app.config["REPORT_STALE_AFTER_SECONDS"]) == (30, 45)

    @pytest.mark.parametrize("name", ["REPORT_REQUEUE_EVERY_SECONDS", "REPORT_STALE_AFTER_SECONDS"])
    @pytest.mark.parametrize("raw", ["0", "-5", "uno"])
    def test_un_intervalo_invalido_impide_arrancar(self, monkeypatch, connection, name, raw):
        from app import create_app
        from infra.configuration import ConfigurationError
        from tests.conftest import _session_on

        monkeypatch.setenv(name, raw)
        with pytest.raises(ConfigurationError, match=name):
            create_app(session_factory=lambda: _session_on(connection))


class TestRetencion:
    """D-33: la limpieza diaria borra los reportes de mas de N dias (7 por defecto)."""

    NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)

    def report(self, session, days_ago, status="READY"):
        record = MonthlyReportRecord(
            user_id=uuid4(), period="2026-10", language="es", status=status,
            content=b"x" if status == "READY" else None, created_at=self.NOW - timedelta(days=days_ago),
        )
        session.add(record)
        session.commit()
        return record.id

    def service(self, session, **kwargs):
        return ReportService(session, CsvReportRenderer(), clock=lambda: self.NOW, **kwargs)

    def test_borra_los_de_mas_de_7_dias_en_cualquier_estado(self, session):
        viejo = self.report(session, 8)
        viejo_pendiente = self.report(session, 10, status="PENDING")
        viejo_fallido = self.report(session, 9, status="FAILED")
        reciente = self.report(session, 6)
        justo = self.report(session, 7)

        assert self.service(session).purge_expired() == 3
        session.expire_all()
        restantes = {r.id for r in session.query(MonthlyReportRecord).all()}
        assert {viejo, viejo_pendiente, viejo_fallido}.isdisjoint(restantes)
        assert {reciente, justo} <= restantes

    def test_la_retencion_es_configurable(self, session):
        tres = self.report(session, 4)
        dos = self.report(session, 2)
        assert self.service(session, retention_days=3).purge_expired() == 1
        session.expire_all()
        assert session.get(MonthlyReportRecord, tres) is None
        assert session.get(MonthlyReportRecord, dos) is not None

    def test_es_idempotente(self, session):
        self.report(session, 30)
        assert self.service(session).purge_expired() == 1
        assert self.service(session).purge_expired() == 0

    def test_la_aplicacion_lee_la_retencion_del_entorno(self, monkeypatch, connection):
        from app import create_app
        from tests.conftest import _session_on

        monkeypatch.setenv("REPORT_RETENTION_DAYS", "30")
        app = create_app(session_factory=lambda: _session_on(connection))
        assert app.config["REPORT_RETENTION_DAYS"] == 30
