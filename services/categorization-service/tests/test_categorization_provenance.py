"""Criterio A-14 en el origen: cada categorizador declara su propia procedencia.

Parte sin red de `finance-service/tests/test_categorization_provenance.py`,
movida aqui con los categorizadores (E2-M3b). Que la procedencia llegue intacta
hasta la fila la verifica `finance-service`.
"""
from domain.shared.value_objects import Money
from domain.value_objects import CategorizationSource, TransactionType
from infra.categorizers import AICategorizer, MockCategorizer, RuleBasedCategorizer

DESCRIPCION_DE_GASTO = "Almuerzo en el restaurante"


class ClienteQueResponde:
    """Cliente de proveedor externo que devuelve una sugerencia valida."""

    def suggest_category(self, description, amount, transaction_type):
        return ("Transporte", 0.93)


class ClienteQueFalla:
    """Cliente de proveedor externo que se cae."""

    def suggest_category(self, description, amount, transaction_type):
        raise TimeoutError("el proveedor no respondio")


# ---------------------------------------------------------------------------
# Nivel de dominio e infraestructura, sin base de datos
# ---------------------------------------------------------------------------


class TestProcedenciaDeCadaCategorizador:
    """Cada implementacion declara la suya y ninguna suplanta a otra."""

    ARGUMENTOS = (DESCRIPCION_DE_GASTO, Money("120000", "COP"), TransactionType.EXPENSE)

    def test_el_mock_reporta_mock(self):
        """A-14: antes reportaba `rule` y falseaba la traza."""
        assert MockCategorizer().categorize(*self.ARGUMENTOS).source is (
            CategorizationSource.MOCK
        )

    def test_el_mock_con_categoria_configurada_tambien_reporta_mock(self):
        suggestion = MockCategorizer("Transporte", 0.5).categorize(*self.ARGUMENTOS)

        assert suggestion.category_name == "Transporte"
        assert suggestion.source is CategorizationSource.MOCK

    def test_la_procedencia_del_mock_sigue_siendo_configurable(self):
        """El parametro no desaparece: un test puede simular otra procedencia."""
        suggestion = MockCategorizer(
            source=CategorizationSource.AI
        ).categorize(*self.ARGUMENTOS)

        assert suggestion.source is CategorizationSource.AI

    def test_las_reglas_reportan_rule(self):
        assert RuleBasedCategorizer().categorize(*self.ARGUMENTOS).source is (
            CategorizationSource.RULE
        )

    def test_el_proveedor_externo_con_cliente_reporta_ai(self):
        suggestion = AICategorizer(client=ClienteQueResponde()).categorize(
            *self.ARGUMENTOS
        )

        assert suggestion.source is CategorizationSource.AI
        assert suggestion.category_name == "Transporte"

    def test_sin_cliente_reporta_la_procedencia_del_respaldo(self):
        """Quien clasifico fue el respaldo, asi que la procedencia es la suya."""
        suggestion = AICategorizer(client=None).categorize(*self.ARGUMENTOS)

        assert suggestion.source is CategorizationSource.RULE

    def test_con_cliente_caido_reporta_la_procedencia_del_respaldo(self):
        suggestion = AICategorizer(client=ClienteQueFalla()).categorize(
            *self.ARGUMENTOS
        )

        assert suggestion.source is CategorizationSource.RULE

    def test_con_respaldo_mock_la_degradacion_reporta_mock(self):
        """La procedencia sigue al mecanismo real, sea cual sea el respaldo."""
        suggestion = AICategorizer(
            client=ClienteQueFalla(), fallback=MockCategorizer()
        ).categorize(*self.ARGUMENTOS)

        assert suggestion.source is CategorizationSource.MOCK

    def test_ninguna_implementacion_comparte_procedencia_con_otra(self):
        procedencias = {
            RuleBasedCategorizer().categorize(*self.ARGUMENTOS).source,
            MockCategorizer().categorize(*self.ARGUMENTOS).source,
            AICategorizer(client=ClienteQueResponde())
            .categorize(*self.ARGUMENTOS)
            .source,
        }

        assert procedencias == {
            CategorizationSource.RULE,
            CategorizationSource.MOCK,
            CategorizationSource.AI,
        }
