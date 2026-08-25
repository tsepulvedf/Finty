"""Tests del contrato de la interfaz `Categorizer`.

Verifican que la ABC obliga a implementar `categorize` y que una implementacion
minima satisface el contrato declarado en su docstring. Las implementaciones
reales llegan en M4; aqui se prueba la interfaz, no sus adaptadores.

Dominio puro: sin marca `django_db`, corren sin PostgreSQL levantado.
"""
import inspect

import pytest

from core.domain.value_objects import Money
from finance.domain.interfaces import Categorizer
from finance.domain.value_objects import (
    CategorizationSource,
    CategorySuggestion,
    TransactionType,
)


class _StubCategorizer(Categorizer):
    """Implementacion minima de prueba: siempre la misma categoria.

    Definida dentro del modulo de tests a proposito: los categorizadores reales
    son de M4 y viven en `finance/infra/`.
    """

    def categorize(self, description, amount, transaction_type):
        """Devuelve una sugerencia fija, cumpliendo el contrato."""
        return CategorySuggestion("Sin clasificar", 0.1, CategorizationSource.RULE)


class _CategorizerSinImplementar(Categorizer):
    """Subclase que no implementa el metodo abstracto."""


class TestLaAbcObliga:
    """`Categorizer` no es instanciable sin implementar su contrato."""

    def test_no_se_puede_instanciar_la_abc(self):
        with pytest.raises(TypeError):
            Categorizer()

    def test_no_se_puede_instanciar_una_subclase_incompleta(self):
        with pytest.raises(TypeError):
            _CategorizerSinImplementar()

    def test_una_implementacion_completa_si_se_instancia(self):
        assert isinstance(_StubCategorizer(), Categorizer)

    def test_categorize_esta_marcado_como_abstracto(self):
        assert Categorizer.categorize.__isabstractmethod__

    def test_la_interfaz_expone_un_solo_metodo_abstracto(self):
        """ISP: una interfaz minima no carga a nadie con lo que no usa."""
        assert Categorizer.__abstractmethods__ == frozenset({"categorize"})


class TestFirmaDelContrato:
    """La firma declarada es la que consumen los services."""

    def test_parametros_de_categorize(self):
        firma = inspect.signature(Categorizer.categorize)

        assert list(firma.parameters) == [
            "self",
            "description",
            "amount",
            "transaction_type",
        ]

    def test_el_contrato_esta_documentado(self):
        """El docstring es lo que sostiene el LSP; no puede faltar."""
        assert Categorizer.categorize.__doc__


class TestCumplimientoDelContrato:
    """Una implementacion minima satisface las cuatro reglas declaradas."""

    @pytest.fixture
    def categorizer(self):
        return _StubCategorizer()

    def test_devuelve_un_category_suggestion(self, categorizer):
        """Regla 1: siempre un `CategorySuggestion` valido."""
        resultado = categorizer.categorize(
            "Almuerzo en el centro", Money("25000", "COP"), TransactionType.EXPENSE
        )

        assert isinstance(resultado, CategorySuggestion)
        assert resultado.category_name
        assert 0.0 <= resultado.confidence <= 1.0
        assert isinstance(resultado.source, CategorizationSource)

    @pytest.mark.parametrize(
        "description", ["", "   ", "texto cualquiera", "!@#$%", "x" * 500]
    )
    def test_no_propaga_excepciones_ante_entradas_raras(self, categorizer, description):
        """Regla 2: nunca propaga excepciones."""
        assert isinstance(
            categorizer.categorize(
                description, Money("1", "COP"), TransactionType.EXPENSE
            ),
            CategorySuggestion,
        )

    def test_es_idempotente(self, categorizer):
        """Regla 3: la misma entrada produce la misma salida."""
        argumentos = ("Almuerzo", Money("25000", "COP"), TransactionType.EXPENSE)

        primera = categorizer.categorize(*argumentos)
        segunda = categorizer.categorize(*argumentos)

        assert primera == segunda

    def test_no_muta_sus_argumentos(self, categorizer):
        """Regla 4: sin efectos de lado observables."""
        monto = Money("25000", "COP")

        categorizer.categorize("Almuerzo", monto, TransactionType.EXPENSE)

        assert monto == Money("25000", "COP")

    def test_llamadas_sucesivas_no_acumulan_estado(self, categorizer):
        """Regla 4: sin contadores internos que alteren respuestas posteriores."""
        argumentos = ("Almuerzo", Money("100", "COP"), TransactionType.EXPENSE)
        resultados = [categorizer.categorize(*argumentos) for _ in range(5)]

        assert len(set(resultados)) == 1

    def test_es_sustituible_donde_se_espera_la_abstraccion(self, categorizer):
        """LSP: quien programa contra la ABC funciona con cualquier concrecion."""

        def consumidor(categorizador):
            return categorizador.categorize(
                "Cafe", Money("5000", "COP"), TransactionType.EXPENSE
            ).category_name

        assert consumidor(categorizer) == "Sin clasificar"
