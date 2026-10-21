"""Criterio A-08: `TransactionService` funciona igual con cualquier `Categorizer`.

Desde E2-M3b las implementaciones que ve este servicio son el adaptador remoto
(`RemoteCategorizer`, contra el servidor falso de `categorization-service`), su
respaldo local (`RuleBasedCategorizer`) y un doble de pruebas.

Portado de `TestLSPEnElServicio` (`finance/tests/test_services.py` del monolito,
E2-M3a). Ni el servicio ni estos tests contienen una sola linea condicional sobre
que categorizador se inyecto: eso es lo que significa que sean sustituibles.
"""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.exceptions import ZeroAmountError
from infra.categorization_client import RemoteCategorizer
from infra.categorizers import RuleBasedCategorizer
from tests.doubles import MockCategorizer
from models import Account, Category, Transaction
from services import AccountService, CategoryService, TransactionService

YESTERDAY = date.today() - timedelta(days=1)


@pytest.fixture(params=["remoto", "remoto-caido", "rule", "mock"])
def factory(request, session, categorization):
    """Constructor sin argumentos del categorizador de cada caso."""
    builders = {
        "remoto": lambda: RemoteCategorizer(
            categorization.url, CategoryService(session).catalog, RuleBasedCategorizer(), timeout=0.3
        ),
        "remoto-caido": lambda: RemoteCategorizer(
            "http://127.0.0.1:9", CategoryService(session).catalog, RuleBasedCategorizer(), timeout=0.3
        ),
        "rule": RuleBasedCategorizer,
        "mock": MockCategorizer,
    }
    return builders[request.param]


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def account(session, user_id):
    return AccountService(session).create_account(
        user_id, "Cuenta corriente", "bank", initial_balance=Decimal("1000000.00")
    )


def registrar(service, user_id, account, amount, kind="expense", **extra):
    return service.register_transaction(
        user_id=user_id,
        account_id=account.id,
        amount=Decimal(amount),
        transaction_type=kind,
        occurred_on=YESTERDAY,
        **extra,
    )


class TestLSPEnElServicio:
    def test_registra_una_transaccion_valida(self, session, user_id, account, factory):
        service = TransactionService(session, factory())

        movimiento = registrar(service, user_id, account, "120000", description="Mercado de la semana")

        assert session.get(Transaction, movimiento.id) is not None

    def test_la_categoria_queda_resuelta(self, session, user_id, account, factory):
        service = TransactionService(session, factory())

        movimiento = registrar(service, user_id, account, "120000", description="Mercado de la semana")

        assert movimiento.category is not None
        assert session.get(Category, movimiento.category_id) is not None

    def test_la_categoria_corresponde_al_tipo(self, session, user_id, account, factory):
        service = TransactionService(session, factory())

        movimiento = registrar(service, user_id, account, "500000", "income", description="Pago de nomina")

        assert movimiento.category.applies_to == "income"

    def test_la_fuente_y_la_confianza_quedan_registradas(self, session, user_id, account, factory):
        service = TransactionService(session, factory())

        movimiento = registrar(service, user_id, account, "120000", description="Taxi")

        assert movimiento.categorization_source in {"ai", "rule", "manual", "mock"}
        assert 0.0 <= movimiento.categorization_confidence <= 1.0

    def test_el_balance_queda_correcto(self, session, user_id, account, factory):
        service = TransactionService(session, factory())

        registrar(service, user_id, account, "120000", description="Mercado")

        session.expire_all()
        assert session.get(Account, account.id).balance == Decimal("880000.00")

    def test_las_invariantes_siguen_aplicando(self, session, user_id, account, factory):
        service = TransactionService(session, factory())

        with pytest.raises(ZeroAmountError):
            registrar(service, user_id, account, "0")

    def test_una_descripcion_hostil_no_rompe_el_registro(self, session, user_id, account, factory):
        service = TransactionService(session, factory())

        movimiento = registrar(service, user_id, account, "1000", description="'; DROP TABLE x; --🍔")

        assert movimiento.category is not None
