"""Paridad con DRF en lo que el port de `test_api.py` no fija: los mensajes.

Los esperados de `VALIDATION_CASES` no se escribieron a mano: son la salida real
de los serializers de `finance/api/serializers.py` (DRF 3.17.1, `es-co`) para
las mismas entradas, capturada en el contenedor `django` durante E2-M2a. Si el
servicio responde distinto, el contrato cambio.

Tambien fija las respuestas HTTP que DRF producia por su cuenta: 401, 404 con
`detail`, 405, cuerpo mal formado, 415, paginacion y el detalle de cuentas
archivadas.
"""
from datetime import date, timedelta
from uuid import uuid4

import pytest

ACCOUNTS_URL = "/api/v1/accounts/"
CATEGORIES_URL = "/api/v1/categories/"
TRANSACTIONS_URL = "/api/v1/transactions/"

REQUIRED = "Este campo es requerido."
NULL = "Este campo no puede ser nulo."
BLANK = "Este campo no puede estar en blanco."
INVALID_DATE = (
    "Fecha con formato erróneo. Use uno de los siguientes formatos en su lugar: "
    "YYYY-MM-DD."
)

# (url, cuerpo, errores esperados) — salida real de DRF para cada cuerpo.
VALIDATION_CASES = {
    "acc_empty": (ACCOUNTS_URL, {}, {"name": [REQUIRED], "type": [REQUIRED]}),
    "acc_blank": (
        ACCOUNTS_URL,
        {"name": "  ", "type": "x", "initial_balance": "abc", "currency": "CO"},
        {
            "name": [BLANK],
            "type": ['"x" no es una elección válida.'],
            "initial_balance": ["Se requiere un número válido."],
            "currency": ["Asegúrese de que este campo tenga al menos 3 caracteres."],
        },
    ),
    "acc_null": (
        ACCOUNTS_URL,
        {"name": None, "type": None, "initial_balance": None, "currency": None},
        {"name": [NULL], "type": [NULL], "initial_balance": [NULL], "currency": [NULL]},
    ),
    "acc_long": (
        ACCOUNTS_URL,
        {"name": "a" * 121, "type": "bank", "initial_balance": "1.234", "currency": "COPX"},
        {
            "name": ["Asegúrese de que este campo no tenga más de 120 caracteres."],
            "initial_balance": ["Asegúrese de que no haya más de 2 decimales."],
            "currency": ["Asegúrese de que este campo no tenga más de 3 caracteres."],
        },
    ),
    "acc_digits": (
        ACCOUNTS_URL,
        {"name": 123, "type": 5, "initial_balance": "1234567890123.45", "currency": ""},
        {
            "type": ['"5" no es una elección válida.'],
            "initial_balance": ["Asegúrese de que no haya más de 14 dígitos en total."],
            "currency": [BLANK],
        },
    ),
    "acc_bool": (
        ACCOUNTS_URL,
        {"name": True, "type": ["bank"], "initial_balance": True, "currency": 123},
        {
            "name": ["No es una cadena válida."],
            "type": ["\"['bank']\" no es una elección válida."],
            "initial_balance": ["Se requiere un número válido."],
        },
    ),
    "acc_nan": (
        ACCOUNTS_URL,
        {"name": {"a": 1}, "type": "BANK", "initial_balance": "NaN", "currency": "cop"},
        {
            "name": ["No es una cadena válida."],
            "type": ['"BANK" no es una elección válida.'],
            "initial_balance": ["Se requiere un número válido."],
        },
    ),
    "acc_big": (
        ACCOUNTS_URL,
        {"name": "x", "type": "bank", "initial_balance": 1e20},
        {"initial_balance": ["Asegúrese de que no haya más de 14 dígitos en total."]},
    ),
    "acc_inf": (
        ACCOUNTS_URL,
        {"name": "x", "type": "bank", "initial_balance": "Infinity"},
        {"initial_balance": ["Se requiere un número válido."]},
    ),
    "tx_empty": (
        TRANSACTIONS_URL,
        {},
        {
            "account_id": [REQUIRED],
            "amount": [REQUIRED],
            "type": [REQUIRED],
            "occurred_on": [REQUIRED],
        },
    ),
    "tx_bad": (
        TRANSACTIONS_URL,
        {
            "account_id": "nope",
            "amount": "x",
            "type": "transfer",
            "occurred_on": "2026-13-01",
            "description": 5,
            "category_name": "",
        },
        {
            "account_id": ["Debe ser un UUID válido."],
            "amount": ["Se requiere un número válido."],
            "type": ['"transfer" no es una elección válida.'],
            "occurred_on": [INVALID_DATE],
            "category_name": [BLANK],
        },
    ),
    "tx_bad2": (
        TRANSACTIONS_URL,
        {
            "account_id": 12,
            "amount": "1.999",
            "type": "income",
            "occurred_on": "2026-10-01T10:00:00",
            "description": None,
            "category_name": None,
        },
        {
            "amount": ["Asegúrese de que no haya más de 2 decimales."],
            "occurred_on": [INVALID_DATE],
            "description": [NULL],
            "category_name": [NULL],
        },
    ),
    "tx_bad3": (
        TRANSACTIONS_URL,
        {
            "account_id": None,
            "amount": None,
            "type": "",
            "occurred_on": None,
            "description": "d" * 256,
            "category_name": "c" * 81,
        },
        {
            "account_id": [NULL],
            "amount": [NULL],
            "type": ['"" no es una elección válida.'],
            "occurred_on": [NULL],
            "description": ["Asegúrese de que este campo no tenga más de 255 caracteres."],
            "category_name": ["Asegúrese de que este campo no tenga más de 80 caracteres."],
        },
    ),
    "tx_bad4": (
        TRANSACTIONS_URL,
        {"account_id": "", "amount": "", "occurred_on": "", "description": "  "},
        {
            "account_id": ["Debe ser un UUID válido."],
            "amount": ["Se requiere un número válido."],
            "type": [REQUIRED],
            "occurred_on": [INVALID_DATE],
        },
    ),
    "tx_bad5": (
        TRANSACTIONS_URL,
        {
            "account_id": "550e8400e29b41d4a716446655440000",
            "amount": 10,
            "type": "income",
            "occurred_on": 20261001,
        },
        {"occurred_on": [INVALID_DATE]},
    ),
    "rename_list": (
        f"{ACCOUNTS_URL}{uuid4()}/",
        [],
        {"non_field_errors": ["Datos inválidos. Se esperaba un diccionario pero es un list."]},
    ),
    "rename_str": (
        f"{ACCOUNTS_URL}{uuid4()}/",
        "hola",
        {"non_field_errors": ["Datos inválidos. Se esperaba un diccionario pero es un str."]},
    ),
}


