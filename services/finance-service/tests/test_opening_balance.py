"""Saldo de apertura e INV-07 en su formulacion corregida (C-17, criterio A-06).

`balance = opening_balance + suma de movimientos`. Portado de
`finance/tests/test_opening_balance.py` del monolito (E2-M3a): creacion,
inmutabilidad del saldo de apertura y recalculo. La constraint de signo y la
anemia del modelo ya estan en `tests/persistence/test_constraints.py` y en
`tests/test_architecture.py`.
"""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import update

from infra.categorizers import MockCategorizer
from models import Account
from services import AccountService, TransactionService

YESTERDAY = date.today() - timedelta(days=1)
APERTURA = Decimal("2000000.00")


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def accounts(session):
    return AccountService(session)


@pytest.fixture
def service(session):
    return TransactionService(session, MockCategorizer("Alimentación", 0.9))


@pytest.fixture
def cuenta(accounts, user_id):
    return accounts.create_account(user_id, "Cuenta corriente", "bank", initial_balance=APERTURA)


def registrar(service, user_id, account, amount, kind="expense", **extra):
    return service.register_transaction(
        user_id=user_id,
        account_id=account.id,
        amount=Decimal(amount),
        transaction_type=kind,
        occurred_on=YESTERDAY,
        **extra,
    )


def fila(session, account):
    session.expire_all()
    return session.get(Account, account.id)


class TestCreacion:
    def test_apertura_y_balance_coinciden_al_crear(self, cuenta):
        assert cuenta.opening_balance == cuenta.balance == APERTURA

    def test_se_persisten_ambos(self, session, cuenta):
        persistida = fila(session, cuenta)
        assert (persistida.opening_balance, persistida.balance) == (APERTURA, APERTURA)

    def test_apertura_por_defecto_es_cero(self, session, accounts, user_id):
        creada = accounts.create_account(user_id, "Sin apertura", "cash")
        assert fila(session, creada).opening_balance == Decimal("0.00")

    def test_la_apertura_es_decimal(self, session, cuenta):
        assert isinstance(fila(session, cuenta).opening_balance, Decimal)

    def test_una_cuenta_de_credito_puede_abrir_en_negativo(self, session, accounts, user_id):
        creada = accounts.create_account(
            user_id, "Tarjeta", "credit", initial_balance=Decimal("-500000.00")
        )
        assert fila(session, creada).opening_balance == Decimal("-500000.00")


class TestInmutabilidad:
    def test_registrar_una_transaccion_no_toca_la_apertura(self, session, service, user_id, cuenta):
        registrar(service, user_id, cuenta, "320000")
        assert fila(session, cuenta).opening_balance == APERTURA

    def test_varias_transacciones_no_tocan_la_apertura(self, session, service, user_id, cuenta):
        for amount in ("1", "2", "3"):
            registrar(service, user_id, cuenta, amount)
        assert fila(session, cuenta).opening_balance == APERTURA

    def test_eliminar_una_transaccion_no_toca_la_apertura(self, session, service, user_id, cuenta):
        movimiento = registrar(service, user_id, cuenta, "320000")
        service.delete_transaction(user_id, movimiento.id)
        assert fila(session, cuenta).opening_balance == APERTURA

    def test_recategorizar_no_toca_la_apertura(self, session, service, user_id, cuenta):
        movimiento = registrar(service, user_id, cuenta, "320000")
        service.recategorize(user_id, movimiento.id, "Compras")
        assert fila(session, cuenta).opening_balance == APERTURA

    def test_archivar_no_toca_la_apertura(self, session, accounts, user_id, cuenta):
        accounts.archive_account(user_id, cuenta.id)
        assert fila(session, cuenta).opening_balance == APERTURA

    def test_recompute_no_toca_la_apertura(self, session, accounts, service, user_id, cuenta):
        registrar(service, user_id, cuenta, "320000")
        accounts.recompute_balance(user_id, cuenta.id)
        assert fila(session, cuenta).opening_balance == APERTURA


class TestRecomputeIncluyeLaApertura:
    def test_devuelve_apertura_mas_suma_no_solo_suma(self, accounts, service, user_id, cuenta):
        registrar(service, user_id, cuenta, "320000")
        registrar(service, user_id, cuenta, "850000", "income", category_name="Salario")

        assert accounts.recompute_balance(user_id, cuenta.id).balance == Decimal("2530000.00")

    def test_repara_un_balance_corrompido_incluyendo_la_apertura(
        self, session, accounts, service, user_id, cuenta
    ):
        registrar(service, user_id, cuenta, "320000")
        session.execute(update(Account).where(Account.id == cuenta.id).values(balance=Decimal("1.00")))
        session.commit()

        assert accounts.recompute_balance(user_id, cuenta.id).balance == Decimal("1680000.00")

    def test_sin_movimientos_devuelve_la_apertura(self, accounts, user_id, cuenta):
        assert accounts.recompute_balance(user_id, cuenta.id).balance == APERTURA

    def test_sobre_una_cuenta_abierta_en_cero_sigue_funcionando(self, accounts, service, user_id):
        creada = accounts.create_account(user_id, "En cero", "bank")
        registrar(service, user_id, creada, "1000", "income", category_name="Salario")

        assert accounts.recompute_balance(user_id, creada.id).balance == Decimal("1000.00")


class TestInv07ConAperturaDistintaDeCero:
    """A-06: tras cinco movimientos mezclados, balance = apertura + suma."""

    MOVIMIENTOS = [
        ("320000", "expense"),
        ("45000", "expense"),
        ("850000", "income"),
        ("12500.50", "expense"),
        ("100000", "income"),
    ]

    @pytest.fixture
    def con_movimientos(self, service, user_id, cuenta):
        for amount, kind in self.MOVIMIENTOS:
            extra = {"category_name": "Salario"} if kind == "income" else {}
            registrar(service, user_id, cuenta, amount, kind, **extra)
        return cuenta

    def test_hay_al_menos_cinco_movimientos(self):
        assert len(self.MOVIMIENTOS) >= 5

    def test_el_balance_es_apertura_mas_suma(self, session, con_movimientos):
        suma = sum(
            Decimal(amount) * (1 if kind == "income" else -1)
            for amount, kind in self.MOVIMIENTOS
        )
        assert fila(session, con_movimientos).balance == APERTURA + suma

    def test_el_valor_exacto(self, session, con_movimientos):
        assert fila(session, con_movimientos).balance == Decimal("2572499.50")

    def test_recompute_confirma_el_mismo_valor(self, accounts, user_id, con_movimientos):
        assert accounts.recompute_balance(user_id, con_movimientos.id).balance == Decimal("2572499.50")

    def test_la_apertura_sigue_intacta(self, session, con_movimientos):
        assert fila(session, con_movimientos).opening_balance == APERTURA
