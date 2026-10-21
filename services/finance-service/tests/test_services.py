"""Tests de `services.py` contra PostgreSQL.

Cubren lo que el contrato HTTP no deja ver: el bloqueo de la fila (A-11), INV-07
tras escrituras mezcladas, la propiedad por `user_id` (INV-03, D-08), la
atomicidad y la inyeccion del categorizador (DIP). Mismos casos que los grupos
equivalentes de `finance/tests/test_services.py` del monolito.
"""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from domain.exceptions import (
    AccountHasTransactionsError,
    AccountNotFoundError,
    ArchivedAccountError,
    CategoryNotFoundError,
    DuplicateAccountNameError,
    NegativeBalanceNotAllowedError,
    TransactionNotFoundError,
    ZeroAmountError,
)
from domain.interfaces import Categorizer
from domain.shared.value_objects import Money
from domain.value_objects import (
    CategorizationSource,
    CategorySuggestion,
    TransactionType,
)
from infra.categorizers import RuleBasedCategorizer
from tests.doubles import MockCategorizer
from infra.outbox import SqlAlchemyOutbox
from models import Account, Transaction
from services import AccountService, TransactionService

YESTERDAY = date.today() - timedelta(days=1)


class CountingCategorizer(Categorizer):
    """Categorizador de prueba que cuenta sus invocaciones."""

    def __init__(self):
        self.calls = 0

    def categorize(self, description, amount, transaction_type):
        self.calls += 1
        return MockCategorizer().categorize(description, amount, transaction_type)


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def other_user_id():
    return uuid4()


@pytest.fixture
def accounts(session):
    return AccountService(session)


@pytest.fixture
def service(session):
    return TransactionService(session, RuleBasedCategorizer(), SqlAlchemyOutbox(session))


@pytest.fixture
def account(accounts, user_id):
    return accounts.create_account(
        user_id, "Banco", "bank", initial_balance=Decimal("1000.00")
    )


@pytest.fixture
def cash_account(accounts, user_id):
    return accounts.create_account(user_id, "Efectivo", "cash")


def register(service, user_id, account, amount="100.00", kind="expense", **extra):
    return service.register_transaction(
        user_id=user_id,
        account_id=account.id,
        amount=Decimal(amount),
        transaction_type=kind,
        occurred_on=extra.pop("occurred_on", YESTERDAY),
        **extra,
    )


def count_transactions(session):
    return session.execute(select(func.count()).select_from(Transaction)).scalar_one()


@pytest.fixture
def captured_sql(session):
    """SQL emitido durante el test, para verificar el bloqueo (A-11)."""
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = session.get_bind().engine
    event.listen(engine, "before_cursor_execute", capture)
    yield statements
    event.remove(engine, "before_cursor_execute", capture)


class TestCrearCuenta:
    def test_crea_la_fila(self, session, account, user_id):
        persisted = session.get(Account, account.id)
        assert persisted.user_id == user_id
        assert persisted.balance == Decimal("1000.00")
        assert persisted.opening_balance == Decimal("1000.00")

    def test_el_nombre_se_recorta(self, accounts, user_id):
        assert accounts.create_account(user_id, "  Ahorros  ", "bank").name == "Ahorros"

    def test_nombre_duplicado_para_el_mismo_usuario(self, accounts, user_id, account):
        with pytest.raises(DuplicateAccountNameError):
            accounts.create_account(user_id, "Banco", "cash")

    def test_tras_el_duplicado_la_sesion_sigue_utilizable(
        self, accounts, user_id, account
    ):
        with pytest.raises(DuplicateAccountNameError):
            accounts.create_account(user_id, "Banco", "cash")
        assert accounts.create_account(user_id, "Otra", "cash").name == "Otra"

    def test_el_mismo_nombre_para_otro_usuario_es_valido(
        self, accounts, other_user_id, account
    ):
        assert accounts.create_account(other_user_id, "Banco", "bank").name == "Banco"

    def test_balance_inicial_negativo_rechazado_en_efectivo(self, accounts, user_id):
        with pytest.raises(NegativeBalanceNotAllowedError):
            accounts.create_account(
                user_id, "Efectivo", "cash", initial_balance=Decimal("-1")
            )


