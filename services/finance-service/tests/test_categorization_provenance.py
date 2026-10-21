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

Portado de `finance/tests/test_categorization_provenance.py` del monolito
(E2-M3a). Desde E2-M3b la parte sin red vive en
`categorization-service`, con los categorizadores; aqui queda lo que solo este
servicio puede probar: que la procedencia llega intacta a la fila y que, sin el
remoto, la que se graba es la del respaldo.
"""
from datetime import date, timedelta
from uuid import UUID

import pytest
from sqlalchemy import update

from models import Transaction

YESTERDAY = date.today() - timedelta(days=1)

ACCOUNTS_URL = "/api/v1/accounts/"
TRANSACTIONS_URL = "/api/v1/transactions/"

DESCRIPCION_DE_GASTO = "Almuerzo en el restaurante"


# ---------------------------------------------------------------------------
# Nivel HTTP, con base de datos
# ---------------------------------------------------------------------------


class TestProcedenciaPorHttp:
    """La procedencia viaja intacta hasta la respuesta HTTP."""

    @pytest.fixture
    def cuenta(self, ana):
        respuesta = ana.post(
            ACCOUNTS_URL,
            {
                "name": "Cuenta corriente",
                "type": "bank",
                "currency": "COP",
                "initial_balance": "1000000.00",
            },
        )
        assert respuesta.status_code == 201
        return respuesta.json

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
        )
        assert respuesta.status_code == 201, respuesta.get_data(as_text=True)
        return respuesta.json

    @pytest.mark.parametrize(
        "modo,procedencia",
        [
            ("rule", "rule"),
            ("mock", "mock"),
            ("error", "rule"),
            ("slow", "rule"),
            ("garbage", "rule"),
            ("unknown", "rule"),
            ("manual", "rule"),
        ],
    )
    def test_la_fila_dice_quien_clasifico(self, categorization, ana, cuenta, modo, procedencia):
        """El remoto declara la suya; si no sirve, clasifica el respaldo (`rule`)."""
        categorization.mode = modo
        assert self._registrar(ana, cuenta)["categorization_source"] == procedencia

    def test_la_recategorizacion_manual_dice_manual(self, ana, cuenta):
        creada = self._registrar(ana, cuenta)

        respuesta = ana.post(
            f"{TRANSACTIONS_URL}{creada['id']}/categorize/", {"category_name": "Transporte"}
        )

        assert respuesta.status_code == 200
        assert respuesta.json["categorization_source"] == "manual"

    @pytest.mark.parametrize("procedencia", ["ai", "rule", "manual", "mock"])
    def test_los_cuatro_valores_se_persisten_y_se_recuperan(
        self, session, ana, cuenta, procedencia
    ):
        creada = self._registrar(ana, cuenta)
        session.execute(
            update(Transaction)
            .where(Transaction.id == UUID(creada["id"]))
            .values(categorization_source=procedencia)
        )
        session.commit()

        respuesta = ana.get(f"{TRANSACTIONS_URL}{creada['id']}/")

        assert respuesta.status_code == 200
        assert respuesta.json["categorization_source"] == procedencia
