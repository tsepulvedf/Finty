"""Contrato HTTP de analytics-service (ARCHITECTURE.md §10.6)."""
import os
from datetime import date
from uuid import uuid4

import pytest

from services import EventProjector
from tests.streams import Transaction, event

DASHBOARD = "/api/v1/analytics/dashboard/"
INSIGHTS = "/api/v1/analytics/insights/"
PATTERNS = "/api/v1/analytics/spending-patterns/"
SUMMARY = "/api/v1/public/spending-summary/"


@pytest.fixture
def feed(session):
    projector = EventProjector(session)

    def _feed(*messages):
        for i, message in enumerate(messages):
            projector.project(event(message), f"{i}-0")

    return _feed


def test_la_zona_horaria_del_proceso_es_la_de_time_zone(app):
    """RULES.md: cada servicio Flask fija la zona del proceso a `TIME_ZONE`."""
    assert os.environ["TZ"] == app.config["TIME_ZONE"] == "America/Bogota"


class TestAutenticacion:
    @pytest.mark.parametrize("url", [DASHBOARD, INSIGHTS, PATTERNS])
    def test_sin_identidad_401(self, anonimo, url):
        response = anonimo.get(url)
        assert response.status_code == 401
        assert response.json == {"detail": "Las credenciales de autenticación no se proveyeron."}
        assert response.headers["WWW-Authenticate"] == "Token"

    def test_el_resumen_publico_no_pide_identidad(self, anonimo):
        assert anonimo.get(f"{SUMMARY}?period=2026-10").status_code == 200

    def test_metodo_no_permitido(self, ana):
        response = ana.post(DASHBOARD, {})
        assert response.status_code == 405
        assert response.json == {"detail": 'Método "POST" no permitido.'}

    def test_periodo_invalido_400(self, ana):
        response = ana.get(f"{DASHBOARD}?period=2026-13")
        assert response.status_code == 400
        assert response.json == {"period": ["Periodo invalido. Use el formato AAAA-MM, por ejemplo 2026-10."]}


class TestDashboard:
    def test_refleja_alta_reclasificacion_y_borrado(self, ana, feed):
        tx = Transaction(user_id=ana.user_id)
        feed(tx.added())
        body = ana.get(f"{DASHBOARD}?period=2026-10").json
        [cop] = body["currencies"]
        assert (body["period"], cop["currency"], cop["expense"]) == ("2026-10", "COP", "120000.00")
        assert cop["categories"][0]["category_name"] == "Alimentación"

        feed(tx.categorized("Compras"))
        [cop] = ana.get(f"{DASHBOARD}?period=2026-10").json["currencies"]
        assert cop["categories"][0]["category_name"] == "Compras"

        feed(tx.deleted())
        assert ana.get(f"{DASHBOARD}?period=2026-10").json["currencies"] == []

    def test_solo_ve_lo_suyo(self, ana, juan, feed):
        feed(Transaction(user_id=juan.user_id).added())
        assert ana.get(f"{DASHBOARD}?period=2026-10").json["currencies"] == []

    def test_forma_completa(self, ana, feed):
        feed(Transaction(user_id=ana.user_id).added(), Transaction(user_id=ana.user_id, kind="income", category="Salario", amount="500000.00").added())
        [cop] = ana.get(f"{DASHBOARD}?period=2026-10").json["currencies"]

        assert list(cop) == ["currency", "income", "expense", "net", "categories", "accounts", "trend"]
        assert (cop["income"], cop["net"]) == ("500000.00", "380000.00")
        assert len(cop["trend"]) == 6 and cop["trend"][-1]["period"] == "2026-10"
        assert cop["categories"][0]["share"] == "1.0000"

    def test_monedas_separadas(self, ana, feed):
        feed(Transaction(user_id=ana.user_id).added(), Transaction(user_id=ana.user_id, currency="USD", amount="10.00").added())
        currencies = [c["currency"] for c in ana.get(f"{DASHBOARD}?period=2026-10").json["currencies"]]
        assert currencies == ["COP", "USD"]


class TestInsightsYPatrones:
    def test_insights_con_code_params_y_evidencia(self, ana, feed):
        feed(
            Transaction(user_id=ana.user_id, kind="income", category="Salario", amount="100000.00").added(),
            Transaction(user_id=ana.user_id, amount="150000.00").added(),
        )
        body = ana.get(f"{INSIGHTS}?period=2026-10").json

        codes = [i["code"] for i in body["insights"]]
        assert codes == ["negative_savings", "top_category"]
        negative = body["insights"][0]
        assert negative["severity"] == "warning"
        assert negative["params"] == {"currency": "COP", "deficit": "50000.00"}
        assert negative["evidence"] == {"income": "100000.00", "expense": "150000.00"}

    def test_spike_con_meses_anteriores(self, ana, feed):
        months = [date(2026, m, 5) for m in (7, 8, 9)]
        feed(*[Transaction(user_id=ana.user_id, amount="100000.00", on=d).added() for d in months],
             Transaction(user_id=ana.user_id, amount="200000.00").added())
        spike = next(i for i in ana.get(f"{INSIGHTS}?period=2026-10").json["insights"] if i["code"] == "category_spike")
        assert spike["params"]["increase_pct"] == "100.0"
        assert spike["evidence"]["previous_months"] == [
            {"period": "2026-07", "total": "100000.00"},
            {"period": "2026-08", "total": "100000.00"},
            {"period": "2026-09", "total": "100000.00"},
        ]

    def test_patrones(self, ana, feed):
        feed(*[Transaction(user_id=ana.user_id, amount="39900.00", category="Entretenimiento",
                           description="Netflix", on=date(2026, m, 3)).added() for m in (8, 9, 10)])
        body = ana.get(f"{PATTERNS}?period=2026-10").json

        assert (body["reference_period"], body["window_months"]) == ("2026-10", 6)
        [pattern] = body["patterns"]
        assert pattern == {
            "description": "netflix", "category_name": "Entretenimiento", "currency": "COP",
            "average_amount": "39900.00", "months_present": 3, "window_months": 6,
            "occurrences": 3, "monthly_frequency": "1.00", "last_seen": "2026-10-03",
        }


class TestResumenPublico:
    def test_k_anonimato(self, anonimo, feed):
        users = [uuid4() for _ in range(3)]
        feed(
            *[Transaction(user_id=u, amount="90000.00").added() for u in users],
            *[Transaction(user_id=u, amount="5000.00", category="Salud").added() for u in users[:2]],
        )
        body = anonimo.get(f"{SUMMARY}?period=2026-10").json

        assert body["min_users"] == 3
        assert body["categories"] == [{
            "category_name": "Alimentación", "currency": "COP", "users": 3,
            "total": "270000.00", "average_per_user": "90000.00",
        }]

    def test_k_configurable(self, app, anonimo, feed):
        from dataclasses import replace
        app.config["ANALYTICS_THRESHOLDS"] = replace(app.config["ANALYTICS_THRESHOLDS"], public_min_users=1)
        feed(Transaction(amount="5000.00", category="Salud").added())
        names = [c["category_name"] for c in anonimo.get(f"{SUMMARY}?period=2026-10").json["categories"]]
        assert names == ["Salud"]

    def test_lo_borrado_no_cuenta(self, anonimo, feed):
        txs = [Transaction(amount="10.00") for _ in range(3)]
        feed(*[t.added() for t in txs], txs[0].deleted())
        assert anonimo.get(f"{SUMMARY}?period=2026-10").json["categories"] == []
