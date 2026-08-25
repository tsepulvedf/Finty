"""Tests de `CategorizerFactory`: conmutacion por configuracion.

Sin marca `django_db`: `override_settings` no toca la base. Corren sin PostgreSQL.
"""
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from finance.domain.interfaces import Categorizer
from finance.infra.categorizers import (
    AICategorizer,
    MockCategorizer,
    RuleBasedCategorizer,
)
from finance.infra.factories import CategorizerFactory


class TestDespacho:
    """Cada valor de configuracion devuelve su implementacion."""

    @override_settings(CATEGORIZER_PROVIDER="RULE")
    def test_rule(self):
        assert isinstance(CategorizerFactory.get_categorizer(), RuleBasedCategorizer)

    @override_settings(CATEGORIZER_PROVIDER="AI")
    def test_ai(self):
        assert isinstance(CategorizerFactory.get_categorizer(), AICategorizer)

    @override_settings(CATEGORIZER_PROVIDER="MOCK")
    def test_mock(self):
        assert isinstance(CategorizerFactory.get_categorizer(), MockCategorizer)

    @override_settings(CATEGORIZER_PROVIDER="AI")
    def test_el_de_proveedor_externo_llega_con_respaldo(self):
        """Sin cliente configurado, delega en el respaldo determinista."""
        categorizer = CategorizerFactory.get_categorizer()

        assert categorizer._client is None
        assert isinstance(categorizer._fallback, RuleBasedCategorizer)


class TestNormalizacion:
    """El valor de configuracion se normaliza antes de despachar."""

    @pytest.mark.parametrize("valor", ["mock", "Mock", "MOCK", "  mock  ", "mOcK"])
    def test_insensible_a_mayusculas_y_espacios(self, valor):
        with override_settings(CATEGORIZER_PROVIDER=valor):
            assert isinstance(CategorizerFactory.get_categorizer(), MockCategorizer)

    @pytest.mark.parametrize("valor", ["rule", "RULE", " Rule "])
    def test_lo_mismo_para_el_determinista(self, valor):
        with override_settings(CATEGORIZER_PROVIDER=valor):
            assert isinstance(
                CategorizerFactory.get_categorizer(), RuleBasedCategorizer
            )


class TestFalloRuidoso:
    """Un valor desconocido no degrada en silencio."""

    @pytest.mark.parametrize(
        "valor", ["GPT", "", "rulle", "none", "None", "RULE_BASED", "0"]
    )
    def test_valor_desconocido_lanza_improperly_configured(self, valor):
        with override_settings(CATEGORIZER_PROVIDER=valor):
            with pytest.raises(ImproperlyConfigured):
                CategorizerFactory.get_categorizer()

    @override_settings(CATEGORIZER_PROVIDER="GPT")
    def test_el_mensaje_incluye_el_valor_recibido(self):
        with pytest.raises(ImproperlyConfigured) as error:
            CategorizerFactory.get_categorizer()

        assert "GPT" in str(error.value)

    @override_settings(CATEGORIZER_PROVIDER="GPT")
    def test_el_mensaje_lista_los_valores_validos(self):
        with pytest.raises(ImproperlyConfigured) as error:
            CategorizerFactory.get_categorizer()

        for proveedor in CategorizerFactory.available_providers():
            assert proveedor in str(error.value)


class TestAvailableProviders:
    """`available_providers()` es la unica fuente de la lista."""

    def test_devuelve_una_tupla(self):
        assert isinstance(CategorizerFactory.available_providers(), tuple)

    def test_contiene_los_tres_proveedores(self):
        assert set(CategorizerFactory.available_providers()) == {"RULE", "AI", "MOCK"}

    def test_todo_valor_listado_es_despachable(self):
        """Ningun proveedor anunciado puede fallar al instanciarse."""
        for proveedor in CategorizerFactory.available_providers():
            with override_settings(CATEGORIZER_PROVIDER=proveedor):
                assert CategorizerFactory.get_categorizer() is not None

    def test_toda_instancia_devuelta_es_un_categorizer(self):
        """Es lo que permite inyectarlas indistintamente en el Service."""
        for proveedor in CategorizerFactory.available_providers():
            with override_settings(CATEGORIZER_PROVIDER=proveedor):
                assert isinstance(CategorizerFactory.get_categorizer(), Categorizer)


class TestInstanciacion:
    """Sin memoizacion ni singleton."""

    @override_settings(CATEGORIZER_PROVIDER="RULE")
    def test_cada_llamada_devuelve_una_instancia_nueva(self):
        primera = CategorizerFactory.get_categorizer()
        segunda = CategorizerFactory.get_categorizer()

        assert primera is not segunda

    @override_settings(CATEGORIZER_PROVIDER="MOCK")
    def test_las_instancias_son_equivalentes_en_comportamiento(self):
        from core.domain.value_objects import Money
        from finance.domain.value_objects import TransactionType

        argumentos = ("almuerzo", Money("1", "COP"), TransactionType.EXPENSE)

        assert CategorizerFactory.get_categorizer().categorize(
            *argumentos
        ) == CategorizerFactory.get_categorizer().categorize(*argumentos)

    def test_el_metodo_es_estatico(self):
        assert isinstance(
            CategorizerFactory.__dict__["get_categorizer"], staticmethod
        )
        assert isinstance(
            CategorizerFactory.__dict__["available_providers"], staticmethod
        )
