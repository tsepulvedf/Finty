"""Tests de `CategorizerFactory`: conmutacion por configuracion.

Portado de `finance/tests/test_categorizer_factory.py`. Las aserciones son las
mismas; cambia el mecanismo de configuracion: `monkeypatch.setenv` sobre
`CATEGORIZER_PROVIDER` en lugar de `override_settings`, y `ConfigurationError`
en lugar de `ImproperlyConfigured`. Sin base de datos.
"""
import pytest

from domain.interfaces import Categorizer
from infra.categorizers import (
    AICategorizer,
    MockCategorizer,
    RuleBasedCategorizer,
)
from infra.factories import ConfigurationError, CategorizerFactory


@pytest.fixture
def provider(monkeypatch):
    """Fija el valor de `CATEGORIZER_PROVIDER` para el test."""

    def _set(value):
        monkeypatch.setenv("CATEGORIZER_PROVIDER", value)

    return _set


class TestDespacho:
    """Cada valor de configuracion devuelve su implementacion."""

    def test_rule(self, provider):
        provider("RULE")
        assert isinstance(CategorizerFactory.get_categorizer(), RuleBasedCategorizer)

    def test_ai(self, provider):
        provider("AI")
        assert isinstance(CategorizerFactory.get_categorizer(), AICategorizer)

    def test_mock(self, provider):
        provider("MOCK")
        assert isinstance(CategorizerFactory.get_categorizer(), MockCategorizer)

    def test_sin_variable_el_proveedor_es_rule(self, monkeypatch):
        """Mismo default que `settings.py` del monolito."""
        monkeypatch.delenv("CATEGORIZER_PROVIDER", raising=False)
        assert isinstance(CategorizerFactory.get_categorizer(), RuleBasedCategorizer)

    def test_el_de_proveedor_externo_llega_con_respaldo(self, provider):
        """Sin cliente configurado, delega en el respaldo determinista."""
        provider("AI")
        categorizer = CategorizerFactory.get_categorizer()

        assert categorizer._client is None
        assert isinstance(categorizer._fallback, RuleBasedCategorizer)


class TestNormalizacion:
    """El valor de configuracion se normaliza antes de despachar."""

    @pytest.mark.parametrize("valor", ["mock", "Mock", "MOCK", "  mock  ", "mOcK"])
    def test_insensible_a_mayusculas_y_espacios(self, provider, valor):
        provider(valor)
        assert isinstance(CategorizerFactory.get_categorizer(), MockCategorizer)

    @pytest.mark.parametrize("valor", ["rule", "RULE", " Rule "])
    def test_lo_mismo_para_el_determinista(self, provider, valor):
        provider(valor)
        assert isinstance(CategorizerFactory.get_categorizer(), RuleBasedCategorizer)


class TestFalloRuidoso:
    """Un valor desconocido no degrada en silencio."""

    @pytest.mark.parametrize(
        "valor", ["GPT", "", "rulle", "none", "None", "RULE_BASED", "0"]
    )
    def test_valor_desconocido_lanza_configuration_error(self, provider, valor):
        provider(valor)
        with pytest.raises(ConfigurationError):
            CategorizerFactory.get_categorizer()

    def test_el_mensaje_incluye_el_valor_recibido(self, provider):
        provider("GPT")
        with pytest.raises(ConfigurationError) as error:
            CategorizerFactory.get_categorizer()

        assert "GPT" in str(error.value)

    def test_el_mensaje_lista_los_valores_validos(self, provider):
        provider("GPT")
        with pytest.raises(ConfigurationError) as error:
            CategorizerFactory.get_categorizer()

        for proveedor in CategorizerFactory.available_providers():
            assert proveedor in str(error.value)


class TestAvailableProviders:
    """`available_providers()` es la unica fuente de la lista."""

    def test_devuelve_una_tupla(self):
        assert isinstance(CategorizerFactory.available_providers(), tuple)

    def test_contiene_los_tres_proveedores(self):
        assert set(CategorizerFactory.available_providers()) == {"RULE", "AI", "MOCK"}

    def test_todo_valor_listado_es_despachable(self, provider):
        """Ningun proveedor anunciado puede fallar al instanciarse."""
        for proveedor in CategorizerFactory.available_providers():
            provider(proveedor)
            assert CategorizerFactory.get_categorizer() is not None

    def test_toda_instancia_devuelta_es_un_categorizer(self, provider):
        """Es lo que permite inyectarlas indistintamente en el Service."""
        for proveedor in CategorizerFactory.available_providers():
            provider(proveedor)
            assert isinstance(CategorizerFactory.get_categorizer(), Categorizer)


class TestInstanciacion:
    """Sin memoizacion ni singleton."""

    def test_cada_llamada_devuelve_una_instancia_nueva(self, provider):
        provider("RULE")
        primera = CategorizerFactory.get_categorizer()
        segunda = CategorizerFactory.get_categorizer()

        assert primera is not segunda

    def test_las_instancias_son_equivalentes_en_comportamiento(self, provider):
        from domain.shared.value_objects import Money
        from domain.value_objects import TransactionType

        provider("MOCK")
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