@pytest.mark.parametrize("case", sorted(VALIDATION_CASES))
def test_los_errores_de_validacion_son_los_de_drf(ana, case):
    url, body, expected = VALIDATION_CASES[case]
    send = ana.put if case.startswith("rename") else ana.post

    respuesta = send(url, body)

    assert respuesta.status_code == 400
    assert respuesta.json == expected
    # El orden de los campos tambien es el de DRF: el de declaracion.
    assert list(respuesta.json) == list(expected)


def test_un_cuerpo_null_responde_no_data_provided(ana):
    respuesta = ana.post(ACCOUNTS_URL, data="null", content_type="application/json")
    assert respuesta.status_code == 400
    assert respuesta.json == {"non_field_errors": ["No data provided"]}


def test_los_filtros_mal_formados_tienen_los_mensajes_de_drf(ana):
    respuesta = ana.get(
        f"{TRANSACTIONS_URL}?account_id=x&category_id=&date_from=ayer&date_to="
    )
    assert respuesta.status_code == 400
    assert respuesta.json == {
        "account_id": ["Debe ser un UUID válido."],
        "category_id": ["Debe ser un UUID válido."],
        "date_from": [INVALID_DATE],
        "date_to": [INVALID_DATE],
    }


class TestRespuestasHttp:
    def test_401_lleva_www_authenticate(self, anonimo):
        respuesta = anonimo.get(ACCOUNTS_URL)
        assert respuesta.status_code == 401
        assert respuesta.headers["WWW-Authenticate"] == "Token"

    def test_sin_identidad_un_metodo_no_permitido_da_401_y_no_405(self, anonimo):
        """Como DRF: la autenticacion corre antes que el despacho por metodo."""
        assert anonimo.post(CATEGORIES_URL, {}).status_code == 401

    def test_405_con_el_mensaje_de_drf(self, ana):
        respuesta = ana.post(CATEGORIES_URL, {})
        assert respuesta.status_code == 405
        assert respuesta.json == {"detail": 'Método "POST" no permitido.'}

    def test_categoria_con_id_invalido_da_404_detail(self, ana):
        respuesta = ana.get(f"{CATEGORIES_URL}no-es-un-uuid/")
        assert respuesta.status_code == 404
        assert respuesta.json == {"detail": "No encontrado."}

    def test_detalle_de_cuenta_inexistente_da_el_404_de_django(self, ana):
        """Como `get_object_or_404`: con id valido, el mensaje de Django."""
        respuesta = ana.get(f"{ACCOUNTS_URL}{uuid4()}/")
        assert respuesta.status_code == 404
        assert respuesta.json == {"detail": "No Account matches the given query."}

    def test_detalle_de_cuenta_con_id_mal_formado_da_no_encontrado(self, ana):
        respuesta = ana.get(f"{ACCOUNTS_URL}no-es-un-uuid/")
        assert respuesta.json == {"detail": "No encontrado."}

    def test_categoria_inexistente_da_el_404_de_django(self, ana):
        respuesta = ana.get(f"{CATEGORIES_URL}{uuid4()}/")
        assert respuesta.json == {"detail": "No Category matches the given query."}

    def test_archivar_cuenta_inexistente_da_el_error_de_dominio(self, ana):
        respuesta = ana.post(f"{ACCOUNTS_URL}{uuid4()}/archive/")
        assert respuesta.status_code == 404
        assert respuesta.json["error"]["code"] == "account_not_found"

    def test_una_cuenta_archivada_no_aparece_en_su_detalle(self, ana):
        cuenta = ana.post(ACCOUNTS_URL, {"name": "Vieja", "type": "bank"}).json
        ana.post(f"{ACCOUNTS_URL}{cuenta['id']}/archive/")

        assert ana.get(f"{ACCOUNTS_URL}{cuenta['id']}/").status_code == 404
        con_flag = ana.get(f"{ACCOUNTS_URL}{cuenta['id']}/?include_archived=1")
        assert con_flag.status_code == 200

    def test_uuid_en_mayusculas_en_transacciones_da_404(self, ana):
        """El convertidor `<uuid:pk>` de Django solo acepta minusculas."""
        respuesta = ana.get(f"{TRANSACTIONS_URL}{str(uuid4()).upper()}/")
        assert respuesta.status_code == 404

    def test_json_mal_formado(self, ana):
        respuesta = ana.post(ACCOUNTS_URL, data="{", content_type="application/json")
        assert respuesta.status_code == 400
        assert respuesta.json["detail"].startswith("JSON parse error - ")

    def test_nan_literal_es_json_invalido(self, ana):
        respuesta = ana.post(
            ACCOUNTS_URL,
            data='{"name": "x", "type": "bank", "initial_balance": NaN}',
            content_type="application/json",
        )
        assert respuesta.status_code == 400
        assert "Out of range float values are not JSON compliant" in respuesta.json["detail"]

    def test_un_cuerpo_que_no_es_json_da_415(self, ana):
        respuesta = ana.post(ACCOUNTS_URL, data="hola", content_type="text/plain")
        assert respuesta.status_code == 415
        assert respuesta.json == {
            "detail": 'Tipo de medio "text/plain" incompatible en la solicitud.'
        }

    def test_sin_cuerpo_cuenta_como_objeto_vacio(self, ana):
        respuesta = ana.post(ACCOUNTS_URL)
        assert respuesta.json == {"name": [REQUIRED], "type": [REQUIRED]}

    def test_el_json_sale_en_utf8_sin_escapar(self, ana):
        cuerpo = ana.get(CATEGORIES_URL).get_data(as_text=True)
        assert "Alimentación" in cuerpo


