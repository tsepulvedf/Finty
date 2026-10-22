"""D-30 (E2-M8b): busqueda y tipo en /transactions/."""
from datetime import date, timedelta
from urllib.parse import urlencode

import pytest

ACCOUNTS = "/api/v1/accounts/"
TRANSACTIONS = "/api/v1/transactions/"
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def account(client, name, currency="COP", balance="1000000", kind="bank"):
    response = client.post(ACCOUNTS, {"name": name, "type": kind, "initial_balance": balance, "currency": currency})
    assert response.status_code == 201, response.json
    return response.json["id"]


def register(client, account_id, amount, kind="expense", description=""):
    response = client.post(TRANSACTIONS, {
        "account_id": account_id, "amount": amount, "type": kind,
        "occurred_on": YESTERDAY, "description": description,
    })
    assert response.status_code == 201, response.json
    return response.json["id"]


def descriptions(client, **query):
    return sorted(t["description"] for t in client.get(f"{TRANSACTIONS}?{urlencode(query)}").json["results"])


@pytest.fixture
def movimientos(ana):
    cuenta = account(ana, "Nequi")
    register(ana, cuenta, "38000", description="Almuerzo en el CAFÉ central")
    register(ana, cuenta, "12000", description="cafe con leche")
    register(ana, cuenta, "500000", "income", description="Pago de nómina")
    register(ana, cuenta, "9000", description="Descuento 50% en_linea")
    return cuenta


class TestBusqueda:
    def test_sin_mayusculas_ni_tildes(self, ana, movimientos):
        assert descriptions(ana, q="cafe") == ["Almuerzo en el CAFÉ central", "cafe con leche"]
        assert descriptions(ana, q="CAFÉ") == ["Almuerzo en el CAFÉ central", "cafe con leche"]
        assert descriptions(ana, q="nomina") == ["Pago de nómina"]

    def test_comodines_literales(self, ana, movimientos):
        assert descriptions(ana, q="50%") == ["Descuento 50% en_linea"]
        # Como comodin, "_" coincidiria con la "e" de "Descuento"; aqui es literal.
        assert descriptions(ana, q="u_n") == []
        assert descriptions(ana, q="en_l") == ["Descuento 50% en_linea"]

    def test_en_blanco_no_filtra(self, ana, movimientos):
        assert len(descriptions(ana, q="  ")) == 4

    def test_solo_las_propias(self, ana, juan, movimientos):
        assert descriptions(juan, q="cafe") == []

    def test_demasiado_larga_400(self, ana):
        response = ana.get(f"{TRANSACTIONS}?q={'x' * 256}")
        assert response.status_code == 400
        assert list(response.json) == ["q"]


class TestTipo:
    def test_filtra_por_tipo(self, ana, movimientos):
        assert descriptions(ana, type="income") == ["Pago de nómina"]
        assert len(descriptions(ana, type="expense")) == 3

    def test_se_combina_con_la_busqueda(self, ana, movimientos):
        assert descriptions(ana, type="income", q="cafe") == []

    def test_valor_invalido_400(self, ana):
        response = ana.get(f"{TRANSACTIONS}?type=transfer")
        assert (response.status_code, response.json) == (400, {"type": ['"transfer" no es una elección válida.']})

