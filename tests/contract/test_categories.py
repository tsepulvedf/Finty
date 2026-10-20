"""`/api/v1/categories/`: catalogo global de solo lectura."""
import uuid

import pytest

from helpers import CATEGORIES, NOT_FOUND, method_not_allowed, model_not_found

SEEDED = {
    "Alimentación", "Transporte", "Vivienda", "Servicios públicos", "Salud",
    "Educación", "Entretenimiento", "Compras", "Deudas y créditos", "Otros gastos",
    "Salario", "Freelance", "Inversiones", "Reembolsos", "Otros ingresos",
}


@pytest.fixture(scope="module")
def catalogo(ana):
    return ana.client.get(CATEGORIES)


class TestListado:
    def test_paginado_con_las_quince(self, catalogo):
        assert catalogo.status == 200
        body = catalogo.json
        assert list(body) == ["count", "next", "previous", "results"]
        assert (body["count"], body["next"], body["previous"]) == (15, None, None)
        assert {c["name"] for c in body["results"]} == SEEDED

    def test_cada_categoria_expone_tres_campos(self, catalogo):
        for category in catalogo.json["results"]:
            assert list(category) == ["id", "name", "applies_to"]

    def test_orden_por_tipo_y_nombre(self, catalogo):
        keys = [(c["applies_to"], c["name"]) for c in catalogo.json["results"]]
        assert keys[0][0] == "expense" and keys[-1][0] == "income"
        assert [k for k in keys if k[0] == "income"] == sorted(k for k in keys if k[0] == "income")

    def test_el_json_sale_en_utf8_sin_escapar(self, catalogo):
        assert "Alimentación" in catalogo.text
        assert catalogo.header("Content-Type").startswith("application/json")


class TestDetalle:
    def test_detalle(self, ana, catalogo):
        alimentacion = next(c for c in catalogo.json["results"] if c["name"] == "Alimentación")
        response = ana.client.get(f"{CATEGORIES}{alimentacion['id']}/")
        assert response.status == 200
        assert response.json == alimentacion

    def test_id_inexistente(self, ana):
        response = ana.client.get(f"{CATEGORIES}{uuid.uuid4()}/")
        assert (response.status, response.json) == (404, model_not_found("Category"))

    def test_id_mal_formado(self, ana):
        response = ana.client.get(f"{CATEGORIES}no-es-un-uuid/")
        assert (response.status, response.json) == (404, NOT_FOUND)


class TestSoloLectura:
    def test_post_405(self, ana):
        response = ana.client.post(CATEGORIES, {"name": "Inventada", "applies_to": "expense"})
        assert (response.status, response.json) == (405, method_not_allowed("POST"))

    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
    def test_escrituras_sobre_el_detalle_405(self, ana, catalogo, method):
        category = catalogo.json["results"][0]
        response = ana.client.request(method, f"{CATEGORIES}{category['id']}/", body={})
        assert (response.status, response.json) == (405, method_not_allowed(method))
