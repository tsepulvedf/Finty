"""Tests de `RemoteCategorizer`: el cliente de categorization-service (E2-M3b).

Contra el servidor falso de `tests/fakes.py`, que cumple el contrato de
`POST /v1/suggestions/`. Cubren A-22 (respaldo ante cualquier fallo del
remoto), A-14 (procedencia veraz) y A-12 (una sugerencia que no esta en el
catalogo de este servicio no se usa). Sin base de datos: el catalogo es un
diccionario fijo con la forma de `CategoryService.catalog()`.
"""
import time

import pytest

from domain.shared.value_objects import Money
from domain.value_objects import CategorizationSource, CategorySuggestion, TransactionType
from infra.categorization_client import RemoteCategorizer
from infra.categorizers import RuleBasedCategorizer

CATALOG = {
    "Alimentación": "expense",
    "Otros gastos": "expense",
    "Salario": "income",
    "Otros ingresos": "income",
}
TIMEOUT = 0.3
DESCRIPCION = "Almuerzo en el restaurante"
RESPALDO = CategorySuggestion("Alimentación", 0.75, CategorizationSource.RULE)


def remote(url, timeout=TIMEOUT):
    return RemoteCategorizer(url, lambda: CATALOG, RuleBasedCategorizer(), timeout=timeout)


def categorize(categorizer, description=DESCRIPCION, kind=TransactionType.EXPENSE):
    return categorizer.categorize(description, Money("120000", "COP"), kind)


class TestCuandoElRemotoResponde:
    def test_usa_la_sugerencia_del_remoto(self, categorization):
        assert categorize(remote(categorization.url)) == RESPALDO

    def test_conserva_la_procedencia_que_declara(self, categorization):
        """A-14: si clasifico el mock del remoto, se graba `mock`."""
        categorization.mode = "mock"

        suggestion = categorize(remote(categorization.url))

        assert suggestion == CategorySuggestion("Otros gastos", 1.0, CategorizationSource.MOCK)

    def test_envia_descripcion_y_tipo_sin_identidad(self, categorization):
        categorize(remote(categorization.url), "Pago de nomina", TransactionType.INCOME)

        request = categorization.requests[-1]
        assert request["path"] == "/v1/suggestions/"
        assert request["body"] == {"description": "Pago de nomina", "transaction_type": "income"}
        assert "X-User-Id" not in request["headers"]

    def test_una_descripcion_vacia_viaja_como_cadena(self, categorization):
        categorize(remote(categorization.url), None)
        assert categorization.requests[-1]["body"]["description"] == ""


class TestRespaldoA22:
    """Ante cualquier fallo del remoto clasifica el respaldo, con `rule`."""

    @pytest.mark.parametrize("mode", ["error", "garbage", "bad_confidence"])
    def test_respuesta_inutilizable(self, categorization, mode):
        categorization.mode = mode
        assert categorize(remote(categorization.url)) == RESPALDO

    def test_conexion_rechazada(self):
        assert categorize(remote("http://127.0.0.1:9")) == RESPALDO

    def test_nombre_de_host_que_no_resuelve(self):
        assert categorize(remote("http://categorization-service.invalid:8000")) == RESPALDO

    def test_timeout_corto(self, categorization):
        categorization.mode = "slow"
        categorization.delay = 2.0

        started = time.monotonic()
        suggestion = categorize(remote(categorization.url, timeout=0.2))

        assert suggestion == RESPALDO
        assert time.monotonic() - started < 1.5

    def test_nunca_propaga_una_excepcion(self):
        """LSP: el puerto promete una sugerencia, pase lo que pase con la red."""
        broken = RemoteCategorizer("no-es-una-url", lambda: CATALOG, RuleBasedCategorizer())
        assert categorize(broken) == RESPALDO

    def test_un_catalogo_que_falla_tambien_cae_al_respaldo(self, categorization):
        def catalogo_roto():
            raise RuntimeError("base caida")

        categorizer = RemoteCategorizer(categorization.url, catalogo_roto, RuleBasedCategorizer())
        assert categorize(categorizer) == RESPALDO


class TestProcedenciaA14:
    def test_el_remoto_no_puede_declarar_manual(self, categorization):
        """Solo una persona clasifica manualmente."""
        categorization.mode = "manual"
        assert categorize(remote(categorization.url)).source is CategorizationSource.RULE


class TestCatalogoA12:
    """Una sugerencia del remoto que no esta en el catalogo de finty_finance no se usa."""

    def test_categoria_inexistente(self, categorization):
        categorization.mode = "unknown"
        assert categorize(remote(categorization.url)) == RESPALDO

    def test_categoria_del_otro_tipo(self, categorization):
        categorization.mode = "wrong_type"
        assert categorize(remote(categorization.url)) == RESPALDO

    def test_el_catalogo_se_consulta_solo_al_validar(self, categorization):
        """Construir el adaptador no toca la base: lo hace el blueprint en cada peticion."""
        calls = []
        RemoteCategorizer(categorization.url, lambda: calls.append(1) or CATALOG, RuleBasedCategorizer())
        assert calls == []