class TestRegistroYBalance:
    def test_un_gasto_resta(self, session, service, user_id, account):
        register(service, user_id, account, "100.00", "expense")
        assert session.get(Account, account.id).balance == Decimal("900.00")

    def test_un_ingreso_suma(self, session, service, user_id, account):
        register(service, user_id, account, "100.00", "income")
        assert session.get(Account, account.id).balance == Decimal("1100.00")

    def test_inv_07_tras_varias_transacciones_mezcladas(
        self, session, service, accounts, user_id, account
    ):
        movimientos = [("120.50", "expense"), ("300", "income"), ("0.75", "expense")]
        creadas = [register(service, user_id, account, m, k) for m, k in movimientos]
        service.delete_transaction(user_id, creadas[0].id)

        persisted = session.get(Account, account.id).balance
        expected = Decimal("1000.00") + Decimal("300") - Decimal("0.75")
        assert persisted == expected
        assert accounts.recompute_balance(user_id, account.id).balance == expected

    def test_recompute_repara_un_balance_corrompido(
        self, session, service, accounts, user_id, account
    ):
        register(service, user_id, account, "100.00", "expense")
        session.get(Account, account.id).balance = Decimal("1.00")
        session.commit()

        assert accounts.recompute_balance(user_id, account.id).balance == Decimal("900.00")

    def test_la_categoria_la_resuelve_el_catalogo(self, service, user_id, account):
        created = register(service, user_id, account, description="taxi al centro")
        assert created.category.name == "Transporte"
        assert created.categorization_source == CategorizationSource.RULE.value


class TestBloqueo:
    """A-11: toda escritura del balance ocurre con la fila bloqueada."""

    def test_registrar_bloquea_la_cuenta(self, service, user_id, account, captured_sql):
        register(service, user_id, account)
        assert any("FOR UPDATE" in sql for sql in captured_sql)

    def test_eliminar_bloquea_la_cuenta(self, service, user_id, account, captured_sql):
        created = register(service, user_id, account)
        captured_sql.clear()
        service.delete_transaction(user_id, created.id)
        assert any("FOR UPDATE" in sql for sql in captured_sql)

    def test_recalcular_bloquea_la_cuenta(self, accounts, user_id, account, captured_sql):
        accounts.recompute_balance(user_id, account.id)
        assert any("FOR UPDATE" in sql for sql in captured_sql)


class TestPropiedad:
    """INV-03 por `user_id`; ajena e inexistente son indistinguibles (D-08)."""

    def test_cuenta_ajena_da_not_found(self, accounts, other_user_id, account):
        with pytest.raises(AccountNotFoundError):
            accounts.get_owned_account(other_user_id, account.id)

    def test_ajena_e_inexistente_dan_el_mismo_error(
        self, accounts, other_user_id, account
    ):
        with pytest.raises(AccountNotFoundError) as ajena:
            accounts.get_owned_account(other_user_id, account.id)
        with pytest.raises(AccountNotFoundError) as inexistente:
            accounts.get_owned_account(other_user_id, uuid4())
        assert ajena.value.code == inexistente.value.code

    def test_identificador_con_forma_invalida(self, accounts, user_id):
        with pytest.raises(AccountNotFoundError):
            accounts.get_owned_account(user_id, "no-es-un-uuid")

    def test_no_puede_registrar_sobre_una_cuenta_ajena(
        self, service, other_user_id, account
    ):
        with pytest.raises(AccountNotFoundError):
            register(service, other_user_id, account)

    def test_no_puede_leer_ni_borrar_una_transaccion_ajena(
        self, service, user_id, other_user_id, account
    ):
        created = register(service, user_id, account)
        with pytest.raises(TransactionNotFoundError):
            service.get_transaction(other_user_id, created.id)
        with pytest.raises(TransactionNotFoundError):
            service.delete_transaction(other_user_id, created.id)
        with pytest.raises(TransactionNotFoundError):
            service.recategorize(other_user_id, created.id, "Compras")

    def test_los_listados_nunca_devuelven_filas_ajenas(
        self, service, accounts, user_id, other_user_id, account
    ):
        register(service, user_id, account)
        assert service.list_transactions(other_user_id).count() == 0
        assert service.list_transactions(other_user_id, account_id=account.id).count() == 0
        assert accounts.list_accounts(other_user_id).count() == 0


