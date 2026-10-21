"""analytics-service por el Gateway: lectura autenticada y endpoint publico (§10.6, §10.7).

El dashboard es **eventualmente consistente** (ADR-15): una transaccion aparece
unos instantes despues de registrarla, cuando analytics-worker consume su evento.
Por eso los tests de punta a punta sondean con un limite de tiempo
(`wait_until`) en lugar de dormir un tiempo fijo.

Cada test usa un periodo pasado aleatorio sin datos previos, para no depender
de lo que otros tests o corridas anteriores registraron.
"""
import random
import time

import pytest

from helpers import NOT_AUTHENTICATED, TRANSACTIONS, create_account, method_not_allowed, register

DASHBOARD = "/api/v1/analytics/dashboard/"
INSIGHTS = "/api/v1/analytics/insights/"
PATTERNS = "/api/v1/analytics/spending-patterns/"
SUMMARY = "/api/v1/public/spending-summary/"

# Margen para que el worker consuma el evento (en local tarda milisegundos).
EVENTUAL_TIMEOUT_SECONDS = 15
POLL_INTERVAL_SECONDS = 0.3
# El endpoint publico tiene una cuota estricta (finty_public, 30/min).
PUBLIC_POLL_INTERVAL_SECONDS = 2


def wait_until(probe, timeout=EVENTUAL_TIMEOUT_SECONDS, interval=POLL_INTERVAL_SECONDS):
    """Repite `probe()` hasta que devuelva algo verdadero o se agote el tiempo."""
    deadline = time.monotonic() + timeout
    while True:
        result = probe()
        if result:
            return result
        if time.monotonic() >= deadline:
            pytest.fail(f"no se cumplio en {timeout} s (consistencia eventual)")
        time.sleep(interval)


def random_period():
    return f"{random.randint(2000, 2024)}-{random.randint(1, 12):02d}"


def fresh_period(anonimo):
    """Periodo pasado sin categorias publicadas en el resumen publico."""
    for _ in range(10):
        period = random_period()
        if not anonimo.get(f"{SUMMARY}?period={period}").json["categories"]:
            return period
    pytest.fail("no se encontro un periodo pasado sin datos")


def currency_section(user, period, currency="COP"):
    body = user.client.get(f"{DASHBOARD}?period={period}").json
    return next((c for c in body["currencies"] if c["currency"] == currency), None)


def categories(section):
    return {c["category_name"]: c["total"] for c in section["categories"]} if section else {}


@pytest.fixture
def cuenta(ana):
    return create_account(ana, initial_balance="1000000")


class TestAutenticacion:
    @pytest.mark.parametrize("path", [DASHBOARD, INSIGHTS, PATTERNS, "/api/v1/analytics"])
    def test_sin_token_401_del_gateway(self, anonimo, path):
        response = anonimo.get(path)
        assert response.status == 401
        assert response.json == NOT_AUTHENTICATED
        assert response.header("WWW-Authenticate") == "Token"
        assert response.header("X-Finty-Route") == "analytics"

    def test_x_user_id_del_cliente_se_ignora(self, anonimo, ana):
        response = anonimo.get(DASHBOARD, headers={"X-User-Id": ana.user_id})
        assert response.status == 401

    def test_metodo_no_permitido(self, ana):
        response = ana.client.post(DASHBOARD, {})
        assert response.status == 405
        assert response.json == method_not_allowed("POST")

    def test_periodo_invalido(self, ana):
        response = ana.client.get(f"{DASHBOARD}?period=2026-13")
        assert response.status == 400
        assert list(response.json) == ["period"]


