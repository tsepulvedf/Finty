"""A-19: ningun camino lleva a datos ajenos; una cuenta ajena da 404, no 403 (D-08)."""
import pytest

from helpers import (
    ACCOUNTS,
    TRANSACTIONS,
    all_ids,
    create_account,
    error_code,
    model_not_found,
    register,
)


@pytest.fixture(scope="module")
def de_ana(ana):
    account = create_account(ana, initial_balance="1000000")
    movement = register(ana, account["id"]).json
    return account, movement


class TestA19CuentaAjena:
    def test_detalle(self, juan, de_ana):
        account, _ = de_ana
        response = juan.client.get(f"{ACCOUNTS}{account['id']}/")
        assert (response.status, response.json) == (404, model_not_found("Account"))

    @pytest.mark.parametrize(
        "method,suffix,body",
        [
            ("PUT", "", {"name": "Robada"}),
            ("PATCH", "", {"name": "Robada"}),
            ("DELETE", "", None),
            ("POST", "archive/", None),
        ],
    )
    def test_escrituras(self, juan, de_ana, method, suffix, body):
        account, _ = de_ana
        response = juan.client.request(method, f"{ACCOUNTS}{account['id']}/{suffix}", body=body)
        assert response.status == 404
        assert error_code(response) == "account_not_found"

    def test_registrar_sobre_ella(self, juan, de_ana):
        account, _ = de_ana
        response = register(juan, account["id"])
        assert response.status == 404
        assert error_code(response) == "account_not_found"

    def test_filtrar_por_ella_devuelve_vacio_no_403(self, juan, de_ana):
        account, _ = de_ana
        response = juan.client.get(f"{TRANSACTIONS}?account_id={account['id']}")
        assert response.status == 200
        assert response.json["count"] == 0

    def test_no_aparece_en_el_listado(self, juan, de_ana):
        account, _ = de_ana
        assert account["id"] not in all_ids(juan.client, f"{ACCOUNTS}?include_archived=1")

    def test_el_balance_de_ana_no_cambio(self, ana, de_ana):
        account, _ = de_ana
        assert ana.client.get(f"{ACCOUNTS}{account['id']}/").json["balance"] == "880000.00"


class TestA19TransaccionAjena:
    @pytest.mark.parametrize(
        "method,suffix,body",
        [("GET", "", None), ("DELETE", "", None), ("POST", "categorize/", {"category_name": "Compras"})],
    )
    def test_cualquier_operacion_da_404(self, juan, de_ana, method, suffix, body):
        _, movement = de_ana
        response = juan.client.request(method, f"{TRANSACTIONS}{movement['id']}/{suffix}", body=body)
        assert response.status == 404
        assert error_code(response) == "transaction_not_found"
