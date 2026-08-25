"""Tests del criterio A-14: la procedencia registrada es veraz.

`categorization_source` debe identificar **el mecanismo que realmente
clasifico**, no el que se pidio. Dos casos concretos:

- Un doble de pruebas no puede reportarse como `rule`, porque dejaria una traza
  de auditoria que atribuye a las reglas de negocio una decision que tomo un
  mock. Por eso `CategorizationSource.MOCK` existe (correccion C-19).
- Cuando el clasificador de proveedor externo degrada a su respaldo, quien
  clasifico fue el respaldo: la procedencia es `rule`, no `ai`.

Es tambien una mejor demostracion del Factory que la de M6: los tres proveedores
se distinguen ahora en la respuesta HTTP por procedencia, y no solo por el nombre
de la categoria que devuelven.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from core.domain.value_objects import Money
from finance.domain.value_objects import CategorizationSource, TransactionType
from finance.infra.categorizers import (
    AICategorizer,
    MockCategorizer,
    RuleBasedCategorizer,
)
from finance.models import Transaction

PASSWORD = "Contrasena-Segura-2026"
YESTERDAY = date.today() - timedelta(days=1)

ACCOUNTS_URL = "/api/v1/accounts/"
TRANSACTIONS_URL = "/api/v1/transactions/"

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


# ---------------------------------------------------------------------------
# Nivel HTTP, con base de datos
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProcedenciaPorHttp:
    """La procedencia viaja intacta hasta la respuesta HTTP."""

    @pytest.fixture
    def cliente(self):
        anonimo = APIClient()
        registro = anonimo.post(
            "/api/v1/auth/register/",
            {
                "email": "proveniencia@finty.co",
                "password": PASSWORD,
                "display_name": "Procedencia",
            },
            format="json",
        )
        assert registro.status_code == 201
        autenticado = APIClient()
        autenticado.credentials(
            HTTP_AUTHORIZATION=f"Token {registro.json()['token']}"
        )
        return autenticado

    @pytest.fixture
    def cuenta(self, cliente):
        respuesta = cliente.post(
            ACCOUNTS_URL,
            {
                "name": "Cuenta corriente",
                "type": "bank",
                "currency": "COP",
                "initial_balance": "1000000.00",
            },
            format="json",
        )
        assert respuesta.status_code == 201
        return respuesta.json()

    def _registrar(self, cliente, cuenta, descripcion=DESCRIPCION_DE_GASTO):
        """Envia siempre el mismo cuerpo de peticion."""
        respuesta = cliente.post(
            TRANSACTIONS_URL,
            {
                "account_id": cuenta["id"],
                "amount": "120000.00",
                "type": "expense",
                "occurred_on": YESTERDAY.isoformat(),
                "description": descripcion,
            },
            format="json",
        )
        assert respuesta.status_code == 201, respuesta.content
        return respuesta.json()

    @override_settings(CATEGORIZER_PROVIDER="MOCK")
    def test_con_proveedor_mock_la_respuesta_dice_mock(self, cliente, cuenta):
        assert self._registrar(cliente, cuenta)["categorization_source"] == "mock"

    @override_settings(CATEGORIZER_PROVIDER="RULE")
    def test_con_proveedor_rule_la_respuesta_dice_rule(self, cliente, cuenta):
        assert self._registrar(cliente, cuenta)["categorization_source"] == "rule"

    @override_settings(CATEGORIZER_PROVIDER="AI")
    def test_con_proveedor_ai_sin_cliente_la_respuesta_dice_rule(
        self, cliente, cuenta
    ):
        """Sin cliente configurado clasifico el respaldo, y eso es lo que se graba."""
        assert self._registrar(cliente, cuenta)["categorization_source"] == "rule"

    def test_la_recategorizacion_manual_dice_manual(self, cliente, cuenta):
        creada = self._registrar(cliente, cuenta)

        respuesta = cliente.post(
            f"{TRANSACTIONS_URL}{creada['id']}/categorize/",
            {"category_name": "Transporte"},
            format="json",
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["categorization_source"] == "manual"

    def test_el_mismo_cuerpo_produce_procedencias_distintas(self, cliente, cuenta):
        """A-13 y A-14 juntos: el Factory es observable por la procedencia.

        Exactamente el mismo cuerpo de peticion y exactamente el mismo codigo. Lo
        unico que cambia entre las tres corridas es una variable de configuracion.
        """
        procedencias = {}
        for proveedor in ("RULE", "MOCK", "AI"):
            with override_settings(CATEGORIZER_PROVIDER=proveedor):
                procedencias[proveedor] = self._registrar(cliente, cuenta)[
                    "categorization_source"
                ]

        assert procedencias == {"RULE": "rule", "MOCK": "mock", "AI": "rule"}
        assert procedencias["RULE"] != procedencias["MOCK"]

    @pytest.mark.parametrize("procedencia", ["ai", "rule", "manual", "mock"])
    def test_los_cuatro_valores_se_persisten_y_se_recuperan(
        self, cliente, cuenta, procedencia
    ):
        creada = self._registrar(cliente, cuenta)
        Transaction.objects.filter(pk=creada["id"]).update(
            categorization_source=procedencia
        )

        respuesta = cliente.get(f"{TRANSACTIONS_URL}{creada['id']}/")

        assert respuesta.status_code == 200
        assert respuesta.json()["categorization_source"] == procedencia
        assert (
            Transaction.objects.get(pk=creada["id"]).categorization_source
            == procedencia
        )

    def test_los_choices_del_modelo_cubren_los_cuatro_valores(self):
        """El enum del dominio y los `choices` del modelo no pueden divergir."""
        declarados = {
            valor
            for valor, _ in Transaction._meta.get_field(
                "categorization_source"
            ).choices
        }

        assert declarados == {member.value for member in CategorizationSource}