class TestDePuntaAPunta:
    """Registrar, reclasificar y eliminar en finance se refleja en el dashboard."""

    def test_registrar_reclasificar_y_eliminar(self, anonimo, ana, cuenta):
        period = fresh_period(anonimo)
        created = register(ana, cuenta["id"], "45000", occurred_on=f"{period}-15",
                           category_name="Compras", description="Libros")
        assert created.status == 201, created.text
        tx = created.json

        section = wait_until(lambda: categories(currency_section(ana, period)).get("Compras") == "45000.00"
                             and currency_section(ana, period))
        assert (section["expense"], section["net"]) == ("45000.00", "-45000.00")
        assert section["accounts"][0]["account_id"] == cuenta["id"]

        moved = ana.client.post(f"{TRANSACTIONS}{tx['id']}/categorize/", {"category_name": "Entretenimiento"})
        assert moved.status == 200, moved.text
        wait_until(lambda: categories(currency_section(ana, period)) == {"Entretenimiento": "45000.00"})

        assert ana.client.delete(f"{TRANSACTIONS}{tx['id']}/").status == 204
        wait_until(lambda: currency_section(ana, period) is None)

    def test_cada_usuario_ve_solo_lo_suyo(self, anonimo, ana, juan, cuenta):
        period = fresh_period(anonimo)
        assert register(ana, cuenta["id"], "1000", occurred_on=f"{period}-02").status == 201
        wait_until(lambda: currency_section(ana, period))
        assert currency_section(juan, period) is None


class TestInsightsYPatrones:
    def test_insights_explicables(self, anonimo, ana, cuenta):
        period = fresh_period(anonimo)
        register(ana, cuenta["id"], "100000", "income", occurred_on=f"{period}-01", description="Pago de nomina")
        register(ana, cuenta["id"], "150000", occurred_on=f"{period}-02", category_name="Compras")

        def codes():
            body = ana.client.get(f"{INSIGHTS}?period={period}").json
            found = {i["code"]: i for i in body["insights"]}
            return found if "negative_savings" in found else None

        found = wait_until(codes)
        negative = found["negative_savings"]
        assert negative["severity"] == "warning"
        assert negative["params"] == {"currency": "COP", "deficit": "50000.00"}
        assert negative["evidence"] == {"income": "100000.00", "expense": "150000.00"}
        assert found["top_category"]["params"]["category_name"] == "Compras"

    def test_gasto_recurrente(self, anonimo, ana, cuenta):
        period = fresh_period(anonimo)
        year, month = map(int, period.split("-"))
        months = [(year, month - offset) if month > offset else (year - 1, month - offset + 12) for offset in (0, 1, 2)]
        name = f"Suscripcion {random.randint(1000, 9999)}"
        for y, m in months:
            assert register(ana, cuenta["id"], "39900", occurred_on=f"{y}-{m:02d}-05",
                            category_name="Entretenimiento", description=name).status == 201

        def pattern():
            body = ana.client.get(f"{PATTERNS}?period={period}").json
            return next((p for p in body["patterns"] if p["description"] == name.lower()), None)

        found = wait_until(pattern)
        assert (found["average_amount"], found["months_present"], found["last_seen"]) == (
            "39900.00", 3, f"{period}-05",
        )


class TestResumenPublico:
    def test_sin_autenticacion_y_con_su_forma(self, anonimo):
        response = anonimo.get(f"{SUMMARY}?period=2026-10")
        assert response.status == 200
        assert response.header("X-Finty-Route") == "public"
        assert list(response.json) == ["period", "min_users", "categories"]

    def test_periodo_invalido(self, anonimo):
        assert anonimo.get(f"{SUMMARY}?period=octubre").status == 400

    def test_k_anonimato(self, anonimo, ana, juan, eva):
        """Con menos de k usuarios la categoria no aparece; con k, si."""
        period = fresh_period(anonimo)
        users = [ana, juan, eva]
        for user in users[:2]:
            account = create_account(user, initial_balance="1000000")
            assert register(user, account["id"], "20000", occurred_on=f"{period}-10", category_name="Salud").status == 201
            wait_until(lambda: currency_section(user, period))

        body = anonimo.get(f"{SUMMARY}?period={period}").json
        assert body["min_users"] == 3
        assert "Salud" not in {c["category_name"] for c in body["categories"]}

        account = create_account(eva, initial_balance="1000000")
        assert register(eva, account["id"], "50000", occurred_on=f"{period}-11", category_name="Salud").status == 201

        def salud():
            rows = anonimo.get(f"{SUMMARY}?period={period}").json["categories"]
            return next((c for c in rows if c["category_name"] == "Salud"), None)

        row = wait_until(salud, interval=PUBLIC_POLL_INTERVAL_SECONDS)
        assert row == {"category_name": "Salud", "currency": "COP", "users": 3,
                       "total": "90000.00", "average_per_user": "30000.00"}
