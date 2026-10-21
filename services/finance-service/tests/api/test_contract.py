"""Tests del contrato REST de `finance-service`.

Portados de `finance/tests/test_api.py` del monolito, con las mismas clases y las
mismas aserciones: son la evidencia de que el servicio Flask cumple el contrato
`/api/v1/` que hoy sirve Django (A-20). Cambia el andamiaje:

- La identidad llega en `X-User-Id` (lo que pondra el Gateway), no con un token.
- Las comprobaciones contra la base usan la sesion SQLAlchemy de la fixture.
- El proveedor de categorizacion se conmuta con la variable de entorno.

Tocan la base de datos de pruebas (ver `tests/conftest.py`).
"""
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

import messages
from models import Account, Category, Transaction

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)

ACCOUNTS_URL = "/api/v1/accounts/"
CATEGORIES_URL = "/api/v1/categories/"
TRANSACTIONS_URL = "/api/v1/transactions/"

NOT_AUTHENTICATED = messages.NOT_AUTHENTICATED


def crear_cuenta(client, name="Cuenta corriente", tipo="bank", **extra):
    """Crea una cuenta por HTTP y devuelve el cuerpo de la respuesta."""
    payload = {"name": name, "type": tipo, "currency": "COP"}
    payload.update(extra)
    respuesta = client.post(ACCOUNTS_URL, payload)
    assert respuesta.status_code == 201, respuesta.get_data(as_text=True)
    return respuesta.json


def crear_transaccion(client, account_id, amount="120000", tipo="expense", **extra):
    """Registra una transaccion por HTTP y devuelve la respuesta cruda."""
    payload = {
        "account_id": account_id,
        "amount": amount,
        "type": tipo,
        "occurred_on": extra.pop("occurred_on", YESTERDAY).isoformat(),
    }
    payload.update(extra)
    return client.post(TRANSACTIONS_URL, payload)


def categoria_por_nombre(session, name):
    """Categoria del catalogo sembrado por la migracion 0002."""
    return session.execute(select(Category).where(Category.name == name)).scalar_one()


@pytest.fixture
def cuenta(ana):
    return crear_cuenta(ana, initial_balance="1000000.00")


class TestFlujoCompleto:
    """El diagrama de secuencia de ARCHITECTURE.md 9.2, ejecutado por HTTP."""

    def test_recorrido_de_extremo_a_extremo(self, client_for):
        # 1. Registro y acceso son de `identity` (Django). Aqui el usuario llega
        #    ya identificado por el Gateway en `X-User-Id`.
        autenticado = client_for(uuid4())

        # 2. Crear cuenta con saldo de apertura.
        cuenta = crear_cuenta(autenticado, initial_balance="1000000.00")
        assert cuenta["balance"] == "1000000.00"
        assert cuenta["opening_balance"] == "1000000.00"

        # 3. Tres transacciones mezcladas.
        gasto_uno = crear_transaccion(
            autenticado, cuenta["id"], "120000", "expense", description="Mercado"
        )
        gasto_dos = crear_transaccion(
            autenticado, cuenta["id"], "35000", "expense", description="Taxi al centro"
        )
        ingreso = crear_transaccion(
            autenticado, cuenta["id"], "500000", "income", description="Pago de nomina"
        )
        assert [gasto_uno.status_code, gasto_dos.status_code, ingreso.status_code] == [
            201,
            201,
            201,
        ]

        # 4. Listar.
        listado = autenticado.get(TRANSACTIONS_URL)
        assert listado.status_code == 200
        assert listado.json["count"] == 3

        # 5. Recategorizar una.
        recategorizada = autenticado.post(
            f"{TRANSACTIONS_URL}{gasto_uno.json['id']}/categorize/",
            {"category_name": "Compras"},
        )
        assert recategorizada.status_code == 200
        assert recategorizada.json["category_name"] == "Compras"
        assert recategorizada.json["categorization_source"] == "manual"

        # 6. Eliminar otra.
        borrada = autenticado.delete(f"{TRANSACTIONS_URL}{gasto_dos.json['id']}/")
        assert borrada.status_code == 204

        # 7. El balance refleja exactamente lo que queda.
        final = autenticado.get(f"{ACCOUNTS_URL}{cuenta['id']}/")
        assert final.status_code == 200
        # 1.000.000 - 120.000 + 500.000 = 1.380.000
        assert final.json["balance"] == "1380000.00"
        assert final.json["opening_balance"] == "1000000.00"
        assert autenticado.get(TRANSACTIONS_URL).json["count"] == 2


