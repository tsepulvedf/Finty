"""Autenticacion del bloque finance: INV-01 y A-18.

Antes de la conmutacion la hace DRF dentro de Django; despues, el Gateway con
`auth_request` (ADR-09). El cliente debe ver exactamente lo mismo.
"""
import uuid

import pytest

from conftest import Client
from helpers import (
    ACCOUNTS,
    all_ids,
    CATEGORIES,
    INVALID_TOKEN,
    NOT_AUTHENTICATED,
    TOKEN_WITH_SPACES,
    TOKEN_WITHOUT_CREDENTIALS,
    TRANSACTIONS,
    create_account,
    register,
)


@pytest.fixture(scope="module")
def ids(ana):
    account = create_account(ana, initial_balance="1000000")
    movement = register(ana, account["id"]).json
    return {"account": account["id"], "transaction": movement["id"]}


def endpoints(ids):
    account = f"{ACCOUNTS}{ids['account']}/"
    movement = f"{TRANSACTIONS}{ids['transaction']}/"
    return [
        ("GET", ACCOUNTS, None),
        ("POST", ACCOUNTS, {"name": "x", "type": "cash"}),
        ("GET", account, None),
        ("PUT", account, {"name": "x"}),
        ("PATCH", account, {"name": "x"}),
        ("DELETE", account, None),
        ("POST", f"{account}archive/", None),
        ("GET", CATEGORIES, None),
        ("GET", TRANSACTIONS, None),
        ("POST", TRANSACTIONS, {}),
        ("GET", movement, None),
        ("DELETE", movement, None),
        ("POST", f"{movement}categorize/", {}),
    ]


class TestSinCredenciales:
    def test_todos_los_endpoints_responden_401(self, anonimo, ids):
        for method, path, body in endpoints(ids):
            response = anonimo.request(method, path, body=body)
            assert response.status == 401, f"{method} {path}"
            assert response.json == NOT_AUTHENTICATED, f"{method} {path}"
            assert response.header("WWW-Authenticate") == "Token", f"{method} {path}"

    def test_un_esquema_distinto_de_token_cuenta_como_sin_credenciales(self, anonimo):
        response = anonimo.get(ACCOUNTS, headers={"Authorization": "Bearer abc"})
        assert (response.status, response.json) == (401, NOT_AUTHENTICATED)

    def test_un_metodo_no_permitido_sin_credenciales_da_401(self, anonimo):
        """La autenticacion va antes que el despacho por metodo."""
        response = anonimo.post(CATEGORIES, {})
        assert (response.status, response.json) == (401, NOT_AUTHENTICATED)


class TestTokenInvalido:
    @pytest.mark.parametrize(
        "header,expected",
        [
            ("Token " + "0" * 40, INVALID_TOKEN),
            ("Token", TOKEN_WITHOUT_CREDENTIALS),
            ("Token abc def", TOKEN_WITH_SPACES),
        ],
    )
    def test_el_motivo_conserva_el_texto_de_drf(self, anonimo, header, expected):
        response = anonimo.get(ACCOUNTS, headers={"Authorization": header})
        assert response.status == 401
        assert response.json == expected
        assert response.header("WWW-Authenticate") == "Token"


def _with_forged_identity(send, user_id):
    """Envia `X-User-Id` falso en todas las peticiones, paginas incluidas."""

    def forged(method, path, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers["X-User-Id"] = user_id
        return send(method, path, headers=headers, **kwargs)

    return forged


class TestA18XUserIdDelCliente:
    """A-18: un `X-User-Id` enviado por el cliente se ignora."""

    def test_la_identidad_sale_del_token_y_no_de_la_cabecera(self, ana, juan):
        cuenta_de_juan = create_account(juan)
        cuenta_de_ana = create_account(ana)

        forged = Client(ana.client.base_url, ana.client.token)
        forged.request = _with_forged_identity(forged.request, juan.user_id)

        ids = all_ids(forged, f"{ACCOUNTS}?include_archived=true")
        assert cuenta_de_ana["id"] in ids
        assert cuenta_de_juan["id"] not in ids

    def test_no_se_puede_escribir_en_nombre_de_otro(self, ana, juan):
        creada = ana.client.post(
            ACCOUNTS, {"name": "Suplantada", "type": "cash"},
            headers={"X-User-Id": juan.user_id},
        ).json

        assert juan.client.get(f"{ACCOUNTS}{creada['id']}/").status == 404
        assert ana.client.get(f"{ACCOUNTS}{creada['id']}/").status == 200

    def test_sin_token_la_cabecera_no_autentica(self, anonimo, ana):
        response = anonimo.get(ACCOUNTS, headers={"X-User-Id": ana.user_id})
        assert (response.status, response.json) == (401, NOT_AUTHENTICATED)

    def test_una_identidad_inventada_tampoco(self, anonimo):
        response = anonimo.get(ACCOUNTS, headers={"X-User-Id": str(uuid.uuid4())})
        assert response.status == 401
