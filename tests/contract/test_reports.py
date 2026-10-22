"""Reporte mensual asincrono por el Gateway (E2-M7, §10.6).

`POST /analytics/reports/` responde 202 PENDING; la tarea de Celery
(`analytics-celery`) lo deja READY, y `/download/` entrega el CSV. Se usa una
usuaria propia y FREE (`rosa`): sus movimientos son exactamente los de este
modulo, y sirve para la ventana de 3 meses.

Antes de pedir el reporte se espera a que analytics proyecte los movimientos
(consistencia eventual, A-27): el reporte se arma con lo que analytics sabe.
"""
import csv
import io
import time
import uuid
from datetime import date

import pytest

from conftest import _register_and_login
from helpers import NOT_AUTHENTICATED, create_account, register

REPORTS = "/api/v1/analytics/reports/"
DASHBOARD = "/api/v1/analytics/dashboard/"
POLL_SECONDS = 30


def period(offset):
    today = date.today()
    index = today.year * 12 + today.month - 1 + offset
    return f"{index // 12}-{index % 12 + 1:02d}"


def wait_for(check, label, timeout=POLL_SECONDS):
    end = time.monotonic() + timeout
    while True:
        value = check()
        if value:
            return value
        if time.monotonic() > end:
            pytest.fail(f"tiempo agotado esperando: {label}")
        time.sleep(0.5)


def rows(response):
    text = response.text
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:])))


@pytest.fixture(scope="module")
def rosa(anonimo):
    """FREE, con dos movimientos del mes en curso ya proyectados en analytics."""
    user = _register_and_login(anonimo, "rosa")
    account = create_account(user, name=f"Reporte {uuid.uuid4().hex[:6]}", initial_balance="100000")
    today = date.today().isoformat()
    for kwargs in (
        {"amount": "38000", "description": "Almuerzo del reporte", "category_name": "Alimentación"},
        {"amount": "3100000", "kind": "income", "description": "Salario del reporte", "category_name": "Salario"},
    ):
        response = register(user, account["id"], occurred_on=today, **kwargs)
        assert response.status == 201, response.text

    def projected():
        sections = user.client.get(f"{DASHBOARD}?period={period(0)}").json["currencies"]
        return sections and sections[0]["expense"] == "38000.00" and sections[0]["income"] == "3100000.00"

    wait_for(projected, "proyeccion de los movimientos")
    return user


def ready(client, report_id):
    def check():
        body = client.get(f"{REPORTS}{report_id}/").json
        return body if body["status"] != "PENDING" else None

    return wait_for(check, f"reporte {report_id} listo")


class TestReporteDePuntaAPunta:
    def test_sin_token_401_del_gateway(self, anonimo):
        response = anonimo.post(REPORTS, {"period": period(0)})
        assert (response.status, response.json) == (401, NOT_AUTHENTICATED)
        assert response.header("X-Finty-Route") == "analytics"

    def test_pending_ready_y_csv_en_espanol(self, rosa):
        response = rosa.client.post(REPORTS, {"period": period(0)}, headers={"Accept-Language": "es-CO,es;q=0.9"})
        assert response.status == 202
        created = response.json
        assert (created["status"], created["period"], created["language"]) == ("PENDING", period(0), "es")
        assert created["download_url"] is None

        body = ready(rosa.client, created["id"])
        assert body["status"] == "READY"
        assert body["download_url"] == f"/api/v1/analytics/reports/{created['id']}/download/"

        download = rosa.client.get(body["download_url"])
        assert download.status == 200
        assert download.header("Content-Type") == "text/csv; charset=utf-8"
        assert download.header("Content-Disposition") == f'attachment; filename="finty-reporte-{period(0)}.csv"'
        data = rows(download)
        assert data[0] == ["Movimientos"]
        assert data[1] == ["Fecha", "Tipo", "Categoría", "Descripción", "Monto", "Moneda"]
        movements = sorted(tuple(row) for row in data[2:4])
        today = date.today().isoformat()
        assert movements == sorted([
            (today, "Gasto", "Alimentación", "Almuerzo del reporte", "38000.00", "COP"),
            (today, "Ingreso", "Salario", "Salario del reporte", "3100000.00", "COP"),
        ])
        assert data[4] == [] and data[5] == ["Resumen por categoría y moneda"]
        assert data[6] == ["Moneda", "Tipo", "Categoría", "Total", "Movimientos"]
        assert data[7:] == [["COP", "Gasto", "Alimentación", "38000.00", "1"],
                            ["COP", "Ingreso", "Salario", "3100000.00", "1"]]

    def test_csv_en_ingles(self, rosa):
        created = rosa.client.post(REPORTS, {"period": period(0)}, headers={"Accept-Language": "en-US,en;q=0.9"}).json
        assert created["language"] == "en"
        body = ready(rosa.client, created["id"])

        download = rosa.client.get(body["download_url"])
        assert download.header("Content-Disposition") == f'attachment; filename="finty-report-{period(0)}.csv"'
        data = rows(download)
        assert data[0] == ["Transactions"]
        assert data[1] == ["Date", "Type", "Category", "Description", "Amount", "Currency"]
        assert data[5] == ["Summary by category and currency"]
        assert data[7:] == [["COP", "Expense", "Food", "38000.00", "1"], ["COP", "Income", "Salary", "3100000.00", "1"]]


class TestReporteReglas:
    def test_solo_el_dueno_lo_ve(self, rosa, ana):
        report_id = rosa.client.post(REPORTS, {"period": period(0)}).json["id"]
        for path in (f"{REPORTS}{report_id}/", f"{REPORTS}{report_id}/download/"):
            response = ana.client.get(path)
            assert response.status == 404
            assert response.json["error"]["code"] == "report_not_found"

    def test_free_fuera_de_su_ventana_403(self, rosa):
        response = rosa.client.post(REPORTS, {"period": period(-3)})
        assert response.status == 403
        assert response.json["error"]["code"] == "premium_required"

    @pytest.mark.parametrize("offset", [-1, -2])
    def test_free_dentro_de_su_ventana_202(self, rosa, offset):
        assert rosa.client.post(REPORTS, {"period": period(offset)}).status == 202

    def test_premium_pide_cualquier_mes(self, ana):
        assert ana.client.post(REPORTS, {"period": period(-12)}).status == 202

    @pytest.mark.parametrize("body", [{}, {"period": "2026-13"}, {"period": 202610}])
    def test_periodo_invalido_400(self, rosa, body):
        response = rosa.client.post(REPORTS, body)
        assert response.status == 400 and "period" in response.json

    def test_un_periodo_sin_movimientos_tambien_genera(self, rosa):
        report_id = rosa.client.post(REPORTS, {"period": period(-2)}).json["id"]
        body = ready(rosa.client, report_id)
        assert body["status"] == "READY"
        data = rows(rosa.client.get(body["download_url"]))
        assert data[2] == [] and data[3] == ["Resumen por categoría y moneda"]
