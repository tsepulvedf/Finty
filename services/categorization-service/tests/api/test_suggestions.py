"""Contrato interno `POST /v1/suggestions/` (ARCHITECTURE.md §10.4)."""
import os

import pytest

URL = "/v1/suggestions/"


def suggest(client, description="Almuerzo en el restaurante", transaction_type="expense"):
    return client.post(URL, json={"description": description, "transaction_type": transaction_type})


class TestRespuesta:
    def test_200_con_los_tres_campos_en_orden(self, client):
        response = suggest(client)

        assert response.status_code == 200
        assert list(response.json) == ["category_name", "confidence", "source"]
        assert response.json == {
            "category_name": "Alimentación",
            "confidence": 0.75,
            "source": "rule",
        }

    def test_ingreso(self, client):
        response = suggest(client, "Pago de nomina", "income")
        assert response.json["category_name"] == "Salario"

    def test_sin_regla_cae_en_la_categoria_de_respaldo(self, client):
        response = suggest(client, "algo sin regla", "income")
        assert response.json == {"category_name": "Otros ingresos", "confidence": 0.2, "source": "rule"}

    def test_la_descripcion_es_opcional(self, client):
        response = client.post(URL, json={"transaction_type": "expense"})
        assert response.json["category_name"] == "Otros gastos"

    def test_no_pide_identidad(self, client):
        """La clasificacion no depende del usuario: sin X-User-Id responde igual."""
        assert "X-User-Id" not in suggest(client).request.headers
        assert suggest(client).status_code == 200

    def test_el_json_sale_en_utf8(self, client):
        assert "Alimentación" in suggest(client).get_data(as_text=True)


class TestFactoryPorEntorno:
    """A-13 en el origen: la misma peticion, procedencia distinta segun el proveedor."""

    @pytest.mark.parametrize(
        "provider,expected",
        [
            ("RULE", ("Alimentación", 0.75, "rule")),
            ("MOCK", ("Otros gastos", 1.0, "mock")),
            ("AI", ("Alimentación", 0.75, "rule")),
        ],
    )
    def test_procedencia_segun_proveedor(self, monkeypatch, client, provider, expected):
        monkeypatch.setenv("CATEGORIZER_PROVIDER", provider)
        body = suggest(client).json
        assert (body["category_name"], body["confidence"], body["source"]) == expected

    def test_un_proveedor_desconocido_es_un_error_de_configuracion(self, monkeypatch, client):
        monkeypatch.setenv("CATEGORIZER_PROVIDER", "GPT")
        response = suggest(client)
        assert response.status_code == 500
        assert response.json["error"]["code"] == "configuration_error"


class TestValidacion:
    @pytest.mark.parametrize(
        "body,field",
        [
            ({}, "transaction_type"),
            ({"transaction_type": "transfer"}, "transaction_type"),
            ({"transaction_type": "expense", "description": 5}, "description"),
            ({"transaction_type": "expense", "description": "x" * 256}, "description"),
            ({"transaction_type": None}, "transaction_type"),
        ],
    )
    def test_400_con_el_campo_que_falla(self, client, body, field):
        response = client.post(URL, json=body)

        assert response.status_code == 400
        assert response.json["error"]["code"] == "invalid_request"
        assert field in response.json["error"]["fields"]

    def test_cuerpo_que_no_es_objeto(self, client):
        response = client.post(URL, json=["x"])
        assert (response.status_code, response.json["error"]["code"]) == (400, "invalid_request")

    def test_json_mal_formado(self, client):
        response = client.post(URL, data="{", content_type="application/json")
        assert (response.status_code, response.json["error"]["code"]) == (400, "invalid_request")


class TestRutas:
    def test_metodo_no_permitido(self, client):
        response = client.get(URL)
        assert (response.status_code, response.json["error"]["code"]) == (405, "method_not_allowed")

    def test_ruta_inexistente(self, client):
        response = client.get("/api/v1/accounts/")
        assert (response.status_code, response.json["error"]["code"]) == (404, "not_found")

    def test_health(self, client):
        assert client.get("/health/").json == {"status": "ok"}


def test_la_zona_horaria_del_proceso_es_la_de_time_zone(app):
    assert os.environ["TZ"] == app.config["TIME_ZONE"] == "America/Bogota"
