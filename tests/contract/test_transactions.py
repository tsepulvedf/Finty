"""`/api/v1/transactions/`: registro, categorizacion, filtros, paginacion y errores."""
import uuid

import pytest

from helpers import (
    ACCOUNTS,
    INVALID_DATE,
    INVALID_NUMBER,
    INVALID_PAGE,
    INVALID_UUID,
    REQUIRED,
    TOMORROW,
    TRANSACTION_FIELDS,
    TRANSACTIONS,
    YESTERDAY,
    create_account,
    error_code,
    method_not_allowed,
    register,
)


@pytest.fixture
def cuenta(ana):
    return create_account(ana, initial_balance="1000000")


def balance(user, account):
    return user.client.get(f"{ACCOUNTS}{account['id']}/").json["balance"]


class TestRegistrar:
    def test_201_con_los_campos_del_contrato_en_orden(self, ana, cuenta):
        response = register(ana, cuenta["id"], "120000.55", description="Almuerzo en el restaurante")

        assert response.status == 201
        body = response.json
        assert list(body) == TRANSACTION_FIELDS
        assert (body["account"], body["account_name"]) == (cuenta["id"], cuenta["name"])
        assert (body["amount"], body["type"], body["occurred_on"]) == ("120000.55", "expense", YESTERDAY)
        assert (body["category_name"], body["categorization_source"]) == ("Alimentación", "rule")
        assert body["categorization_confidence"] == 0.75
        assert body["created_at"].endswith("-05:00")

    def test_un_gasto_resta_y_un_ingreso_suma(self, ana, cuenta):
        register(ana, cuenta["id"], "120000", "expense")
        register(ana, cuenta["id"], "500000", "income", description="Pago de nomina")
        assert balance(ana, cuenta) == "1380000.00"

    def test_ingreso_clasificado_por_reglas(self, ana, cuenta):
        body = register(ana, cuenta["id"], "500000", "income", description="Pago de nomina").json
        assert body["category_name"] == "Salario"

    def test_categoria_manual(self, ana, cuenta):
        body = register(ana, cuenta["id"], category_name="Compras").json
        assert (body["category_name"], body["categorization_source"]) == ("Compras", "manual")
        assert body["categorization_confidence"] == 1.0

    @pytest.mark.parametrize(
        "extra,status,code",
        [
            ({"amount": "0"}, 422, "zero_amount"),
            ({"occurred_on": TOMORROW}, 422, "future_transaction_date"),
            ({"category_name": "Salario"}, 422, "category_type_mismatch"),
            ({"category_name": "Criptomonedas"}, 404, "category_not_found"),
        ],
    )
    def test_errores_de_dominio(self, ana, cuenta, extra, status, code):
        response = register(ana, cuenta["id"], **extra)
        assert (response.status, error_code(response)) == (status, code)
        assert balance(ana, cuenta) == "1000000.00"

    def test_efectivo_no_queda_en_negativo(self, ana):
        efectivo = create_account(ana, kind="cash")
        response = register(ana, efectivo["id"], "1")
        assert (response.status, error_code(response)) == (409, "negative_balance_not_allowed")

    def test_credito_si(self, ana):
        tarjeta = create_account(ana, kind="credit")
        assert register(ana, tarjeta["id"], "1").status == 201

    def test_cuenta_archivada(self, ana, cuenta):
        ana.client.post(f"{ACCOUNTS}{cuenta['id']}/archive/")
        response = register(ana, cuenta["id"])
        assert (response.status, error_code(response)) == (409, "archived_account")

    def test_cuenta_inexistente(self, ana):
        response = register(ana, str(uuid.uuid4()))
        assert (response.status, error_code(response)) == (404, "account_not_found")

    def test_validacion_400_con_los_mensajes_de_drf(self, ana):
        response = ana.client.post(
            TRANSACTIONS,
            {"account_id": "nope", "amount": "x", "type": "transfer", "occurred_on": "2026-13-01"},
        )
        assert response.status == 400
        assert response.json == {
            "account_id": [INVALID_UUID],
            "amount": [INVALID_NUMBER],
            "type": ['"transfer" no es una elección válida.'],
            "occurred_on": [INVALID_DATE],
        }

    def test_campos_faltantes(self, ana):
        response = ana.client.post(TRANSACTIONS, {})
        assert response.json == {
            "account_id": [REQUIRED], "amount": [REQUIRED], "type": [REQUIRED], "occurred_on": [REQUIRED],
        }