class TestCuentasCodigosDeEstado:
    """`/api/v1/accounts/`."""

    def test_crear_devuelve_201(self, ana):
        respuesta = ana.post(
            ACCOUNTS_URL, {"name": "Ahorros", "type": "bank"}
        )
        assert respuesta.status_code == 201

    def test_nombre_duplicado_devuelve_409(self, ana, cuenta):
        respuesta = ana.post(
            ACCOUNTS_URL, {"name": "Cuenta corriente", "type": "cash"}
        )

        assert respuesta.status_code == 409
        assert respuesta.json["error"]["code"] == "duplicate_account_name"

    def test_balance_inicial_negativo_en_cash_devuelve_409(self, ana):
        respuesta = ana.post(
            ACCOUNTS_URL,
            {"name": "Efectivo", "type": "cash", "initial_balance": "-1.00"},
        )

        assert respuesta.status_code == 409
        assert respuesta.json["error"]["code"] == "negative_balance_not_allowed"

    def test_balance_inicial_negativo_en_credit_procede(self, ana):
        respuesta = ana.post(
            ACCOUNTS_URL,
            {"name": "Tarjeta", "type": "credit", "initial_balance": "-500000.00"},
        )

        assert respuesta.status_code == 201
        assert respuesta.json["balance"] == "-500000.00"

    def test_tipo_invalido_devuelve_400(self, ana):
        respuesta = ana.post(
            ACCOUNTS_URL, {"name": "Rara", "type": "crypto"}
        )
        assert respuesta.status_code == 400

    def test_renombrar_devuelve_200(self, ana, cuenta):
        respuesta = ana.put(
            f"{ACCOUNTS_URL}{cuenta['id']}/", {"name": "Nomina"}
        )

        assert respuesta.status_code == 200
        assert respuesta.json["name"] == "Nomina"

    def test_renombrar_no_cambia_el_tipo_ni_la_moneda(self, ana, cuenta):
        respuesta = ana.put(
            f"{ACCOUNTS_URL}{cuenta['id']}/",
            {"name": "Nomina", "type": "cash", "currency": "USD"},
        )

        assert respuesta.json["type"] == "bank"
        assert respuesta.json["currency"] == "COP"

    def test_renombrar_a_un_nombre_ocupado_devuelve_409(self, ana, cuenta):
        crear_cuenta(ana, name="Ahorros", tipo="cash")

        respuesta = ana.put(
            f"{ACCOUNTS_URL}{cuenta['id']}/", {"name": "Ahorros"}
        )
        assert respuesta.status_code == 409

    def test_archivar_devuelve_200(self, ana, cuenta):
        respuesta = ana.post(f"{ACCOUNTS_URL}{cuenta['id']}/archive/")

        assert respuesta.status_code == 200
        assert respuesta.json["is_archived"] is True

    def test_una_cuenta_archivada_desaparece_del_listado(self, ana, cuenta):
        ana.post(f"{ACCOUNTS_URL}{cuenta['id']}/archive/")

        assert ana.get(ACCOUNTS_URL).json["count"] == 0

    def test_include_archived_la_devuelve(self, ana, cuenta):
        ana.post(f"{ACCOUNTS_URL}{cuenta['id']}/archive/")

        assert ana.get(f"{ACCOUNTS_URL}?include_archived=true").json["count"] == 1

    def test_borrar_con_transacciones_devuelve_409(self, ana, cuenta):
        crear_transaccion(ana, cuenta["id"])

        respuesta = ana.delete(f"{ACCOUNTS_URL}{cuenta['id']}/")

        assert respuesta.status_code == 409
        assert respuesta.json["error"]["code"] == "account_has_transactions"

    def test_borrar_sin_transacciones_devuelve_204(self, ana, cuenta, session):
        respuesta = ana.delete(f"{ACCOUNTS_URL}{cuenta['id']}/")

        assert respuesta.status_code == 204
        assert session.get(Account, UUID(cuenta["id"])) is None

    def test_cuenta_ajena_devuelve_404(self, juan, cuenta):
        assert juan.get(f"{ACCOUNTS_URL}{cuenta['id']}/").status_code == 404

    def test_archivar_una_cuenta_ajena_devuelve_404(self, juan, cuenta):
        assert juan.post(f"{ACCOUNTS_URL}{cuenta['id']}/archive/").status_code == 404


