"""`/api/v1/accounts/`: exitos, errores de dominio, validacion, 404 y 405."""
import uuid

import pytest

from helpers import (
    ACCOUNT_FIELDS,
    ACCOUNTS,
    BLANK,
    INVALID_NUMBER,
    NOT_FOUND,
    NULL,
    REQUIRED,
    all_ids,
    create_account,
    error_code,
    method_not_allowed,
    model_not_found,
    register,
    unique,
)


class TestCrear:
    def test_201_con_los_campos_del_contrato_en_orden(self, ana):
        name = unique("Ahorros")
        response = ana.client.post(
            ACCOUNTS, {"name": f"  {name}  ", "type": "bank", "initial_balance": "1000000.5"}
        )

        assert response.status == 201
        body = response.json
        assert list(body) == ACCOUNT_FIELDS
        assert body["name"] == name
        assert (body["balance"], body["opening_balance"]) == ("1000000.50", "1000000.50")
        assert (body["currency"], body["is_archived"], body["type"]) == ("COP", False, "bank")
        assert body["created_at"].endswith("-05:00")

    def test_credito_abre_en_negativo(self, ana):
        body = create_account(ana, kind="credit", initial_balance="-500000")
        assert body["balance"] == "-500000.00"

    def test_moneda_explicita(self, ana):
        assert create_account(ana, currency="usd")["currency"] == "USD"

    def test_nombre_duplicado_409(self, ana):
        name = unique("Duplicada")
        create_account(ana, name=name)
        response = ana.client.post(ACCOUNTS, {"name": name, "type": "cash"})

        assert response.status == 409
        assert response.json == {
            "error": {
                "code": "duplicate_account_name",
                "message": f"Ya tienes una cuenta llamada '{name}'.",
            }
        }

    def test_el_mismo_nombre_para_otro_usuario_es_valido(self, ana, juan):
        name = unique("Compartida")
        create_account(ana, name=name)
        create_account(juan, name=name)

    def test_efectivo_en_negativo_409(self, ana):
        response = ana.client.post(
            ACCOUNTS, {"name": unique("Efectivo"), "type": "cash", "initial_balance": "-1"}
        )
        assert response.status == 409
        assert error_code(response) == "negative_balance_not_allowed"

    def test_validacion_400_con_los_mensajes_de_drf(self, ana):
        response = ana.client.post(
            ACCOUNTS, {"name": "  ", "type": "crypto", "initial_balance": "abc", "currency": None}
        )
        assert response.status == 400
        assert response.json == {
            "name": [BLANK],
            "type": ['"crypto" no es una elección válida.'],
            "initial_balance": [INVALID_NUMBER],
            "currency": [NULL],
        }

    def test_cuerpo_vacio(self, ana):
        response = ana.client.post(ACCOUNTS, {})
        assert response.json == {"name": [REQUIRED], "type": [REQUIRED]}

    def test_precision_del_monto(self, ana):
        response = ana.client.post(
            ACCOUNTS, {"name": "x", "type": "bank", "initial_balance": 10.555}
        )
        assert response.json == {
            "initial_balance": ["Asegúrese de que no haya más de 2 decimales."]
        }

    def test_cuerpo_que_no_es_objeto(self, ana):
        response = ana.client.post(ACCOUNTS, ["x"])
        assert response.json == {
            "non_field_errors": ["Datos inválidos. Se esperaba un diccionario pero es un list."]
        }

    def test_json_mal_formado(self, ana):
        response = ana.client.post(ACCOUNTS, raw=b"{", content_type="application/json")
        assert response.status == 400
        assert response.json["detail"].startswith("JSON parse error - ")


class TestListadoYDetalle:
    def test_el_listado_solo_trae_las_propias(self, ana):
        own = create_account(ana)
        body = ana.client.get(ACCOUNTS).json
        assert list(body) == ["count", "next", "previous", "results"]
        assert own["id"] in all_ids(ana.client, ACCOUNTS)

    def test_ordenado_por_nombre(self, ana):
        names = [a["name"] for a in ana.client.get(ACCOUNTS).json["results"]]
        assert names == sorted(names)

    def test_detalle(self, ana):
        own = create_account(ana)
        assert ana.client.get(f"{ACCOUNTS}{own['id']}/").json == own

    def test_detalle_inexistente(self, ana):
        response = ana.client.get(f"{ACCOUNTS}{uuid.uuid4()}/")
        assert (response.status, response.json) == (404, model_not_found("Account"))

    def test_detalle_mal_formado(self, ana):
        response = ana.client.get(f"{ACCOUNTS}no-es-un-uuid/")
        assert (response.status, response.json) == (404, NOT_FOUND)


