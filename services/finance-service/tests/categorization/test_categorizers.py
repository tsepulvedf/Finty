"""Tests de `RuleBasedCategorizer`, el respaldo local de finance-service.

Desde E2-M3b los tests de `AICategorizer` y `MockCategorizer` viven en
`categorization-service`, con esos categorizadores. Aqui quedan los de las
reglas, que son las que clasifican cuando el remoto no responde (A-22).
"""
import pytest

from domain.shared.value_objects import Money
from domain.value_objects import (
    CategorizationSource,
    CategorySuggestion,
    TransactionType,
)
from infra.categorizers import (
    FALLBACK_CONFIDENCE,
    FALLBACK_EXPENSE_CATEGORY,
    FALLBACK_INCOME_CATEGORY,
    MATCH_CONFIDENCE,
    RuleBasedCategorizer,
    normalize_description,
)

EXPENSE = TransactionType.EXPENSE
INCOME = TransactionType.INCOME
AMOUNT = Money("25000", "COP")


@pytest.fixture
def rule_based():
    return RuleBasedCategorizer()


class TestNormalizacion:
    """`normalize_description`."""

    def test_pasa_a_minusculas(self):
        assert normalize_description("ALMUERZO") == "almuerzo"

    def test_quita_tildes(self):
        assert normalize_description("Nómina de Educación") == "nomina de educacion"

    def test_quita_puntuacion(self):
        assert normalize_description("¡Taxi, urgente!") == "taxi urgente"

    def test_colapsa_espacios(self):
        assert normalize_description("  taxi    al   centro ") == "taxi al centro"

    @pytest.mark.parametrize("entrada", [None, 42, [], object()])
    def test_lo_que_no_es_texto_queda_vacio(self, entrada):
        assert normalize_description(entrada) == ""


class TestReglasDeGasto:
    """Una coincidencia por cada categoria de gasto."""

    CASOS = [
        ("Almuerzo en el restaurante", "Alimentación"),
        ("Mercado de la semana", "Alimentación"),
        ("Taxi al aeropuerto", "Transporte"),
        ("Tanqueada de gasolina", "Transporte"),
        ("Pago del arriendo", "Vivienda"),
        ("Recibo de energia", "Servicios públicos"),
        ("Factura de internet", "Servicios públicos"),
        ("Compra en la farmacia", "Salud"),
        ("Pago de la eps", "Salud"),
        ("Matricula de la universidad", "Educación"),
        ("Suscripcion a netflix", "Entretenimiento"),
        ("Boleta para el cine", "Entretenimiento"),
        ("Ropa nueva", "Compras"),
        ("Cuota del prestamo", "Deudas y créditos"),
    ]

    @pytest.mark.parametrize("descripcion,esperada", CASOS)
    def test_coincidencia(self, rule_based, descripcion, esperada):
        suggestion = rule_based.categorize(descripcion, AMOUNT, EXPENSE)

        assert suggestion.category_name == esperada
        assert suggestion.confidence == MATCH_CONFIDENCE
        assert suggestion.source is CategorizationSource.RULE


class TestReglasDeIngreso:
    """Una coincidencia por cada categoria de ingreso."""

    CASOS = [
        ("Pago de nomina", "Salario"),
        ("Quincena de agosto", "Salario"),
        ("Honorarios del mes", "Freelance"),
        ("Proyecto de consultoria", "Freelance"),
        ("Dividendo del cdt", "Inversiones"),
        ("Reembolso del seguro", "Reembolsos"),
    ]

    @pytest.mark.parametrize("descripcion,esperada", CASOS)
    def test_coincidencia(self, rule_based, descripcion, esperada):
        suggestion = rule_based.categorize(descripcion, AMOUNT, INCOME)

        assert suggestion.category_name == esperada
        assert suggestion.confidence == MATCH_CONFIDENCE


class TestInsensibilidad:
    """Las reglas ignoran tildes, mayusculas y puntuacion."""

    @pytest.mark.parametrize(
        "descripcion",
        ["nomina", "NOMINA", "Nómina", "NÓMINA", "  ¡nómina!  ", "NóMiNa"],
    )
    def test_la_misma_regla_se_activa(self, rule_based, descripcion):
        assert rule_based.categorize(descripcion, AMOUNT, INCOME).category_name == "Salario"


