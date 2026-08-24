"""Tests de `AccountService` y `TransactionService`.

Tocan la base de datos: llevan la marca correspondiente. Es donde se verifica lo
que ninguna capa inferior puede verificar sola: INV-07 bajo bloqueo, INV-14 con
saldo autoritativo, atomicidad y aislamiento entre usuarios.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction as db_transaction
from django.db.transaction import TransactionManagementError
from django.test.utils import CaptureQueriesContext
from django.db import connection

from core.domain.value_objects import Money
from finance.domain.exceptions import (
    AccountHasTransactionsError,
    AccountNotFoundError,
    ArchivedAccountError,
    CategoryNotFoundError,
    CategoryTypeMismatchError,
    DuplicateAccountNameError,
    FutureTransactionDateError,
    NegativeBalanceNotAllowedError,
    TransactionNotFoundError,
    ZeroAmountError,
)
from finance.domain.interfaces import Categorizer
from finance.domain.logic import BalanceCalculator
from finance.domain.value_objects import (
    CategorizationSource,
    CategorySuggestion,
    TransactionType,
)
from finance.infra.categorizers import (
    AICategorizer,
    MockCategorizer,
    RuleBasedCategorizer,
)
from finance.models import Account, Category, Transaction
from finance.services import AccountService, TransactionService
from identity.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "Contrasena-Segura-2026"
TODAY = date.today()
# Saldo con que arranca la cuenta bancaria de las pruebas. Se fija por fiat, como
# lo haria una carga inicial de datos, y hay que recordarlo aparte porque el
# modelo no tiene columna de saldo de apertura.
OPENING_BALANCE = "1000000.00"
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class CountingCategorizer(Categorizer):
    """Doble que cuenta cuantas veces se le invoca."""

    def __init__(self, category_name="Alimentación"):
        self.calls = 0
        self._category_name = category_name

    def categorize(self, description, amount, transaction_type):
        self.calls += 1
        return CategorySuggestion(
            self._category_name, 0.8, CategorizationSource.AI
        )


@pytest.fixture
def user():
    return User.objects.create_user(email="ana@finty.co", password=PASSWORD)


@pytest.fixture
def other_user():
    return User.objects.create_user(email="juan@finty.co", password=PASSWORD)


@pytest.fixture
def accounts():
    return AccountService()


@pytest.fixture
def account(user, accounts):
    """Cuenta bancaria con saldo, del usuario principal."""
    created = accounts.create_account(user, "Cuenta corriente", "bank", currency="COP")
    created.balance = Decimal(OPENING_BALANCE)
    created.save(update_fields=["balance"])
    return created


@pytest.fixture
def cash_account(user, accounts):
    """Cuenta de efectivo sin saldo: no admite numeros rojos."""
    return accounts.create_account(user, "Efectivo", "cash", currency="COP")


@pytest.fixture
def credit_account(user, accounts):
    """Tarjeta de credito: si admite saldo negativo."""
    return accounts.create_account(user, "Tarjeta", "credit", currency="COP")


@pytest.fixture
def service():
    """`TransactionService` con un categorizador de categoria fija."""
    return TransactionService(MockCategorizer("Alimentación", 0.9))


def registrar(service, user, account, amount, transaction_type="expense", **extra):
    """Atajo para registrar una transaccion valida."""
    return service.register_transaction(
        user=user,
        account_id=account.pk,
        amount=Decimal(amount),
        transaction_type=transaction_type,
        occurred_on=extra.pop("occurred_on", YESTERDAY),
        **extra,
    )


def balance_esperado(account, opening="0"):
    """Recalcula el balance con el dominio, como referencia de INV-07.

    `opening` es el saldo con que se abrio la cuenta. Hay que pasarlo aparte
    porque el modelo no lo guarda en una columna propia: `balance` es el saldo
    actual, no el de apertura. Ver la limitacion documentada en
    `AccountService.recompute_balance`.
    """
    movimientos = [
        (Money(row.amount, account.currency), TransactionType.from_value(row.type))
        for row in account.transactions.all()
    ]
    return BalanceCalculator.recompute(Money(opening, account.currency), movimientos)


# ---------------------------------------------------------------------------
# AccountService
# ---------------------------------------------------------------------------


class TestCrearCuenta:
    """`create_account`."""

    def test_crea_la_fila(self, user, accounts):
        cuenta = accounts.create_account(user, "Ahorros", "bank", currency="COP")

        assert Account.objects.filter(pk=cuenta.pk).exists()
        assert cuenta.user == user
        assert cuenta.type == "bank"
        assert cuenta.balance == Decimal("0.00")
        assert cuenta.currency == "COP"

    def test_con_balance_inicial(self, user, accounts):
        cuenta = accounts.create_account(
            user, "Ahorros", "bank", initial_balance=Money("500000", "COP")
        )

        assert cuenta.balance == Decimal("500000.00")
        assert cuenta.currency == "COP"

    def test_el_nombre_se_recorta(self, user, accounts):
        assert accounts.create_account(user, "  Ahorros  ", "bank", currency="COP").name == "Ahorros"

    def test_nombre_duplicado_para_el_mismo_usuario(self, user, accounts, account):
        with pytest.raises(DuplicateAccountNameError):
            accounts.create_account(user, "Cuenta corriente", "cash", currency="COP")

    def test_el_mismo_nombre_para_otro_usuario_es_valido(
        self, user, other_user, accounts, account
    ):
        ajena = accounts.create_account(
            other_user, "Cuenta corriente", "cash", currency="COP"
        )

        assert ajena.pk != account.pk
        assert Account.objects.filter(name="Cuenta corriente").count() == 2

    def test_tras_el_duplicado_la_sesion_sigue_utilizable(self, user, accounts, account):
        """El bloque atomico propio evita dejar la transaccion abortada."""
        with pytest.raises(DuplicateAccountNameError):
            accounts.create_account(user, "Cuenta corriente", "cash", currency="COP")

        assert Account.objects.filter(user=user).count() == 1

    def test_balance_inicial_negativo_rechazado_en_efectivo(self, user, accounts):
        with pytest.raises(NegativeBalanceNotAllowedError):
            accounts.create_account(
                user, "Efectivo", "cash", initial_balance=Money("-1", "COP")
            )

    def test_balance_inicial_negativo_aceptado_en_credito(self, user, accounts):
        cuenta = accounts.create_account(
            user, "Tarjeta", "credit", initial_balance=Money("-500000", "COP")
        )

        assert cuenta.balance == Decimal("-500000.00")

    def test_nada_se_persiste_si_el_builder_rechaza(self, user, accounts):
        with pytest.raises(NegativeBalanceNotAllowedError):
            accounts.create_account(
                user, "Efectivo", "cash", initial_balance=Money("-1", "COP")
            )

        assert not Account.objects.filter(name="Efectivo").exists()


class TestObtenerCuenta:
    """`get_owned_account` y `build_snapshot`."""

    def test_devuelve_la_cuenta_propia(self, user, accounts, account):
        assert accounts.get_owned_account(user, account.pk).pk == account.pk

    def test_cuenta_inexistente(self, user, accounts):
        from uuid import uuid4

        with pytest.raises(AccountNotFoundError):
            accounts.get_owned_account(user, uuid4())

    def test_identificador_con_forma_invalida(self, user, accounts):
        with pytest.raises(AccountNotFoundError):
            accounts.get_owned_account(user, "no-es-un-uuid")

    def test_build_snapshot_reconstruye_el_money(self, accounts, account):
        snapshot = accounts.build_snapshot(account)

        assert snapshot.account_id == account.pk
        assert snapshot.balance == Money("1000000.00", "COP")
        assert snapshot.currency == "COP"
        assert snapshot.account_type.value == "bank"
        assert snapshot.is_archived is False


class TestListarArchivarBorrar:
    """`list_accounts`, `archive_account` y `delete_account`."""

    def test_list_accounts_omite_archivadas_por_defecto(self, user, accounts, account):
        accounts.archive_account(user, account.pk)

        assert list(accounts.list_accounts(user)) == []

    def test_list_accounts_puede_incluir_archivadas(self, user, accounts, account):
        accounts.archive_account(user, account.pk)

        assert len(accounts.list_accounts(user, include_archived=True)) == 1

    def test_archivar_con_transacciones_presentes(self, user, accounts, account, service):
        registrar(service, user, account, "50000")

        archivada = accounts.archive_account(user, account.pk)

        assert archivada.is_archived is True

    def test_archivar_es_idempotente(self, user, accounts, account):
        accounts.archive_account(user, account.pk)
        segunda = accounts.archive_account(user, account.pk)

        assert segunda.is_archived is True

    def test_borrar_una_cuenta_sin_transacciones(self, user, accounts, account):
        accounts.delete_account(user, account.pk)

        assert not Account.objects.filter(pk=account.pk).exists()

    def test_borrar_una_cuenta_con_transacciones(self, user, accounts, account, service):
        registrar(service, user, account, "50000")

        with pytest.raises(AccountHasTransactionsError):
            accounts.delete_account(user, account.pk)

        assert Account.objects.filter(pk=account.pk).exists()


# ---------------------------------------------------------------------------
# Registro y balance
# ---------------------------------------------------------------------------


class TestRegistroYBalance:
    """Camino feliz de `register_transaction`."""

    def test_crea_la_fila_y_resuelve_la_categoria(self, user, account, service):
        movimiento = registrar(service, user, account, "120000", description="Mercado")

        assert Transaction.objects.filter(pk=movimiento.pk).exists()
        assert movimiento.account_id == account.pk
        assert movimiento.amount == Decimal("120000.00")
        assert movimiento.type == "expense"
        assert movimiento.category.name == "Alimentación"
        assert movimiento.description == "Mercado"

    def test_un_gasto_resta(self, user, account, service):
        registrar(service, user, account, "120000", "expense")

        account.refresh_from_db()
        assert account.balance == Decimal("880000.00")

    def test_un_ingreso_suma(self, user, account, service):
        registrar(service, user, account, "500000", "income", category_name="Salario")

        account.refresh_from_db()
        assert account.balance == Decimal("1500000.00")

    def test_el_monto_se_guarda_positivo(self, user, account, service):
        movimiento = registrar(service, user, account, "120000", "expense")

        assert movimiento.amount == Decimal("120000.00")
        assert movimiento.amount > 0

    def test_el_monto_es_decimal(self, user, account, service):
        movimiento = registrar(service, user, account, "120000.55")

        assert isinstance(movimiento.amount, Decimal)
        assert movimiento.amount == Decimal("120000.55")

    def test_acepta_un_money_explicito(self, user, account, service):
        movimiento = service.register_transaction(
            user, account.pk, Money("75000", "COP"), "expense", YESTERDAY
        )

        assert movimiento.amount == Decimal("75000.00")

    def test_inv_07_tras_varias_transacciones_mezcladas(self, user, account, service):
        """Criterio A-06: el balance persistido coincide con `recompute`."""
        movimientos = [
            ("500000", "income", "Salario"),
            ("120000", "expense", None),
            ("35000", "expense", None),
            ("250000", "income", "Freelance"),
            ("899000", "expense", None),
            ("1200", "expense", None),
        ]
        for monto, tipo, categoria in movimientos:
            registrar(
                service, user, account, monto, tipo, category_name=categoria
            )

        account.refresh_from_db()

        assert account.transactions.count() == 6
        assert account.balance == balance_esperado(account, OPENING_BALANCE).amount

    def test_los_decimales_no_se_pierden(self, user, account, service):
        for monto in ["0.01", "0.02", "0.03", "1234.56"]:
            registrar(service, user, account, monto)

        account.refresh_from_db()
        assert account.balance == Decimal("998765.38")


class TestRecomputeBalance:
    """`recompute_balance` es la operacion de reparacion."""

    def test_repara_un_balance_corrompido(self, user, accounts, cash_account, service):
        """La cuenta abre en cero, asi que el recuento desde cero es exacto."""
        registrar(service, user, cash_account, "500000", "income", category_name="Salario")
        registrar(service, user, cash_account, "120000", "expense")
        cash_account.refresh_from_db()
        correcto = cash_account.balance

        Account.objects.filter(pk=cash_account.pk).update(balance=Decimal("999.99"))

        reparada = accounts.recompute_balance(user, cash_account.pk)

        assert reparada.balance == correcto == Decimal("380000.00")

    def test_coincide_con_el_dominio(self, user, accounts, cash_account, service):
        registrar(service, user, cash_account, "5000", "income", category_name="Salario")
        registrar(service, user, cash_account, "1500", "expense")

        reparada = accounts.recompute_balance(user, cash_account.pk)

        assert reparada.balance == balance_esperado(cash_account).amount

    def test_sin_transacciones_deja_el_balance_en_cero(self, user, accounts, cash_account):
        assert accounts.recompute_balance(user, cash_account.pk).balance == Decimal("0.00")


# ---------------------------------------------------------------------------
# Bloqueo
# ---------------------------------------------------------------------------


class TestBloqueo:
    """El `select_for_update()` que sostiene INV-07 bajo concurrencia."""

    def test_el_sql_contiene_for_update(self, user, account, service):
        """Criterio A-11."""
        with CaptureQueriesContext(connection) as consultas:
            registrar(service, user, account, "50000")

        sql_con_bloqueo = [
            consulta["sql"]
            for consulta in consultas.captured_queries
            if "FOR UPDATE" in consulta["sql"].upper()
        ]

        assert sql_con_bloqueo, "register_transaction no bloqueo la fila de la cuenta"
        assert "finance_account" in sql_con_bloqueo[0]

    def test_delete_transaction_tambien_bloquea(self, user, account, service):
        movimiento = registrar(service, user, account, "50000")

        with CaptureQueriesContext(connection) as consultas:
            service.delete_transaction(user, movimiento.pk)

        assert any(
            "FOR UPDATE" in consulta["sql"].upper()
            for consulta in consultas.captured_queries
        )

    def test_recompute_balance_tambien_bloquea(self, user, accounts, account):
        with CaptureQueriesContext(connection) as consultas:
            accounts.recompute_balance(user, account.pk)

        assert any(
            "FOR UPDATE" in consulta["sql"].upper()
            for consulta in consultas.captured_queries
        )


@pytest.mark.django_db(transaction=True)
class TestBloqueoFueraDeTransaccion:
    """`get_locked_account` exige un bloque atomico.

    Lleva `transaction=True` porque el envoltorio atomico por defecto de
    pytest-django haria que `select_for_update()` se creyera dentro de una
    transaccion y el error nunca apareceria.
    """

    def test_fuera_de_un_bloque_atomico_lanza(self):
        usuario = User.objects.create_user(email="lock@finty.co", password=PASSWORD)
        cuenta = AccountService().create_account(
            usuario, "Cuenta", "bank", currency="COP"
        )

        with pytest.raises(TransactionManagementError):
            AccountService().get_locked_account(usuario, cuenta.pk)

    def test_dentro_de_un_bloque_atomico_funciona(self):
        usuario = User.objects.create_user(email="lock2@finty.co", password=PASSWORD)
        cuenta = AccountService().create_account(
            usuario, "Cuenta", "bank", currency="COP"
        )

        with db_transaction.atomic():
            bloqueada = AccountService().get_locked_account(usuario, cuenta.pk)

        assert bloqueada.pk == cuenta.pk


# ---------------------------------------------------------------------------
# Propiedad y aislamiento
# ---------------------------------------------------------------------------


class TestPropiedad:
    """Criterio A-07: un usuario no alcanza datos de otro por ningun camino."""

    def test_cuenta_ajena_da_not_found(self, other_user, accounts, account):
        with pytest.raises(AccountNotFoundError):
            accounts.get_owned_account(other_user, account.pk)

    def test_cuenta_ajena_y_cuenta_inexistente_son_indistinguibles(
        self, other_user, accounts, account
    ):
        """No distinguir revela menos: 403 delataria que el id esta en uso."""
        from uuid import uuid4

        with pytest.raises(AccountNotFoundError) as ajena:
            accounts.get_owned_account(other_user, account.pk)
        with pytest.raises(AccountNotFoundError) as inexistente:
            accounts.get_owned_account(other_user, uuid4())

        assert str(ajena.value) == str(inexistente.value)
        assert ajena.value.code == inexistente.value.code

    def test_no_puede_registrar_sobre_una_cuenta_ajena(self, other_user, account, service):
        with pytest.raises(AccountNotFoundError):
            registrar(service, other_user, account, "50000")

        account.refresh_from_db()
        assert account.balance == Decimal("1000000.00")

    def test_no_puede_archivar_una_cuenta_ajena(self, other_user, accounts, account):
        with pytest.raises(AccountNotFoundError):
            accounts.archive_account(other_user, account.pk)

    def test_no_puede_borrar_una_cuenta_ajena(self, other_user, accounts, account):
        with pytest.raises(AccountNotFoundError):
            accounts.delete_account(other_user, account.pk)

    def test_no_puede_leer_una_transaccion_ajena(self, user, other_user, account, service):
        movimiento = registrar(service, user, account, "50000")

        with pytest.raises(TransactionNotFoundError):
            service.get_transaction(other_user, movimiento.pk)

    def test_no_puede_recategorizar_una_transaccion_ajena(
        self, user, other_user, account, service
    ):
        movimiento = registrar(service, user, account, "50000")

        with pytest.raises(TransactionNotFoundError):
            service.recategorize(other_user, movimiento.pk, "Transporte")

        movimiento.refresh_from_db()
        assert movimiento.category.name == "Alimentación"

    def test_no_puede_eliminar_una_transaccion_ajena(
        self, user, other_user, account, service
    ):
        movimiento = registrar(service, user, account, "50000")

        with pytest.raises(TransactionNotFoundError):
            service.delete_transaction(other_user, movimiento.pk)

        assert Transaction.objects.filter(pk=movimiento.pk).exists()

    def test_list_transactions_nunca_devuelve_filas_ajenas(
        self, user, other_user, accounts, account, service
    ):
        registrar(service, user, account, "50000")
        ajena = accounts.create_account(other_user, "Suya", "cash", currency="COP")
        registrar(service, other_user, ajena, "1000", "income", category_name="Salario")

        de_ana = list(service.list_transactions(user))
        de_juan = list(service.list_transactions(other_user))

        assert len(de_ana) == 1
        assert len(de_juan) == 1
        assert de_ana[0].account.user_id == user.pk
        assert de_juan[0].account.user_id == other_user.pk

    def test_filtrar_por_una_cuenta_ajena_no_devuelve_nada(
        self, user, other_user, account, service
    ):
        registrar(service, user, account, "50000")

        assert not service.list_transactions(other_user, account_id=account.pk).exists()

    def test_list_accounts_no_devuelve_cuentas_ajenas(
        self, other_user, accounts, account
    ):
        assert list(accounts.list_accounts(other_user)) == []


# ---------------------------------------------------------------------------
# Invariantes en el servicio
# ---------------------------------------------------------------------------


class TestInvariantesEnElServicio:
    """Lo que el servicio verifica y el dominio no puede verificar solo."""

    def test_inv_14_gasto_que_dejaria_negativa_una_cuenta_cash(
        self, user, cash_account, service
    ):
        with pytest.raises(NegativeBalanceNotAllowedError):
            registrar(service, user, cash_account, "1")

    def test_inv_14_no_persiste_nada(self, user, cash_account, service):
        with pytest.raises(NegativeBalanceNotAllowedError):
            registrar(service, user, cash_account, "1")

        cash_account.refresh_from_db()
        assert cash_account.balance == Decimal("0.00")
        assert Transaction.objects.count() == 0

    def test_inv_14_la_misma_operacion_procede_en_credito(
        self, user, credit_account, service
    ):
        movimiento = registrar(service, user, credit_account, "500000")

        credit_account.refresh_from_db()
        assert credit_account.balance == Decimal("-500000.00")
        assert Transaction.objects.filter(pk=movimiento.pk).exists()

    def test_inv_14_el_gasto_hasta_dejar_en_cero_si_procede(
        self, user, cash_account, service
    ):
        Account.objects.filter(pk=cash_account.pk).update(balance=Decimal("100.00"))

        registrar(service, user, cash_account, "100")

        cash_account.refresh_from_db()
        assert cash_account.balance == Decimal("0.00")

    def test_cuenta_archivada(self, user, accounts, account, service):
        accounts.archive_account(user, account.pk)

        with pytest.raises(ArchivedAccountError):
            registrar(service, user, account, "50000")

    def test_fecha_futura(self, user, account, service):
        with pytest.raises(FutureTransactionDateError):
            registrar(service, user, account, "50000", occurred_on=TOMORROW)

    def test_la_fecha_de_hoy_es_valida(self, user, account, service):
        assert registrar(service, user, account, "50000", occurred_on=TODAY) is not None

    def test_monto_cero(self, user, account, service):
        with pytest.raises(ZeroAmountError):
            registrar(service, user, account, "0")

    def test_categoria_inexistente(self, user, account, service):
        with pytest.raises(CategoryNotFoundError):
            registrar(service, user, account, "50000", category_name="Criptomonedas")

    def test_categoria_de_ingreso_sobre_un_gasto(self, user, account, service):
        with pytest.raises(CategoryTypeMismatchError):
            registrar(service, user, account, "50000", "expense", category_name="Salario")

    def test_categoria_de_gasto_sobre_un_ingreso(self, user, account, service):
        with pytest.raises(CategoryTypeMismatchError):
            registrar(
                service, user, account, "50000", "income", category_name="Alimentación"
            )

    @pytest.mark.parametrize(
        "caso",
        [
            {"amount": "0"},
            {"occurred_on": TOMORROW},
            {"category_name": "Criptomonedas"},
        ],
    )
    def test_ninguna_invariante_violada_deja_rastro(self, user, account, service, caso):
        monto = caso.pop("amount", "50000")

        with pytest.raises(Exception):
            registrar(service, user, account, monto, **caso)

        account.refresh_from_db()
        assert account.balance == Decimal("1000000.00")
        assert Transaction.objects.count() == 0


# ---------------------------------------------------------------------------
# Atomicidad
# ---------------------------------------------------------------------------


class TestAtomicidad:
    """Un fallo en la persistencia revierte la operacion entera."""

    def test_fallo_al_guardar_el_balance_revierte_la_transaccion(
        self, user, account, service
    ):
        filas_antes = Transaction.objects.count()
        balance_antes = account.balance

        with patch.object(Account, "save", side_effect=RuntimeError("fallo forzado")):
            with pytest.raises(RuntimeError):
                registrar(service, user, account, "50000")

        account.refresh_from_db()

        assert Transaction.objects.count() == filas_antes
        assert account.balance == balance_antes

    def test_fallo_al_crear_la_transaccion_no_mueve_el_balance(
        self, user, account, service
    ):
        with patch.object(
            Transaction.objects, "create", side_effect=RuntimeError("fallo forzado")
        ):
            with pytest.raises(RuntimeError):
                registrar(service, user, account, "50000")

        account.refresh_from_db()

        assert account.balance == Decimal("1000000.00")
        assert Transaction.objects.count() == 0

    def test_el_conteo_de_filas_es_identico_antes_y_despues(
        self, user, account, service
    ):
        registrar(service, user, account, "10000")
        cuentas_antes = Account.objects.count()
        movimientos_antes = Transaction.objects.count()

        with patch.object(Account, "save", side_effect=RuntimeError()):
            with pytest.raises(RuntimeError):
                registrar(service, user, account, "50000")

        assert Account.objects.count() == cuentas_antes
        assert Transaction.objects.count() == movimientos_antes


# ---------------------------------------------------------------------------
# Categorizacion
# ---------------------------------------------------------------------------


class TestCategorizacion:
    """Automatica y manual."""

    def test_con_mock_categorizer_sale_la_categoria_configurada(self, user, account):
        service = TransactionService(MockCategorizer("Transporte", 0.65))

        movimiento = registrar(service, user, account, "20000")

        assert movimiento.category.name == "Transporte"
        assert movimiento.categorization_source == CategorizationSource.RULE.value
        assert movimiento.categorization_confidence == 0.65

    def test_con_categoria_manual_la_fuente_es_manual(self, user, account, service):
        movimiento = registrar(
            service, user, account, "20000", category_name="Transporte"
        )

        assert movimiento.category.name == "Transporte"
        assert movimiento.categorization_source == CategorizationSource.MANUAL.value
        assert movimiento.categorization_confidence == 1.0

    def test_con_categoria_manual_el_categorizador_no_se_invoca(self, user, account):
        contador = CountingCategorizer()
        service = TransactionService(contador)

        registrar(service, user, account, "20000", category_name="Transporte")

        assert contador.calls == 0

    def test_sin_categoria_manual_el_categorizador_se_invoca_una_vez(
        self, user, account
    ):
        contador = CountingCategorizer()
        service = TransactionService(contador)

        registrar(service, user, account, "20000")

        assert contador.calls == 1

    def test_el_categorizador_no_se_invoca_si_una_invariante_falla(self, user, account):
        contador = CountingCategorizer()
        service = TransactionService(contador)

        with pytest.raises(ZeroAmountError):
            registrar(service, user, account, "0")

        assert contador.calls == 0


class TestRecategorizar:
    """`recategorize`."""

    def test_cambia_categoria_y_fuente(self, user, account, service):
        movimiento = registrar(service, user, account, "50000")

        recategorizada = service.recategorize(user, movimiento.pk, "Transporte")

        assert recategorizada.category.name == "Transporte"
        assert recategorizada.categorization_source == CategorizationSource.MANUAL.value
        assert recategorizada.categorization_confidence == 1.0

    def test_no_mueve_el_balance(self, user, account, service):
        movimiento = registrar(service, user, account, "50000")
        account.refresh_from_db()
        balance_antes = account.balance

        service.recategorize(user, movimiento.pk, "Transporte")

        account.refresh_from_db()
        assert account.balance == balance_antes

    def test_no_cambia_el_monto_ni_el_tipo(self, user, account, service):
        movimiento = registrar(service, user, account, "50000")

        service.recategorize(user, movimiento.pk, "Transporte")

        movimiento.refresh_from_db()
        assert movimiento.amount == Decimal("50000.00")
        assert movimiento.type == "expense"

    def test_persiste_el_cambio(self, user, account, service):
        movimiento = registrar(service, user, account, "50000")

        service.recategorize(user, movimiento.pk, "Transporte")

        assert Transaction.objects.get(pk=movimiento.pk).category.name == "Transporte"

    def test_categoria_de_tipo_incorrecto(self, user, account, service):
        movimiento = registrar(service, user, account, "50000")

        with pytest.raises(CategoryTypeMismatchError):
            service.recategorize(user, movimiento.pk, "Salario")

    def test_categoria_inexistente(self, user, account, service):
        movimiento = registrar(service, user, account, "50000")

        with pytest.raises(CategoryNotFoundError):
            service.recategorize(user, movimiento.pk, "Criptomonedas")

    def test_transaccion_inexistente(self, user, service):
        from uuid import uuid4

        with pytest.raises(TransactionNotFoundError):
            service.recategorize(user, uuid4(), "Transporte")


class TestEliminarTransaccion:
    """`delete_transaction` deshace el efecto sobre el balance."""

    def test_elimina_la_fila(self, user, account, service):
        movimiento = registrar(service, user, account, "50000")

        service.delete_transaction(user, movimiento.pk)

        assert not Transaction.objects.filter(pk=movimiento.pk).exists()

    def test_revierte_un_gasto(self, user, account, service):
        movimiento = registrar(service, user, account, "50000", "expense")

        service.delete_transaction(user, movimiento.pk)

        account.refresh_from_db()
        assert account.balance == Decimal("1000000.00")

    def test_revierte_un_ingreso(self, user, account, service):
        movimiento = registrar(
            service, user, account, "50000", "income", category_name="Salario"
        )

        service.delete_transaction(user, movimiento.pk)

        account.refresh_from_db()
        assert account.balance == Decimal("1000000.00")

    def test_el_balance_sigue_coincidiendo_con_recompute(self, user, account, service):
        primera = registrar(service, user, account, "50000", "expense")
        registrar(service, user, account, "30000", "expense")

        service.delete_transaction(user, primera.pk)

        account.refresh_from_db()
        assert account.balance == balance_esperado(account, OPENING_BALANCE).amount

    def test_eliminar_un_ingreso_puede_rechazarse(self, user, cash_account, service):
        """Contraintuitivo pero correcto: dejaria la cuenta en un estado invalido."""
        ingreso = registrar(
            service, user, cash_account, "100000", "income", category_name="Salario"
        )
        registrar(service, user, cash_account, "80000", "expense")

        with pytest.raises(NegativeBalanceNotAllowedError):
            service.delete_transaction(user, ingreso.pk)

        assert Transaction.objects.filter(pk=ingreso.pk).exists()
        cash_account.refresh_from_db()
        assert cash_account.balance == Decimal("20000.00")

    def test_el_mismo_caso_procede_en_credito(self, user, credit_account, service):
        ingreso = registrar(
            service, user, credit_account, "100000", "income", category_name="Salario"
        )
        registrar(service, user, credit_account, "80000", "expense")

        service.delete_transaction(user, ingreso.pk)

        credit_account.refresh_from_db()
        assert credit_account.balance == Decimal("-80000.00")

    def test_transaccion_inexistente(self, user, service):
        from uuid import uuid4

        with pytest.raises(TransactionNotFoundError):
            service.delete_transaction(user, uuid4())


class TestListarTransacciones:
    """`list_transactions` y sus filtros."""

    @pytest.fixture
    def poblada(self, user, account, service):
        registrar(service, user, account, "10000", "expense", occurred_on=date(2026, 1, 15))
        registrar(service, user, account, "20000", "expense", occurred_on=date(2026, 3, 10))
        registrar(
            service, user, account, "30000", "income",
            category_name="Salario", occurred_on=date(2026, 5, 20),
        )
        return account

    def test_devuelve_todas(self, user, service, poblada):
        assert service.list_transactions(user).count() == 3

    def test_filtra_por_cuenta(self, user, service, poblada):
        assert service.list_transactions(user, account_id=poblada.pk).count() == 3

    def test_filtra_por_categoria(self, user, service, poblada):
        salario = Category.objects.get(name="Salario")

        assert service.list_transactions(user, category_id=salario.pk).count() == 1

    def test_filtra_por_fecha_desde(self, user, service, poblada):
        assert service.list_transactions(user, date_from=date(2026, 3, 1)).count() == 2

    def test_filtra_por_fecha_hasta(self, user, service, poblada):
        assert service.list_transactions(user, date_to=date(2026, 3, 31)).count() == 2

    def test_filtra_por_rango(self, user, service, poblada):
        movimientos = service.list_transactions(
            user, date_from=date(2026, 2, 1), date_to=date(2026, 4, 1)
        )
        assert movimientos.count() == 1

    def test_ordering_mas_reciente_primero(self, user, service, poblada):
        fechas = [m.occurred_on for m in service.list_transactions(user)]

        assert fechas == sorted(fechas, reverse=True)

    def test_select_related_evita_el_n_mas_1(self, user, service, poblada):
        """Una sola consulta para las tres filas con su cuenta y su categoria."""
        with CaptureQueriesContext(connection) as consultas:
            for movimiento in service.list_transactions(user):
                _ = movimiento.account.name
                _ = movimiento.category.name if movimiento.category else None

        assert len(consultas.captured_queries) == 1


# ---------------------------------------------------------------------------
# LSP en el servicio
# ---------------------------------------------------------------------------


CATEGORIZADORES = [
    pytest.param(RuleBasedCategorizer, id="RuleBased"),
    pytest.param(MockCategorizer, id="Mock"),
    pytest.param(lambda: AICategorizer(client=None), id="AI-sin-cliente"),
]


@pytest.mark.parametrize("factory", CATEGORIZADORES)
class TestLSPEnElServicio:
    """Criterio A-08: el servicio funciona igual con las tres implementaciones.

    Ni `TransactionService` ni estos tests contienen una sola linea condicional
    sobre que categorizador se inyecto. Eso es lo que significa que sean
    sustituibles.
    """

    def test_registra_una_transaccion_valida(self, user, account, factory):
        service = TransactionService(factory())

        movimiento = registrar(
            service, user, account, "120000", description="Mercado de la semana"
        )

        assert Transaction.objects.filter(pk=movimiento.pk).exists()

    def test_la_categoria_queda_resuelta(self, user, account, factory):
        service = TransactionService(factory())

        movimiento = registrar(
            service, user, account, "120000", description="Mercado de la semana"
        )

        assert movimiento.category is not None
        assert Category.objects.filter(pk=movimiento.category_id).exists()

    def test_la_categoria_corresponde_al_tipo(self, user, account, factory):
        service = TransactionService(factory())

        movimiento = registrar(
            service, user, account, "500000", "income", description="Pago de nomina"
        )

        assert movimiento.category.applies_to == "income"

    def test_la_fuente_y_la_confianza_quedan_registradas(self, user, account, factory):
        service = TransactionService(factory())

        movimiento = registrar(service, user, account, "120000", description="Taxi")

        assert movimiento.categorization_source in {"ai", "rule", "manual"}
        assert 0.0 <= movimiento.categorization_confidence <= 1.0

    def test_el_balance_queda_correcto(self, user, account, factory):
        service = TransactionService(factory())

        registrar(service, user, account, "120000", description="Mercado")

        account.refresh_from_db()
        assert account.balance == Decimal("880000.00")

    def test_las_invariantes_siguen_aplicando(self, user, account, factory):
        service = TransactionService(factory())

        with pytest.raises(ZeroAmountError):
            registrar(service, user, account, "0")

    def test_una_descripcion_hostil_no_rompe_el_registro(self, user, account, factory):
        service = TransactionService(factory())

        movimiento = registrar(
            service, user, account, "1000", description="'; DROP TABLE x; --🍔"
        )

        assert movimiento.category is not None
