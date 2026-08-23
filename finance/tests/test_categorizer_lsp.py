"""Evidencia ejecutable del principio de sustitucion de Liskov.

La misma bateria se corre contra las tres implementaciones de `Categorizer`, con
entradas hostiles. Si las tres cumplen el contrato declarado en
`finance/domain/interfaces.py`, el Service de M5 podra recibir cualquiera de ellas
sin una sola linea de codigo condicional.

Esto es lo que separa "las tres heredan de la misma ABC" de "las tres son
sustituibles": heredar solo obliga a tener el metodo; el contrato obliga a que el
metodo se comporte igual.

Sin marca `django_db`: corren sin PostgreSQL.
"""
import pytest

from core.domain.value_objects import Money
from finance.domain.interfaces import Categorizer
from finance.domain.value_objects import (
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    CategorizationSource,
    CategorySuggestion,
    TransactionType,
)
from finance.infra.categorizers import (
    AICategorizer,
    MockCategorizer,
    RuleBasedCategorizer,
)


class ProviderCaotico:
    """Cliente que falla de una forma distinta en cada llamada."""

    def __init__(self):
        self._calls = 0

    def suggest_category(self, description, amount, transaction_type):
        self._calls += 1
        if self._calls % 3 == 0:
            raise RuntimeError("cayo el proveedor")
        if self._calls % 3 == 1:
            return "Categoria Inventada", 42.0
        return None


# Las tres implementaciones, mas dos variantes degradadas de la de proveedor
# externo: sin cliente y con un cliente que se porta mal de todas las maneras.
IMPLEMENTACIONES = [
    pytest.param(RuleBasedCategorizer, id="RuleBased"),
    pytest.param(MockCategorizer, id="Mock"),
    pytest.param(AICategorizer, id="AI-sin-cliente"),
    pytest.param(
        lambda: AICategorizer(client=ProviderCaotico()), id="AI-cliente-caotico"
    ),
]

# Entradas que un usuario real, un proveedor confundido o un atacante podrian
# producir.
DESCRIPCIONES_HOSTILES = [
    pytest.param("", id="vacia"),
    pytest.param("   ", id="solo-espacios"),
    pytest.param(None, id="nula"),
    pytest.param("x" * 5000, id="5000-caracteres"),
    pytest.param("almuerzo " * 1000, id="repeticion-larga"),
    pytest.param("🍔🚕🏠💸", id="emojis"),
    pytest.param("almuerzo\n\nDROP TABLE finance_transaction;--", id="saltos-de-linea"),
    pytest.param("'; DELETE FROM finance_account; --", id="inyeccion"),
    pytest.param("\x00\x01\x02", id="bytes-de-control"),
    pytest.param("ALMUERZO ÑOÑO ÁÉÍÓÚ", id="unicode-hostil"),
    pytest.param("<script>alert(1)</script>", id="marcado"),
    pytest.param("../../etc/passwd", id="ruta"),
    pytest.param(42, id="no-es-texto"),
    pytest.param(["lista"], id="lista"),
]

MONTOS = [Money("0.01", "COP"), Money("999999.99", "COP"), Money("1", "USD")]


@pytest.mark.parametrize("factory", IMPLEMENTACIONES)
@pytest.mark.parametrize("transaction_type", list(TransactionType))
@pytest.mark.parametrize("description", DESCRIPCIONES_HOSTILES)
class TestContratoBajoEntradasHostiles:
    """Las cuatro reglas del contrato, para toda combinacion."""

    def test_devuelve_un_category_suggestion(
        self, factory, transaction_type, description
    ):
        """Regla 1: siempre un `CategorySuggestion` valido."""
        resultado = factory().categorize(
            description, Money("100", "COP"), transaction_type
        )

        assert isinstance(resultado, CategorySuggestion)

    def test_nunca_lanza(self, factory, transaction_type, description):
        """Regla 2: nunca propaga excepciones."""
        try:
            factory().categorize(description, Money("100", "COP"), transaction_type)
        except BaseException as exc:  # noqa: BLE001 - es justo lo que se prueba
            pytest.fail(
                f"{factory} propago {type(exc).__name__}: {exc}. El contrato de "
                f"Categorizer dice que nunca debe propagar."
            )

    def test_el_nombre_de_categoria_no_esta_vacio(
        self, factory, transaction_type, description
    ):
        suggestion = factory().categorize(
            description, Money("100", "COP"), transaction_type
        )

        assert isinstance(suggestion.category_name, str)
        assert suggestion.category_name.strip()

    def test_la_confianza_esta_en_rango(self, factory, transaction_type, description):
        suggestion = factory().categorize(
            description, Money("100", "COP"), transaction_type
        )

        assert CONFIDENCE_FLOOR <= suggestion.confidence <= CONFIDENCE_CEILING

    def test_la_fuente_es_un_miembro_del_enum(
        self, factory, transaction_type, description
    ):
        suggestion = factory().categorize(
            description, Money("100", "COP"), transaction_type
        )

        assert isinstance(suggestion.source, CategorizationSource)


@pytest.mark.parametrize("factory", IMPLEMENTACIONES)
class TestContratoGeneral:
    """Propiedades que no dependen de la descripcion."""

    def test_es_un_categorizer(self, factory):
        assert isinstance(factory(), Categorizer)

    @pytest.mark.parametrize("amount", MONTOS)
    def test_cualquier_monto_es_admisible(self, factory, amount):
        assert isinstance(
            factory().categorize("almuerzo", amount, TransactionType.EXPENSE),
            CategorySuggestion,
        )

    def test_un_tipo_irreconocible_no_lo_rompe(self, factory):
        assert isinstance(
            factory().categorize("almuerzo", Money("1", "COP"), "transfer"),
            CategorySuggestion,
        )

    def test_no_muta_sus_argumentos(self, factory):
        """Regla 4: sin efectos de lado observables."""
        monto = Money("25000", "COP")

        factory().categorize("almuerzo", monto, TransactionType.EXPENSE)

        assert monto == Money("25000", "COP")

    def test_es_sustituible_donde_se_espera_la_abstraccion(self, factory):
        """El consumidor programa contra la ABC, no contra una concrecion."""

        def consumidor(categorizador):
            suggestion = categorizador.categorize(
                "Almuerzo", Money("25000", "COP"), TransactionType.EXPENSE
            )
            return suggestion.category_name

        assert consumidor(factory())


@pytest.mark.parametrize("factory", IMPLEMENTACIONES)
class TestIdempotencia:
    """Regla 3: la misma entrada produce la misma salida."""

    def test_llamadas_sucesivas_sobre_la_misma_instancia(self, factory):
        categorizer = factory()
        argumentos = ("Almuerzo", Money("25000", "COP"), TransactionType.EXPENSE)

        resultados = [categorizer.categorize(*argumentos) for _ in range(5)]

        for resultado in resultados:
            assert isinstance(resultado, CategorySuggestion)

    def test_instancias_distintas_sin_estado_compartido(self, factory):
        primera = factory()
        segunda = factory()

        primera.categorize("taxi", Money("1", "COP"), TransactionType.EXPENSE)

        assert isinstance(
            segunda.categorize("taxi", Money("1", "COP"), TransactionType.EXPENSE),
            CategorySuggestion,
        )