class TestConsultarRecategorizarEliminar:
    def test_detalle(self, ana, cuenta):
        created = register(ana, cuenta["id"]).json
        assert ana.client.get(f"{TRANSACTIONS}{created['id']}/").json == created

    def test_detalle_inexistente(self, ana):
        response = ana.client.get(f"{TRANSACTIONS}{uuid.uuid4()}/")
        assert (response.status, error_code(response)) == (404, "transaction_not_found")

    def test_identificador_con_forma_invalida_404(self, ana):
        """Solo el codigo: el cuerpo de una ruta que no existe no es contrato."""
        assert ana.client.get(f"{TRANSACTIONS}no-es-un-uuid/").status == 404

    def test_recategorizar_no_mueve_el_balance(self, ana, cuenta):
        created = register(ana, cuenta["id"]).json
        before = balance(ana, cuenta)

        response = ana.client.post(f"{TRANSACTIONS}{created['id']}/categorize/", {"category_name": "Transporte"})

        assert response.status == 200
        assert (response.json["category_name"], response.json["categorization_source"]) == ("Transporte", "manual")
        assert balance(ana, cuenta) == before

    def test_recategorizar_sin_categoria(self, ana, cuenta):
        created = register(ana, cuenta["id"]).json
        response = ana.client.post(f"{TRANSACTIONS}{created['id']}/categorize/", {})
        assert (response.status, response.json) == (400, {"category_name": [REQUIRED]})

    def test_recategorizar_con_tipo_equivocado(self, ana, cuenta):
        created = register(ana, cuenta["id"]).json
        response = ana.client.post(f"{TRANSACTIONS}{created['id']}/categorize/", {"category_name": "Salario"})
        assert (response.status, error_code(response)) == (422, "category_type_mismatch")

    def test_eliminar_deshace_el_balance(self, ana, cuenta):
        created = register(ana, cuenta["id"], "100").json
        response = ana.client.delete(f"{TRANSACTIONS}{created['id']}/")
        assert (response.status, response.text) == (204, "")
        assert balance(ana, cuenta) == "1000000.00"
        assert ana.client.get(f"{TRANSACTIONS}{created['id']}/").status == 404

    def test_metodos_no_permitidos(self, ana, cuenta):
        created = register(ana, cuenta["id"]).json
        put = ana.client.put(f"{TRANSACTIONS}{created['id']}/", {})
        get = ana.client.get(f"{TRANSACTIONS}{created['id']}/categorize/")
        delete = ana.client.delete(TRANSACTIONS)
        assert (put.status, put.json) == (405, method_not_allowed("PUT"))
        assert (get.status, get.json) == (405, method_not_allowed("GET"))
        assert (delete.status, delete.json) == (405, method_not_allowed("DELETE"))


class TestFiltros:
    def test_por_cuenta_categoria_y_fechas(self, ana, cuenta):
        otra = create_account(ana, kind="credit")
        register(ana, cuenta["id"], category_name="Transporte", occurred_on="2026-01-15")
        register(ana, cuenta["id"], category_name="Compras", occurred_on="2026-03-10")
        register(ana, otra["id"], category_name="Transporte", occurred_on="2026-05-20")

        by_account = ana.client.get(f"{TRANSACTIONS}?account_id={cuenta['id']}").json
        assert by_account["count"] == 2

        transporte = next(
            c for c in ana.client.get("/api/v1/categories/").json["results"] if c["name"] == "Transporte"
        )
        by_category = ana.client.get(
            f"{TRANSACTIONS}?account_id={cuenta['id']}&category_id={transporte['id']}"
        ).json
        assert by_category["count"] == 1

        by_dates = ana.client.get(
            f"{TRANSACTIONS}?account_id={cuenta['id']}&date_from=2026-02-01&date_to=2026-04-01"
        ).json
        assert [t["occurred_on"] for t in by_dates["results"]] == ["2026-03-10"]

    def test_mas_recientes_primero(self, ana, cuenta):
        register(ana, cuenta["id"], occurred_on="2026-01-01")
        register(ana, cuenta["id"], occurred_on="2026-02-01")
        dates = [t["occurred_on"] for t in ana.client.get(f"{TRANSACTIONS}?account_id={cuenta['id']}").json["results"]]
        assert dates == sorted(dates, reverse=True)

    def test_filtros_mal_formados(self, ana):
        response = ana.client.get(f"{TRANSACTIONS}?account_id=x&date_from=ayer")
        assert (response.status, response.json) == (
            400, {"account_id": [INVALID_UUID], "date_from": [INVALID_DATE]}
        )


class TestPaginacion:
    @pytest.fixture(scope="class")
    def con_55(self, ana):
        account = create_account(ana, initial_balance="1000000")
        for _ in range(55):
            assert register(ana, account["id"], "1", "income", category_name="Salario").status == 201
        return account

    def test_primera_pagina(self, ana, host, con_55):
        body = ana.client.get(f"{TRANSACTIONS}?account_id={con_55['id']}").json
        assert (body["count"], len(body["results"]), body["previous"]) == (55, 50, None)
        assert body["next"] == f"{host}{TRANSACTIONS}?account_id={con_55['id']}&page=2"

    def test_segunda_pagina_enlaza_a_la_primera_sin_page(self, ana, host, con_55):
        body = ana.client.get(f"{TRANSACTIONS}?page=2&account_id={con_55['id']}").json
        assert (len(body["results"]), body["next"]) == (5, None)
        assert body["previous"] == f"{host}{TRANSACTIONS}?account_id={con_55['id']}"

    def test_page_last(self, ana, con_55):
        body = ana.client.get(f"{TRANSACTIONS}?account_id={con_55['id']}&page=last").json
        assert len(body["results"]) == 5

    @pytest.mark.parametrize("page", ["0", "3", "x"])
    def test_pagina_invalida(self, ana, con_55, page):
        response = ana.client.get(f"{TRANSACTIONS}?account_id={con_55['id']}&page={page}")
        assert (response.status, response.json) == (404, INVALID_PAGE)