class TestTransaccionesCodigosDeEstado:
    """`/api/v1/transactions/`."""

    def test_crear_devuelve_201(self, ana, cuenta):
        respuesta = crear_transaccion(ana, cuenta["id"])

        assert respuesta.status_code == 201
        assert respuesta.json["amount"] == "120000.00"

    def test_monto_cero_devuelve_422(self, ana, cuenta):
        respuesta = crear_transaccion(ana, cuenta["id"], "0")

        assert respuesta.status_code == 422
        assert respuesta.json["error"]["code"] == "zero_amount"

    def test_fecha_futura_devuelve_422(self, ana, cuenta):
        respuesta = crear_transaccion(ana, cuenta["id"], occurred_on=TOMORROW)

        assert respuesta.status_code == 422
        assert respuesta.json["error"]["code"] == "future_transaction_date"

    def test_cuenta_ajena_devuelve_404(self, juan, cuenta):
        respuesta = crear_transaccion(juan, cuenta["id"])

        assert respuesta.status_code == 404
        assert respuesta.json["error"]["code"] == "account_not_found"

    def test_categoria_inexistente_devuelve_404(self, ana, cuenta):
        respuesta = crear_transaccion(
            ana, cuenta["id"], category_name="Criptomonedas"
        )

        assert respuesta.status_code == 404
        assert respuesta.json["error"]["code"] == "category_not_found"

    def test_categoria_del_tipo_equivocado_devuelve_422(self, ana, cuenta):
        respuesta = crear_transaccion(
            ana, cuenta["id"], tipo="expense", category_name="Salario"
        )

        assert respuesta.status_code == 422
        assert respuesta.json["error"]["code"] == "category_type_mismatch"

    def test_gasto_que_deja_negativa_una_cuenta_cash_devuelve_409(self, ana):
        efectivo = crear_cuenta(ana, name="Efectivo", tipo="cash")

        respuesta = crear_transaccion(ana, efectivo["id"], "1")

        assert respuesta.status_code == 409
        assert respuesta.json["error"]["code"] == "negative_balance_not_allowed"

    def test_el_mismo_gasto_en_credit_devuelve_201(self, ana):
        tarjeta = crear_cuenta(ana, name="Tarjeta", tipo="credit")

        assert crear_transaccion(ana, tarjeta["id"], "1").status_code == 201

    def test_cuenta_archivada_devuelve_409(self, ana, cuenta):
        ana.post(f"{ACCOUNTS_URL}{cuenta['id']}/archive/")

        respuesta = crear_transaccion(ana, cuenta["id"])

        assert respuesta.status_code == 409
        assert respuesta.json["error"]["code"] == "archived_account"

    def test_monto_no_numerico_devuelve_400(self, ana, cuenta):
        respuesta = ana.post(
            TRANSACTIONS_URL,
            {
                "account_id": cuenta["id"],
                "amount": "mucho",
                "type": "expense",
                "occurred_on": YESTERDAY.isoformat(),
            },
        )
        assert respuesta.status_code == 400

    def test_tipo_invalido_devuelve_400(self, ana, cuenta):
        assert crear_transaccion(ana, cuenta["id"], tipo="transfer").status_code == 400

    def test_campos_faltantes_devuelve_400(self, ana):
        assert ana.post(TRANSACTIONS_URL, {}).status_code == 400

    def test_get_de_transaccion_propia_devuelve_200(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json

        assert ana.get(f"{TRANSACTIONS_URL}{creada['id']}/").status_code == 200

    def test_get_de_transaccion_ajena_devuelve_404(self, ana, juan, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json

        assert juan.get(f"{TRANSACTIONS_URL}{creada['id']}/").status_code == 404

    def test_delete_devuelve_204(self, ana, cuenta, session):
        creada = crear_transaccion(ana, cuenta["id"]).json

        respuesta = ana.delete(f"{TRANSACTIONS_URL}{creada['id']}/")

        assert respuesta.status_code == 204
        assert session.get(Transaction, UUID(creada["id"])) is None

    def test_delete_de_transaccion_ajena_devuelve_404(self, ana, juan, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json

        assert juan.delete(f"{TRANSACTIONS_URL}{creada['id']}/").status_code == 404

    def test_un_identificador_con_forma_invalida_devuelve_404(self, ana):
        """El convertidor `<uuid:pk>` corta antes de llegar a la vista."""
        assert ana.get(f"{TRANSACTIONS_URL}no-es-un-uuid/").status_code == 404


class TestRecategorizar:
    """`/api/v1/transactions/{id}/categorize/`."""

    def test_devuelve_200(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json

        respuesta = ana.post(
            f"{TRANSACTIONS_URL}{creada['id']}/categorize/",
            {"category_name": "Transporte"},
        )

        assert respuesta.status_code == 200
        assert respuesta.json["category_name"] == "Transporte"

    def test_no_mueve_el_balance(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json
        antes = ana.get(f"{ACCOUNTS_URL}{cuenta['id']}/").json["balance"]

        ana.post(
            f"{TRANSACTIONS_URL}{creada['id']}/categorize/",
            {"category_name": "Transporte"},
        )

        assert ana.get(f"{ACCOUNTS_URL}{cuenta['id']}/").json["balance"] == antes

    def test_categoria_del_tipo_equivocado_devuelve_422(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"], tipo="expense").json

        respuesta = ana.post(
            f"{TRANSACTIONS_URL}{creada['id']}/categorize/",
            {"category_name": "Salario"},
        )

        assert respuesta.status_code == 422
        assert respuesta.json["error"]["code"] == "category_type_mismatch"

    def test_de_una_transaccion_ajena_devuelve_404(self, ana, juan, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json

        respuesta = juan.post(
            f"{TRANSACTIONS_URL}{creada['id']}/categorize/",
            {"category_name": "Transporte"},
        )
        assert respuesta.status_code == 404

    def test_sin_category_name_devuelve_400(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json

        respuesta = ana.post(
            f"{TRANSACTIONS_URL}{creada['id']}/categorize/", {}
        )
        assert respuesta.status_code == 400


class TestCatalogoDeCategorias:
    """`/api/v1/categories/` es de solo lectura."""

    def test_listar_devuelve_200_con_las_quince(self, ana):
        respuesta = ana.get(CATEGORIES_URL)

        assert respuesta.status_code == 200
        assert respuesta.json["count"] == 15

    def test_detalle_devuelve_200(self, ana, session):
        categoria = categoria_por_nombre(session, "Alimentación")

        respuesta = ana.get(f"{CATEGORIES_URL}{categoria.id}/")

        assert respuesta.status_code == 200
        assert respuesta.json["applies_to"] == "expense"

    def test_expone_solo_los_tres_campos(self, ana):
        primera = ana.get(CATEGORIES_URL).json["results"][0]

        assert set(primera) == {"id", "name", "applies_to"}

    def test_post_devuelve_405(self, ana):
        respuesta = ana.post(
            CATEGORIES_URL, {"name": "Inventada", "applies_to": "expense"}
        )
        assert respuesta.status_code == 405

    def test_put_devuelve_405(self, ana, session):
        categoria = categoria_por_nombre(session, "Alimentación")

        respuesta = ana.put(
            f"{CATEGORIES_URL}{categoria.id}/", {"name": "Otra"}
        )
        assert respuesta.status_code == 405

    def test_delete_devuelve_405(self, ana, session):
        categoria = categoria_por_nombre(session, "Alimentación")

        assert ana.delete(f"{CATEGORIES_URL}{categoria.id}/").status_code == 405


class TestAutenticacionRequerida:
    """INV-01: sin `X-User-Id`, ningun endpoint de `finance` responde."""

    @pytest.fixture
    def ids(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json
        return {"cuenta": cuenta["id"], "transaccion": creada["id"]}

    def test_todos_los_endpoints_devuelven_401(self, anonimo, ids):
        peticiones = [
            ("get", ACCOUNTS_URL, None),
            ("post", ACCOUNTS_URL, {"name": "x", "type": "cash"}),
            ("get", f"{ACCOUNTS_URL}{ids['cuenta']}/", None),
            ("put", f"{ACCOUNTS_URL}{ids['cuenta']}/", {"name": "x"}),
            ("delete", f"{ACCOUNTS_URL}{ids['cuenta']}/", None),
            ("post", f"{ACCOUNTS_URL}{ids['cuenta']}/archive/", None),
            ("get", CATEGORIES_URL, None),
            ("get", TRANSACTIONS_URL, None),
            ("post", TRANSACTIONS_URL, {}),
            ("get", f"{TRANSACTIONS_URL}{ids['transaccion']}/", None),
            ("delete", f"{TRANSACTIONS_URL}{ids['transaccion']}/", None),
            ("post", f"{TRANSACTIONS_URL}{ids['transaccion']}/categorize/", {}),
        ]
        for metodo, url, cuerpo in peticiones:
            invocar = getattr(anonimo, metodo)
            respuesta = invocar(url, cuerpo) if cuerpo is not None else invocar(url)
            assert respuesta.status_code == 401, f"{metodo.upper()} {url}"
            assert respuesta.json == {"detail": NOT_AUTHENTICATED}

    def test_un_x_user_id_que_no_es_uuid_tambien_devuelve_401(self, anonimo):
        respuesta = anonimo.get(ACCOUNTS_URL, headers={"X-User-Id": "no-es-un-uuid"})

        assert respuesta.status_code == 401


class TestAislamientoEntreUsuarios:
    """Ningun camino lleva a datos ajenos."""

    def test_listado_de_cuentas(self, ana, juan, cuenta):
        assert ana.get(ACCOUNTS_URL).json["count"] == 1
        assert juan.get(ACCOUNTS_URL).json["count"] == 0

    def test_listado_de_transacciones(self, ana, juan, cuenta):
        crear_transaccion(ana, cuenta["id"])

        assert ana.get(TRANSACTIONS_URL).json["count"] == 1
        assert juan.get(TRANSACTIONS_URL).json["count"] == 0

    def test_ninguna_cuenta_expone_el_campo_user(self, ana, cuenta):
        assert "user" not in cuenta
        assert "user" not in ana.get(f"{ACCOUNTS_URL}{cuenta['id']}/").json

    def test_ninguna_transaccion_expone_el_campo_user(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json

        assert "user" not in creada
        assert "user" not in str(creada.get("account_name", ""))

    def test_filtrar_por_una_cuenta_ajena_devuelve_vacio_no_403(self, ana, juan, cuenta):
        """Un 403 confirmaria que ese identificador existe."""
        crear_transaccion(ana, cuenta["id"])

        respuesta = juan.get(f"{TRANSACTIONS_URL}?account_id={cuenta['id']}")

        assert respuesta.status_code == 200
        assert respuesta.json["count"] == 0

    def test_cada_uno_ve_su_propio_balance(self, ana, juan, cuenta):
        suya = crear_cuenta(juan, name="Cuenta corriente", initial_balance="7.00")

        assert ana.get(f"{ACCOUNTS_URL}{cuenta['id']}/").json["balance"] == "1000000.00"
        assert juan.get(f"{ACCOUNTS_URL}{suya['id']}/").json["balance"] == "7.00"


class TestPaginacionYFiltros:
    """`GET /transactions/`."""

    def test_mas_de_cincuenta_transacciones(self, ana, cuenta):
        for _ in range(55):
            crear_transaccion(ana, cuenta["id"], "1000", "income", category_name="Salario")

        respuesta = ana.get(TRANSACTIONS_URL)
        cuerpo = respuesta.json

        assert cuerpo["count"] == 55
        assert len(cuerpo["results"]) == 50
        assert cuerpo["next"] is not None
        assert cuerpo["previous"] is None

    def test_la_segunda_pagina_trae_el_resto(self, ana, cuenta):
        for _ in range(55):
            crear_transaccion(ana, cuenta["id"], "1000", "income", category_name="Salario")

        segunda = ana.get(f"{TRANSACTIONS_URL}?page=2").json

        assert len(segunda["results"]) == 5
        assert segunda["previous"] is not None

    def test_filtro_por_cuenta(self, ana, cuenta):
        otra = crear_cuenta(ana, name="Otra", tipo="credit")
        crear_transaccion(ana, cuenta["id"])
        crear_transaccion(ana, otra["id"])

        respuesta = ana.get(f"{TRANSACTIONS_URL}?account_id={cuenta['id']}")

        assert respuesta.json["count"] == 1

    def test_filtro_por_categoria(self, ana, cuenta, session):
        crear_transaccion(ana, cuenta["id"], category_name="Transporte")
        crear_transaccion(ana, cuenta["id"], category_name="Compras")
        transporte = categoria_por_nombre(session, "Transporte")

        respuesta = ana.get(f"{TRANSACTIONS_URL}?category_id={transporte.id}")

        assert respuesta.json["count"] == 1

    def test_filtro_por_rango_de_fechas(self, ana, cuenta):
        crear_transaccion(ana, cuenta["id"], occurred_on=date(2026, 1, 15))
        crear_transaccion(ana, cuenta["id"], occurred_on=date(2026, 3, 10))
        crear_transaccion(ana, cuenta["id"], occurred_on=date(2026, 5, 20))

        respuesta = ana.get(
            f"{TRANSACTIONS_URL}?date_from=2026-02-01&date_to=2026-04-01"
        )

        assert respuesta.json["count"] == 1

    def test_una_fecha_mal_formada_devuelve_400(self, ana):
        assert ana.get(f"{TRANSACTIONS_URL}?date_from=ayer").status_code == 400

    def test_un_account_id_mal_formado_devuelve_400(self, ana):
        assert ana.get(f"{TRANSACTIONS_URL}?account_id=xxx").status_code == 400


class TestContratoDeSerializacion:
    """La forma exacta de las respuestas es parte del contrato."""

    def test_el_monto_sale_como_cadena_decimal(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"], "120000.55").json

        assert creada["amount"] == "120000.55"
        assert isinstance(creada["amount"], str)
        assert not isinstance(creada["amount"], float)

    def test_el_balance_sale_como_cadena_decimal(self, cuenta):
        assert cuenta["balance"] == "1000000.00"
        assert isinstance(cuenta["balance"], str)

    def test_la_cuenta_expone_exactamente_los_campos_listados(self, cuenta):
        assert set(cuenta) == {
            "id",
            "name",
            "type",
            "balance",
            "opening_balance",
            "currency",
            "is_archived",
            "created_at",
        }

    def test_la_transaccion_expone_exactamente_los_campos_listados(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"]).json

        assert set(creada) == {
            "id",
            "account",
            "account_name",
            "amount",
            "type",
            "category",
            "category_name",
            "description",
            "occurred_on",
            "categorization_source",
            "categorization_confidence",
            "created_at",
        }

    def test_las_relaciones_vienen_aplanadas(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"], category_name="Transporte").json

        assert creada["account"] == cuenta["id"]
        assert creada["account_name"] == "Cuenta corriente"
        assert creada["category_name"] == "Transporte"

    def test_una_transaccion_sin_categoria_no_rompe_la_salida(self, ana, cuenta, session):
        """La categoria es opcional en el modelo; el serializer lo tolera."""
        creada = crear_transaccion(ana, cuenta["id"]).json
        session.execute(
            update(Transaction)
            .where(Transaction.id == UUID(creada["id"]))
            .values(
                category_id=None,
                categorization_source=None,
                categorization_confidence=None,
            )
        )
        session.commit()

        respuesta = ana.get(f"{TRANSACTIONS_URL}{creada['id']}/")

        assert respuesta.status_code == 200
        assert respuesta.json["category"] is None
        assert respuesta.json["category_name"] is None

    def test_el_error_de_dominio_sale_con_el_formato_uniforme(self, ana, cuenta):
        cuerpo = crear_transaccion(ana, cuenta["id"], "0").json

        assert set(cuerpo) == {"error"}
        assert set(cuerpo["error"]) == {"code", "message"}


class TestCategorizacionRemota:
    """Lo que antes conmutaba `CATEGORIZER_PROVIDER` aqui, ahora lo decide
    `categorization-service` (E2-M3b). Estos tests fijan que la respuesta del
    remoto llega intacta a la transaccion, y que sin el actua el respaldo.
    """

    def test_con_el_remoto_en_mock_la_categoria_la_pone_el_mock(self, ana, cuenta, categorization):
        categorization.mode = "mock"
        creada = crear_transaccion(ana, cuenta["id"], description="Almuerzo en el restaurante").json

        assert creada["category_name"] == "Otros gastos"
        assert creada["categorization_source"] == "mock"
        assert creada["categorization_confidence"] == 1.0

    def test_con_el_remoto_en_reglas_la_categoria_la_ponen_las_reglas(self, ana, cuenta):
        creada = crear_transaccion(ana, cuenta["id"], description="Almuerzo en el restaurante").json

        assert creada["category_name"] == "Alimentación"
        assert creada["categorization_source"] == "rule"
        assert creada["categorization_confidence"] == 0.75

    def test_un_ingreso_se_clasifica_con_el_mapa_de_ingresos(self, ana, cuenta):
        creada = crear_transaccion(
            ana, cuenta["id"], "500000", "income", description="Pago de nomina"
        ).json

        assert creada["category_name"] == "Salario"

    def test_el_mismo_request_da_resultados_distintos_segun_el_remoto(self, ana, cuenta, categorization):
        """A-13 visto desde finance-service: mismo cuerpo, mismo codigo."""
        con_reglas = crear_transaccion(ana, cuenta["id"], description="Almuerzo en el restaurante").json
        categorization.mode = "mock"
        con_mock = crear_transaccion(ana, cuenta["id"], description="Almuerzo en el restaurante").json

        assert (con_reglas["category_name"], con_reglas["categorization_source"]) == ("Alimentación", "rule")
        assert (con_mock["category_name"], con_mock["categorization_source"]) == ("Otros gastos", "mock")

    def test_con_el_remoto_caido_registra_igual_con_el_respaldo(self, app, ana, cuenta):
        """A-22: sin categorization-service la transaccion se registra, con `rule`."""
        app.config["CATEGORIZATION_URL"] = "http://127.0.0.1:9"

        respuesta = crear_transaccion(ana, cuenta["id"], description="Almuerzo en el restaurante")

        assert respuesta.status_code == 201
        assert respuesta.json["category_name"] == "Alimentación"
        assert respuesta.json["categorization_source"] == "rule"

    def test_con_categoria_manual_no_se_consulta_el_remoto(self, ana, cuenta, categorization):
        crear_transaccion(ana, cuenta["id"], category_name="Compras")
        assert categorization.requests == []
