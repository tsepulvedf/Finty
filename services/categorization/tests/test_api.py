"""Contrato HTTP y equivalencia con las reglas originales, sin base de datos."""
import pytest

from core.domain.value_objects import Money
from finance.infra.categorizers import RuleBasedCategorizer
from services.categorization.app import create_app

TOKEN = "test-internal-token"
HEADERS = {"X-Service-Token": TOKEN}


@pytest.fixture
def client():
    return create_app(service_token=TOKEN).test_client()


def payload(description="almuerzo", transaction_type="expense"):
    return {"description": description, "amount": "25000.00", "currency": "COP", "type": transaction_type}


@pytest.mark.parametrize("description,kind", [
    ("almuerzo", "expense"), ("NÓMINA", "income"), ("metro", "expense"),
    ("sin coincidencia", "income"), ("supermercadito", "expense"), ("", "expense"),
])
def test_equivalence(client, description, kind):
    response = client.post("/api/v2/categorization/", json=payload(description, kind), headers=HEADERS)
    expected = RuleBasedCategorizer().categorize(description, Money("25000", "COP"), kind)
    assert response.status_code == 200
    assert response.json == {"category_name": expected.category_name, "confidence": expected.confidence, "source": "rule"}
    assert response.headers["X-Finty-Service"] == "flask-categorization"


@pytest.mark.parametrize("field,value", [
    ("amount", 1.2), ("amount", True), ("amount", "0"), ("amount", "-10"),
    ("amount", "NaN"), ("amount", "1e10000"), ("amount", "1.001"),
    ("type", "transfer"), ("currency", "PESOS"), ("description", "x" * 256),
])
def test_invalid_input(client, field, value):
    data = payload()
    data[field] = value
    response = client.post("/api/v2/categorization/", json=data, headers=HEADERS)
    assert response.status_code == 400
    assert response.json["error"]["code"] == "INVALID_INPUT"


@pytest.mark.parametrize("data", [[], None, {}, {"amount": "1"}])
def test_object_required(client, data):
    response = client.post("/api/v2/categorization/", data=__import__("json").dumps(data), content_type="application/json", headers=HEADERS)
    assert response.status_code == 400


def test_malformed_json(client):
    response = client.post("/api/v2/categorization/", data="{bad", content_type="application/json", headers=HEADERS)
    assert response.status_code == 400
    assert "error" in response.json


def test_authentication(client):
    assert client.post("/api/v2/categorization/", json=payload()).status_code == 401
    assert client.get("/healthz").status_code == 200


def test_500_is_structured_and_does_not_disclose(client):
    class BrokenService:
        def suggest(self, data):
            raise RuntimeError("sensitive-detail")
    client = create_app(service=BrokenService(), service_token=TOKEN).test_client()
    response = client.post("/api/v2/categorization/", json=payload(), headers=HEADERS)
    assert response.status_code == 500
    assert response.json["error"]["code"] == "INTERNAL_ERROR"
    assert "sensitive-detail" not in response.get_data(as_text=True)


def test_payload_limit(client):
    response = client.post("/api/v2/categorization/", data="x" * 17000, content_type="application/json", headers=HEADERS)
    assert response.status_code == 413
    assert "error" in response.json