class TestPaginacion:
    @pytest.fixture
    def con_55(self, ana):
        cuenta = ana.post(
            ACCOUNTS_URL, {"name": "Banco", "type": "bank", "initial_balance": "1000000"}
        ).json
        ayer = (date.today() - timedelta(days=1)).isoformat()
        for _ in range(55):
            ana.post(
                TRANSACTIONS_URL,
                {"account_id": cuenta["id"], "amount": "1", "type": "income",
                 "occurred_on": ayer, "category_name": "Salario"},
            )
        return cuenta

    def test_enlaces_absolutos_y_parametros_ordenados(self, ana, con_55):
        primera = ana.get(f"{TRANSACTIONS_URL}?type=x&account_id={con_55['id']}").json

        assert primera["previous"] is None
        assert primera["next"] == (
            f"http://localhost{TRANSACTIONS_URL}?account_id={con_55['id']}&page=2&type=x"
        )

    def test_la_pagina_2_enlaza_a_la_1_sin_parametro(self, ana, con_55):
        segunda = ana.get(f"{TRANSACTIONS_URL}?page=2").json
        assert segunda["next"] is None
        assert segunda["previous"] == f"http://localhost{TRANSACTIONS_URL}"

    def test_page_last(self, ana, con_55):
        assert len(ana.get(f"{TRANSACTIONS_URL}?page=last").json["results"]) == 5

    @pytest.mark.parametrize("pagina", ["0", "3", "x", "1.5"])
    def test_pagina_invalida(self, ana, con_55, pagina):
        respuesta = ana.get(f"{TRANSACTIONS_URL}?page={pagina}")
        assert respuesta.status_code == 404
        assert respuesta.json == {"detail": "Página inválida."}

    def test_sin_filas_la_pagina_1_existe(self, ana):
        cuerpo = ana.get(ACCOUNTS_URL).json
        assert cuerpo == {"count": 0, "next": None, "previous": None, "results": []}