class TestModificar:
    def test_renombrar_solo_cambia_el_nombre(self, ana):
        own = create_account(ana)
        name = unique("Nomina")
        response = ana.client.put(
            f"{ACCOUNTS}{own['id']}/", {"name": name, "type": "cash", "currency": "USD"}
        )
        assert response.status == 200
        assert (response.json["name"], response.json["type"], response.json["currency"]) == (
            name, "bank", "COP",
        )

    def test_patch_es_igual_a_put(self, ana):
        own = create_account(ana)
        name = unique("Parche")
        assert ana.client.patch(f"{ACCOUNTS}{own['id']}/", {"name": name}).json["name"] == name

    def test_renombrar_con_nombre_vacio(self, ana):
        own = create_account(ana)
        response = ana.client.patch(f"{ACCOUNTS}{own['id']}/", {"name": ""})
        assert (response.status, response.json) == (400, {"name": [BLANK]})

    def test_renombrar_a_un_nombre_ocupado(self, ana):
        taken = create_account(ana)
        own = create_account(ana)
        response = ana.client.put(f"{ACCOUNTS}{own['id']}/", {"name": taken["name"]})
        assert response.status == 409

    def test_renombrar_inexistente(self, ana):
        response = ana.client.put(f"{ACCOUNTS}{uuid.uuid4()}/", {"name": "x"})
        assert response.status == 404
        assert error_code(response) == "account_not_found"


class TestArchivarYBorrar:
    def test_archivar(self, ana):
        own = create_account(ana)
        response = ana.client.post(f"{ACCOUNTS}{own['id']}/archive/")
        assert (response.status, response.json["is_archived"]) == (200, True)

    def test_archivada_sale_del_listado_y_del_detalle(self, ana):
        own = create_account(ana)
        ana.client.post(f"{ACCOUNTS}{own['id']}/archive/")

        assert own["id"] not in all_ids(ana.client, ACCOUNTS)
        assert ana.client.get(f"{ACCOUNTS}{own['id']}/").status == 404
        assert own["id"] in all_ids(ana.client, f"{ACCOUNTS}?include_archived=true")
        assert ana.client.get(f"{ACCOUNTS}{own['id']}/?include_archived=1").status == 200

    def test_archivar_es_idempotente(self, ana):
        own = create_account(ana)
        ana.client.post(f"{ACCOUNTS}{own['id']}/archive/")
        assert ana.client.post(f"{ACCOUNTS}{own['id']}/archive/").status == 200

    def test_borrar_sin_transacciones_204(self, ana):
        own = create_account(ana)
        response = ana.client.delete(f"{ACCOUNTS}{own['id']}/")
        assert (response.status, response.text) == (204, "")
        assert ana.client.get(f"{ACCOUNTS}{own['id']}/").status == 404

    def test_borrar_con_transacciones_409(self, ana):
        own = create_account(ana, initial_balance="1000")
        register(ana, own["id"], "10")
        response = ana.client.delete(f"{ACCOUNTS}{own['id']}/")
        assert response.status == 409
        assert error_code(response) == "account_has_transactions"


class TestMetodos:
    def test_post_sobre_el_detalle_405(self, ana):
        own = create_account(ana)
        response = ana.client.post(f"{ACCOUNTS}{own['id']}/", {})
        assert (response.status, response.json) == (405, method_not_allowed("POST"))

    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
    def test_escrituras_sobre_el_listado_405(self, ana, method):
        response = ana.client.request(method, ACCOUNTS, body={})
        assert (response.status, response.json) == (405, method_not_allowed(method))

    def test_get_sobre_archive_405(self, ana):
        own = create_account(ana)
        response = ana.client.get(f"{ACCOUNTS}{own['id']}/archive/")
        assert (response.status, response.json) == (405, method_not_allowed("GET"))
