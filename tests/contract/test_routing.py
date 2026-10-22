"""Enrutamiento del bloque finance en el Gateway (ADR-08).

Toda variante de las rutas del agregado (sin barra final, con sufijo `.json`)
debe caer en el bloque finance de Nginx, que marca sus respuestas con
`X-Finty-Route: finance`. Asi, tras la conmutacion, ninguna llega a Django por
el bloque generico de `/api/v1/`.

Ademas cada variante conserva su comportamiento: el sufijo `.json` responde
como la ruta canonica, y la ruta sin barra final redirige a la que la tiene. El
codigo de esa redireccion es 301 en Django y 308 en Flask (C-32).
"""
import pytest

from helpers import ACCOUNTS, CATEGORIES, TRANSACTIONS, create_account, register

ROUTE_HEADER = "X-Finty-Route"


@pytest.fixture(scope="module")
def ids(ana):
    account = create_account(ana, initial_balance="1000")
    movement = register(ana, account["id"], "1").json
    return account["id"], movement["id"]


def variants(ids):
    account, movement = ids
    return [
        ("GET", "/api/v1/accounts"),
        ("GET", "/api/v1/accounts/"),
        ("GET", "/api/v1/accounts.json"),
        ("GET", "/api/v1/accounts.json/"),
        ("GET", f"/api/v1/accounts/{account}"),
        ("GET", f"/api/v1/accounts/{account}.json"),
        ("POST", f"/api/v1/accounts/{account}/archive"),
        ("GET", f"/api/v1/accounts/{account}/archive.json"),
        ("GET", "/api/v1/categories"),
        ("GET", "/api/v1/categories.json"),
        ("GET", "/api/v1/transactions"),
        ("GET", "/api/v1/transactions.json"),
        ("GET", f"/api/v1/transactions/{movement}"),
        ("GET", f"/api/v1/transactions/{movement}/categorize"),
    ]


class TestTodaVarianteCaeEnElBloqueFinance:
    def test_con_credenciales(self, ana, ids):
        for method, path in variants(ids):
            response = ana.client.request(method, path)
            assert response.header(ROUTE_HEADER) == "finance", f"{method} {path}"

    def test_sin_credenciales(self, anonimo, ids):
        for method, path in variants(ids):
            response = anonimo.request(method, path)
            assert response.header(ROUTE_HEADER) == "finance", f"{method} {path}"

    @pytest.mark.parametrize(
        "path", ["/api/v1/health/", "/api/v1/profile/", "/api/v1/accountsx/", "/api/v1/"]
    )
    def test_lo_demas_no(self, ana, path):
        assert ana.client.get(path).header(ROUTE_HEADER) is None


class TestLasVariantesConservanSuComportamiento:
    @pytest.mark.parametrize("path", ["/api/v1/accounts.json", "/api/v1/accounts.json/"])
    def test_sufijo_en_el_listado(self, ana, ids, path):
        response = ana.client.get(path)
        assert response.status == 200
        # Solo `results`: los enlaces `next` llevan la ruta pedida, con o sin sufijo.
        assert response.json["results"] == ana.client.get(ACCOUNTS).json["results"]

    def test_sufijo_en_el_detalle(self, ana, ids):
        account, _ = ids
        assert ana.client.get(f"/api/v1/accounts/{account}.json").json == ana.client.get(
            f"{ACCOUNTS}{account}/"
        ).json

    def test_sufijo_en_categorias(self, ana):
        assert ana.client.get("/api/v1/categories.json").json == ana.client.get(CATEGORIES).json

    @pytest.mark.parametrize(
        "path", ["/api/v1/accounts", "/api/v1/categories", "/api/v1/transactions"]
    )
    def test_sin_barra_final_redirige_a_la_canonica(self, ana, host, path):
        response = ana.client.get(path)
        assert response.status in (301, 308)
        assert response.header("Location") in (f"{path}/", f"{host}{path}/")

    def test_transacciones_no_tienen_sufijo(self, ana):
        assert ana.client.get(f"{TRANSACTIONS[:-1]}.json").status == 404


class TestInternal:
    @pytest.mark.parametrize("path", ["/internal/auth/verify/", "/_gateway/auth/verify"])
    def test_no_es_alcanzable_desde_fuera(self, ana, path):
        assert ana.client.get(path).status == 404

    def test_el_contacto_interno_de_identity_no_es_alcanzable(self, ana, anonimo):
        """E2-M7: lo usa subscription-service por la red interna; desde fuera, 404."""
        path = f"/internal/users/{ana.user_id}/contact/"
        assert anonimo.get(path).status == 404
        response = ana.client.get(path)
        assert response.status == 404 and ana.email not in response.text