class TestLimitesDePalabra:
    """Coincidencia por palabra completa, no por subcadena."""

    def test_no_coincide_dentro_de_otra_palabra(self, rule_based):
        """`mercado` no debe activarse dentro de `supermercadito`."""
        suggestion = rule_based.categorize("supermercadito", AMOUNT, EXPENSE)
        assert suggestion.category_name == FALLBACK_EXPENSE_CATEGORY

    def test_si_coincide_como_palabra_suelta(self, rule_based):
        assert (
            rule_based.categorize("mercado", AMOUNT, EXPENSE).category_name
            == "Alimentación"
        )

    def test_coincide_una_frase_de_dos_palabras(self, rule_based):
        assert (
            rule_based.categorize("interes ganado del mes", AMOUNT, INCOME).category_name
            == "Inversiones"
        )


class TestRespaldo:
    """Sin coincidencia se cae en la categoria de respaldo del tipo."""

    @pytest.mark.parametrize("descripcion", ["", "   ", "xyzzy", None, "12345"])
    def test_gasto_sin_coincidencia(self, rule_based, descripcion):
        suggestion = rule_based.categorize(descripcion, AMOUNT, EXPENSE)

        assert suggestion.category_name == FALLBACK_EXPENSE_CATEGORY
        assert suggestion.confidence == FALLBACK_CONFIDENCE

    @pytest.mark.parametrize("descripcion", ["", "xyzzy", None])
    def test_ingreso_sin_coincidencia(self, rule_based, descripcion):
        suggestion = rule_based.categorize(descripcion, AMOUNT, INCOME)

        assert suggestion.category_name == FALLBACK_INCOME_CATEGORY
        assert suggestion.confidence == FALLBACK_CONFIDENCE


class TestSeparacionPorTipo:
    """Una descripcion de ingreso jamas devuelve categoria de gasto."""

    EXPENSE_ONLY = {
        "Alimentación",
        "Transporte",
        "Vivienda",
        "Servicios públicos",
        "Salud",
        "Educación",
        "Entretenimiento",
        "Compras",
        "Deudas y créditos",
        FALLBACK_EXPENSE_CATEGORY,
    }
    INCOME_ONLY = {
        "Salario",
        "Freelance",
        "Inversiones",
        "Reembolsos",
        FALLBACK_INCOME_CATEGORY,
    }

    @pytest.mark.parametrize(
        "descripcion",
        ["almuerzo restaurante", "taxi", "arriendo", "netflix", "cuota tarjeta"],
    )
    def test_una_descripcion_de_gasto_evaluada_como_ingreso(self, rule_based, descripcion):
        suggestion = rule_based.categorize(descripcion, AMOUNT, INCOME)
        assert suggestion.category_name in self.INCOME_ONLY

    @pytest.mark.parametrize(
        "descripcion", ["nomina quincena", "honorarios", "dividendo", "reembolso"]
    )
    def test_una_descripcion_de_ingreso_evaluada_como_gasto(self, rule_based, descripcion):
        suggestion = rule_based.categorize(descripcion, AMOUNT, EXPENSE)
        assert suggestion.category_name in self.EXPENSE_ONLY

    def test_credito_es_gasto_y_no_se_confunde_con_inversion(self, rule_based):
        assert (
            rule_based.categorize("cuota del credito", AMOUNT, EXPENSE).category_name
            == "Deudas y créditos"
        )


class TestDeterminismo:
    """La misma entrada devuelve el mismo resultado."""

    def test_llamadas_sucesivas(self, rule_based):
        resultados = [
            rule_based.categorize("Almuerzo", AMOUNT, EXPENSE) for _ in range(10)
        ]
        assert len(set(resultados)) == 1

    def test_dos_instancias_coinciden(self):
        primera = RuleBasedCategorizer().categorize("Taxi", AMOUNT, EXPENSE)
        segunda = RuleBasedCategorizer().categorize("Taxi", AMOUNT, EXPENSE)

        assert primera == segunda

    def test_no_guarda_estado_entre_llamadas(self, rule_based):
        rule_based.categorize("Taxi", AMOUNT, EXPENSE)

        assert (
            rule_based.categorize("xyzzy", AMOUNT, EXPENSE).category_name
            == FALLBACK_EXPENSE_CATEGORY
        )

    def test_un_tipo_irreconocible_no_lanza(self, rule_based):
        assert isinstance(
            rule_based.categorize("almuerzo", AMOUNT, "transfer"), CategorySuggestion
        )