class TestFormatoDeSalida:
    def test_created_at_en_la_zona_de_bogota(self, ana):
        cuenta = ana.post(ACCOUNTS_URL, {"name": "Banco", "type": "bank"}).json
        assert cuenta["created_at"].endswith("-05:00")

    def test_el_orden_de_los_campos_es_el_del_serializer(self, ana):
        cuenta = ana.post(ACCOUNTS_URL, {"name": "Banco", "type": "bank"}).json
        assert list(cuenta) == [
            "id", "name", "type", "balance", "opening_balance",
            "currency", "is_archived", "created_at",
        ]


class TestSufijoDeFormato:
    """Las variantes `.json` que publicaba `DefaultRouter` en el monolito."""

    @pytest.fixture
    def cuenta(self, ana):
        return ana.post(ACCOUNTS_URL, {"name": "Banco", "type": "bank"}).json

    @pytest.mark.parametrize("ruta", ["/api/v1/accounts.json", "/api/v1/accounts.json/"])
    def test_listado_de_cuentas(self, ana, cuenta, ruta):
        respuesta = ana.get(ruta)
        assert respuesta.status_code == 200
        assert respuesta.json["results"] == ana.get(ACCOUNTS_URL).json["results"]

    def test_detalle_de_cuenta(self, ana, cuenta):
        respuesta = ana.get(f"/api/v1/accounts/{cuenta['id']}.json")
        assert respuesta.json == ana.get(f"{ACCOUNTS_URL}{cuenta['id']}/").json

    def test_archivar_con_sufijo(self, ana, cuenta):
        respuesta = ana.post(f"/api/v1/accounts/{cuenta['id']}/archive.json")
        assert respuesta.status_code == 200
        assert respuesta.json["is_archived"] is True

    def test_categorias_con_sufijo(self, ana):
        assert ana.get("/api/v1/categories.json").json["count"] == 15

    @pytest.mark.parametrize(
        "ruta", ["/api/v1/transactions.json", "/api/v1/accounts.xml", "/api/v1/accounts.api"]
    )
    def test_sin_variante_da_404(self, ana, ruta):
        assert ana.get(ruta).status_code == 404

    def test_el_sufijo_tambien_exige_identidad(self, anonimo):
        assert anonimo.get("/api/v1/accounts.json").status_code == 401