class TestAtomicidad:
    @pytest.mark.parametrize(
        "caso,error",
        [
            ({"amount": "0"}, ZeroAmountError),
            ({"kind": "income", "category_name": "Criptomonedas"}, CategoryNotFoundError),
            ({"amount": "5000"}, NegativeBalanceNotAllowedError),
        ],
    )
    def test_ninguna_invariante_violada_deja_rastro(
        self, session, service, user_id, cash_account, caso, error
    ):
        antes = count_transactions(session)
        with pytest.raises(error):
            register(
                service,
                user_id,
                cash_account,
                caso.get("amount", "1"),
                caso.get("kind", "expense"),
                category_name=caso.get("category_name"),
            )
        assert count_transactions(session) == antes
        assert session.get(Account, cash_account.id).balance == Decimal("0.00")

    def test_cuenta_archivada(self, service, accounts, user_id, account):
        accounts.archive_account(user_id, account.id)
        with pytest.raises(ArchivedAccountError):
            register(service, user_id, account)

    def test_inv_13_no_se_borra_una_cuenta_con_transacciones(
        self, session, service, accounts, user_id, account
    ):
        register(service, user_id, account)
        with pytest.raises(AccountHasTransactionsError):
            accounts.delete_account(user_id, account.id)
        assert session.get(Account, account.id) is not None


class TestCategorizadorInyectado:
    """DIP: el servicio usa el categorizador que recibe, y solo cuando hace falta."""

    def test_sin_categoria_manual_se_invoca_una_vez(self, session, user_id, account):
        categorizer = CountingCategorizer()
        register(TransactionService(session, categorizer, SqlAlchemyOutbox(session)), user_id, account)
        assert categorizer.calls == 1

    def test_con_categoria_manual_no_se_invoca(self, session, user_id, account):
        categorizer = CountingCategorizer()
        created = register(
            TransactionService(session, categorizer, SqlAlchemyOutbox(session)),
            user_id,
            account,
            category_name="Compras",
        )
        assert categorizer.calls == 0
        assert created.categorization_source == CategorizationSource.MANUAL.value

    def test_recategorizar_no_mueve_el_balance(self, session, service, user_id, account):
        created = register(service, user_id, account)
        antes = session.get(Account, account.id).balance

        movement = service.recategorize(user_id, created.id, "Compras")

        assert movement.category.name == "Compras"
        assert movement.categorization_confidence == 1.0
        assert session.get(Account, account.id).balance == antes

    def test_el_mock_reporta_su_propia_procedencia(self, session, user_id, account):
        created = register(TransactionService(session, MockCategorizer(), SqlAlchemyOutbox(session)), user_id, account)
        assert created.categorization_source == CategorizationSource.MOCK.value

    def test_un_money_explicito_se_respeta(self, service, user_id, account):
        created = service.register_transaction(
            user_id=user_id,
            account_id=account.id,
            amount=Money("10.00", "COP"),
            transaction_type="expense",
            occurred_on=YESTERDAY,
        )
        assert created.amount == Decimal("10.00")


def test_categorysuggestion_es_el_contrato_del_puerto():
    """El doble de prueba cumple el mismo contrato que los categorizadores reales."""
    suggestion = CountingCategorizer().categorize(
        "x", Money("1", "COP"), TransactionType.EXPENSE
    )
    assert isinstance(suggestion, CategorySuggestion)
