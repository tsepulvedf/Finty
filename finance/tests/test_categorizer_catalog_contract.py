"""Contrato entre las reglas de categorizacion y el catalogo en base de datos.

Este es el test que **sustituye al import compartido**. El codigo de runtime no
puede importar los nombres de categoria del modulo que siembra el catalogo: esos
archivos se aplastan y se reescriben, y el import quedaria roto sin aviso. En su
lugar, `finance/infra/categorizers.py` declara sus propias constantes y este test
verifica contra la base que ambas listas siguen coincidiendo.

Si alguien agrega una regla con un nombre que no esta sembrado, este test falla
antes de que falle un usuario.

Toca la base de datos, asi que lleva la marca correspondiente.
"""
import pytest

from finance.domain.value_objects import TransactionType
from finance.infra.categorizers import (
    ALL_CATEGORY_NAMES,
    EXPENSE_KEYWORDS,
    FALLBACK_BY_TYPE,
    FALLBACK_EXPENSE_CATEGORY,
    FALLBACK_INCOME_CATEGORY,
    INCOME_KEYWORDS,
    KEYWORDS_BY_TYPE,
    AICategorizer,
    RuleBasedCategorizer,
)
from finance.models import Category

pytestmark = pytest.mark.django_db


def emitible_names():
    """Todos los nombres que `RuleBasedCategorizer` puede llegar a devolver."""
    return sorted(
        set(EXPENSE_KEYWORDS)
        | set(INCOME_KEYWORDS)
        | {FALLBACK_EXPENSE_CATEGORY, FALLBACK_INCOME_CATEGORY}
    )


class TestNombresEmitiblesExistenEnBase:
    """Toda categoria que las reglas pueden emitir esta sembrada."""

    @pytest.mark.parametrize("name", emitible_names())
    def test_la_categoria_existe(self, name):
        assert Category.objects.filter(name=name).exists(), (
            f"La regla puede emitir '{name}', pero esa categoria no esta en la "
            f"base. El servicio no podria resolverla."
        )

    def test_las_dos_de_respaldo_existen(self):
        assert Category.objects.filter(name=FALLBACK_EXPENSE_CATEGORY).exists()
        assert Category.objects.filter(name=FALLBACK_INCOME_CATEGORY).exists()

    def test_no_sobra_ninguna_categoria_en_base(self):
        """El catalogo y las constantes describen el mismo conjunto."""
        en_base = set(Category.objects.values_list("name", flat=True))

        assert en_base == set(emitible_names())


class TestCoherenciaDeTipo:
    """Ninguna categoria de gasto esta registrada como de ingreso."""

    @pytest.mark.parametrize("name", sorted(EXPENSE_KEYWORDS))
    def test_las_categorias_de_gasto_aplican_a_gasto(self, name):
        assert Category.objects.get(name=name).applies_to == TransactionType.EXPENSE.value

    @pytest.mark.parametrize("name", sorted(INCOME_KEYWORDS))
    def test_las_categorias_de_ingreso_aplican_a_ingreso(self, name):
        assert Category.objects.get(name=name).applies_to == TransactionType.INCOME.value

    def test_el_respaldo_de_gasto_aplica_a_gasto(self):
        assert (
            Category.objects.get(name=FALLBACK_EXPENSE_CATEGORY).applies_to
            == TransactionType.EXPENSE.value
        )

    def test_el_respaldo_de_ingreso_aplica_a_ingreso(self):
        assert (
            Category.objects.get(name=FALLBACK_INCOME_CATEGORY).applies_to
            == TransactionType.INCOME.value
        )

    def test_los_dos_mapas_no_comparten_categorias(self):
        assert not set(EXPENSE_KEYWORDS) & set(INCOME_KEYWORDS)


class TestAllowedCategoriesCoincideConLaBase:
    """El filtro anti-alucinacion usa exactamente el catalogo real."""

    def test_coincide_exactamente(self):
        en_base = set(Category.objects.values_list("name", flat=True))

        assert AICategorizer().allowed_categories == en_base

    def test_all_category_names_coincide_con_la_base(self):
        en_base = set(Category.objects.values_list("name", flat=True))

        assert set(ALL_CATEGORY_NAMES) == en_base

    def test_tiene_quince_nombres(self):
        assert len(ALL_CATEGORY_NAMES) == Category.objects.count() == 15


class TestSalidaRealDelCategorizador:
    """Lo que el categorizador devuelve de verdad es resoluble en base."""

    DESCRIPCIONES = [
        ("almuerzo en el restaurante", TransactionType.EXPENSE),
        ("taxi al centro", TransactionType.EXPENSE),
        ("pago del arriendo", TransactionType.EXPENSE),
        ("recibo de energia", TransactionType.EXPENSE),
        ("compra en la farmacia", TransactionType.EXPENSE),
        ("matricula universidad", TransactionType.EXPENSE),
        ("suscripcion netflix", TransactionType.EXPENSE),
        ("ropa nueva", TransactionType.EXPENSE),
        ("cuota del prestamo", TransactionType.EXPENSE),
        ("algo sin regla que aplique", TransactionType.EXPENSE),
        ("pago de nomina", TransactionType.INCOME),
        ("honorarios del proyecto", TransactionType.INCOME),
        ("dividendo del cdt", TransactionType.INCOME),
        ("reembolso del seguro", TransactionType.INCOME),
        ("algo sin regla que aplique", TransactionType.INCOME),
    ]

    @pytest.mark.parametrize("description,transaction_type", DESCRIPCIONES)
    def test_la_sugerencia_se_resuelve_contra_la_tabla(
        self, description, transaction_type
    ):
        from core.domain.value_objects import Money

        suggestion = RuleBasedCategorizer().categorize(
            description, Money("1000", "COP"), transaction_type
        )

        categoria = Category.objects.filter(name=suggestion.category_name).first()

        assert categoria is not None, (
            f"'{description}' produjo la categoria "
            f"'{suggestion.category_name}', que no existe en base."
        )
        assert categoria.applies_to == transaction_type.value

    def test_el_mapa_de_respaldo_cubre_los_dos_tipos(self):
        assert set(FALLBACK_BY_TYPE) == set(TransactionType)
        assert set(KEYWORDS_BY_TYPE) == set(TransactionType)
