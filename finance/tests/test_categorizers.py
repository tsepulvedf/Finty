"""Tests de los tres categorizadores concretos.

Sin marca `django_db`: ninguno toca la base de datos. Corren sin PostgreSQL.
"""
import pytest

from core.domain.value_objects import Money
from finance.domain.value_objects import (
    CategorizationSource,
    CategorySuggestion,
    TransactionType,
)
from finance.infra.categorizers import (
    FALLBACK_CONFIDENCE,
    FALLBACK_EXPENSE_CATEGORY,
    FALLBACK_INCOME_CATEGORY,
    MATCH_CONFIDENCE,
    AICategorizer,
    MockCategorizer,
    RuleBasedCategorizer,
    normalize_description,
)

EXPENSE = TransactionType.EXPENSE
INCOME = TransactionType.INCOME
AMOUNT = Money("25000", "COP")


class ProviderQueFalla:
    """Cliente que siempre lanza la excepcion configurada."""

    def __init__(self, exception):
        self._exception = exception

    def suggest_category(self, description, amount, transaction_type):
        raise self._exception


class ProviderQueResponde:
    """Cliente que devuelve una respuesta fija."""

    def __init__(self, category_name, confidence):
        self._category_name = category_name
        self._confidence = confidence
        self.calls = 0

    def suggest_category(self, description, amount, transaction_type):
        self.calls += 1
        return self._category_name, self._confidence


class ErrorDelProveedor(Exception):
    """Excepcion personalizada de un proveedor imaginario."""


class ExpiracionDura(BaseException):
    """Expiracion de tiempo que no deriva de `Exception`."""


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


class TestAICategorizerCaminoFeliz:
    """Respuesta valida del proveedor."""

    def test_devuelve_fuente_ai(self):
        categorizer = AICategorizer(client=ProviderQueResponde("Transporte", 0.9))

        suggestion = categorizer.categorize("Taxi", AMOUNT, EXPENSE)

        assert suggestion.category_name == "Transporte"
        assert suggestion.confidence == 0.9
        assert suggestion.source is CategorizationSource.AI

    def test_consulta_al_proveedor_una_sola_vez(self):
        client = ProviderQueResponde("Transporte", 0.9)
        AICategorizer(client=client).categorize("Taxi", AMOUNT, EXPENSE)

        assert client.calls == 1

    def test_allowed_categories_por_defecto_tiene_quince_nombres(self):
        assert len(AICategorizer().allowed_categories) == 15


class TestAICategorizerDegradacion:
    """Las cuatro degradaciones terminan en el respaldo."""

    def test_sin_cliente_delega_en_el_respaldo(self):
        suggestion = AICategorizer(client=None).categorize("Taxi", AMOUNT, EXPENSE)

        assert suggestion.category_name == "Transporte"
        assert suggestion.source is CategorizationSource.RULE

    @pytest.mark.parametrize(
        "exception",
        [
            RuntimeError("cayo el proveedor"),
            TimeoutError("expiro"),
            ErrorDelProveedor("error propio"),
            ValueError("respuesta ilegible"),
            ExpiracionDura("no deriva de Exception"),
        ],
    )
    def test_un_cliente_que_lanza_no_propaga(self, exception):
        categorizer = AICategorizer(client=ProviderQueFalla(exception))

        suggestion = categorizer.categorize("Taxi", AMOUNT, EXPENSE)

        assert suggestion.category_name == "Transporte"
        assert suggestion.source is CategorizationSource.RULE

    def test_una_categoria_alucinada_se_descarta(self):
        categorizer = AICategorizer(client=ProviderQueResponde("Criptomonedas", 0.99))

        suggestion = categorizer.categorize("Taxi", AMOUNT, EXPENSE)

        assert suggestion.category_name == "Transporte"
        assert suggestion.source is CategorizationSource.RULE

    def test_una_respuesta_con_forma_inesperada_se_descarta(self):
        categorizer = AICategorizer(client=ProviderQueResponde(None, 0.9))

        assert (
            categorizer.categorize("Taxi", AMOUNT, EXPENSE).source
            is CategorizationSource.RULE
        )

    def test_una_confianza_no_numerica_se_descarta(self):
        categorizer = AICategorizer(client=ProviderQueResponde("Transporte", "alta"))

        assert (
            categorizer.categorize("Taxi", AMOUNT, EXPENSE).source
            is CategorizationSource.RULE
        )

    def test_el_respaldo_es_inyectable(self):
        categorizer = AICategorizer(
            client=ProviderQueFalla(RuntimeError()),
            fallback=MockCategorizer("Compras", 0.5),
        )

        assert categorizer.categorize("Taxi", AMOUNT, EXPENSE).category_name == "Compras"

    def test_allowed_categories_es_inyectable(self):
        categorizer = AICategorizer(
            client=ProviderQueResponde("Solo esta", 0.9),
            allowed_categories={"Solo esta"},
        )

        assert (
            categorizer.categorize("x", AMOUNT, EXPENSE).source
            is CategorizationSource.AI
        )


class TestAICategorizerRecorteDeConfianza:
    """La confianza fuera de rango se recorta, no se descarta."""

    @pytest.mark.parametrize(
        "recibida,esperada", [(1.7, 1.0), (-0.3, 0.0), (100.0, 1.0), (2, 1.0)]
    )
    def test_recorte(self, recibida, esperada):
        categorizer = AICategorizer(client=ProviderQueResponde("Transporte", recibida))

        suggestion = categorizer.categorize("Taxi", AMOUNT, EXPENSE)

        assert suggestion.confidence == esperada
        assert suggestion.source is CategorizationSource.AI

    @pytest.mark.parametrize("confianza", [0.0, 0.5, 1.0])
    def test_una_confianza_en_rango_no_se_toca(self, confianza):
        categorizer = AICategorizer(client=ProviderQueResponde("Transporte", confianza))

        assert categorizer.categorize("Taxi", AMOUNT, EXPENSE).confidence == confianza


class TestMockCategorizer:
    """`MockCategorizer`."""

    def test_con_categoria_configurada(self):
        suggestion = MockCategorizer("Compras", 0.5).categorize("x", AMOUNT, EXPENSE)

        assert suggestion.category_name == "Compras"
        assert suggestion.confidence == 0.5

    def test_sin_categoria_devuelve_el_respaldo_de_gasto(self):
        assert (
            MockCategorizer().categorize("x", AMOUNT, EXPENSE).category_name
            == FALLBACK_EXPENSE_CATEGORY
        )

    def test_sin_categoria_devuelve_el_respaldo_de_ingreso(self):
        assert (
            MockCategorizer().categorize("x", AMOUNT, INCOME).category_name
            == FALLBACK_INCOME_CATEGORY
        )

    def test_confianza_por_defecto(self):
        assert MockCategorizer().categorize("x", AMOUNT, EXPENSE).confidence == 1.0

    def test_fuente_configurable(self):
        suggestion = MockCategorizer(
            "Compras", 1.0, CategorizationSource.MANUAL
        ).categorize("x", AMOUNT, EXPENSE)

        assert suggestion.source is CategorizationSource.MANUAL

    def test_siempre_devuelve_lo_mismo(self):
        categorizer = MockCategorizer("Compras")
        resultados = [
            categorizer.categorize(texto, AMOUNT, EXPENSE)
            for texto in ["taxi", "nomina", "", "xyz"]
        ]

        assert len(set(resultados)) == 1
