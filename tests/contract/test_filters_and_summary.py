"""D-29 y D-30 por el Gateway (E2-M8b): filtros de /transactions/, /accounts/summary/
y la comparacion del dashboard. Son cambios compatibles: la suite anterior sigue
pasando sin tocarla.
"""
import uuid
from urllib.parse import urlencode

from helpers import TRANSACTIONS, YESTERDAY, create_account, register
from test_analytics import DASHBOARD, wait_until

SUMMARY = "/api/v1/accounts/summary/"


def descriptions(user, **query):
    body = user.client.get(f"{TRANSACTIONS}?{urlencode(query)}").json
    return sorted(t["description"] for t in body["results"])


class TestBusquedaYTipo:
    def test_busqueda_sin_mayusculas_ni_tildes_y_tipo(self, ana):
        cuenta = create_account(ana, initial_balance="1000000")
        marca = uuid.uuid4().hex[:8]
        register(ana, cuenta["id"], "38000", description=f"Almuerzo CAFÉ {marca}")
        register(ana, cuenta["id"], "12000", description=f"cafe con leche {marca}")
        register(ana, cuenta["id"], "500000", "income", description=f"Nómina {marca}")

        # "cafe" encuentra "CAFÉ": sin mayusculas ni tildes.
        assert descriptions(ana, q=f"cafe {marca}") == [f"Almuerzo CAFÉ {marca}"]
        assert descriptions(ana, q=f"CON LECHE {marca}") == [f"cafe con leche {marca}"]
        assert descriptions(ana, q=f"nomina {marca}") == [f"Nómina {marca}"]
        assert len(descriptions(ana, q=marca)) == 3
        assert descriptions(ana, q=marca, type="income") == [f"Nómina {marca}"]
        assert len(descriptions(ana, q=marca, type="expense")) == 2

    def test_tipo_invalido_400(self, ana):
        response = ana.client.get(f"{TRANSACTIONS}?type=transfer")
        assert response.status == 400
        assert response.json == {"type": ['"transfer" no es una elección válida.']}

    def test_busqueda_solo_en_lo_propio(self, ana, juan):
        cuenta = create_account(ana, initial_balance="100000")
        marca = uuid.uuid4().hex
        register(ana, cuenta["id"], "1000", description=marca)
        assert descriptions(juan, q=marca) == []


class TestResumenDeSaldos:
    def test_una_fila_por_moneda_sin_mezclar(self, mateo):
        antes = {row["currency"]: row for row in mateo.client.get(SUMMARY).json["currencies"]}
        create_account(mateo, initial_balance="1000.50", currency="USD")
        despues = {row["currency"]: row for row in mateo.client.get(SUMMARY).json["currencies"]}

        usd_antes = antes.get("USD", {"balance": "0.00", "accounts": 0})
        assert despues["USD"]["accounts"] == usd_antes["accounts"] + 1
        assert float(despues["USD"]["balance"]) == float(usd_antes["balance"]) + 1000.50
        assert list(despues["USD"]) == ["currency", "balance", "accounts"]

    def test_sin_token_401(self, anonimo):
        response = anonimo.get(SUMMARY)
        assert response.status == 401
        assert response.header("X-Finty-Route") == "finance"


class TestComparacionDelDashboard:
    def test_trae_periodo_anterior_variacion_y_tasa(self, ana):
        cuenta = create_account(ana, initial_balance="5000000")
        register(ana, cuenta["id"], "1000000", "income", description="Pago de nomina")
        register(ana, cuenta["id"], "250000", category_name="Compras")
        period = YESTERDAY[:7]

        def section():
            body = ana.client.get(f"{DASHBOARD}?period={period}").json
            found = next((c for c in body["currencies"] if c["currency"] == "COP"), None)
            return found if found and found["savings_rate"] is not None else None

        cop = wait_until(section)
        assert set(cop) >= {"previous", "expense_change_pct", "savings_rate"}
        assert cop["previous"]["period"] < period
        assert -1 <= float(cop["savings_rate"]) <= 1
