"""Tests del saldo de apertura de `Account` (correccion C-17).

La invariante INV-07 en su formulacion corregida es
`balance = opening_balance + suma de movimientos`. Antes de existir esta columna,
`recompute_balance` recalculaba desde cero y una cuenta abierta con saldo inicial
lo perdia al repararse. Estos tests fijan ese comportamiento.

Tocan la base de datos: llevan la marca correspondiente.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db import transaction as db_transaction

from core.domain.value_objects import Money
from finance.domain.logic import BalanceCalculator
from finance.domain.value_objects import TransactionType
from finance.infra.categorizers import MockCategorizer
from finance.models import Account, Transaction
from finance.services import AccountService, TransactionService
from identity.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "Contrasena-Segura-2026"
YESTERDAY = date.today() - timedelta(days=1)
APERTURA = Decimal("1000000.00")


@pytest.fixture
def user():
    return User.objects.create_user(email="ana@finty.co", password=PASSWORD)


@pytest.fixture
def accounts():
    return AccountService()


@pytest.fixture
def service():
    return TransactionService(MockCategorizer("Alimentación", 0.9))


@pytest.fixture
def account(user, accounts):
    """Cuenta bancaria abierta con un saldo inicial distinto de cero."""
    return accounts.create_account(
        user, "Cuenta corriente", "bank", initial_balance=Money(APERTURA, "COP")
    )


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


def suma_de_movimientos(account):
    """Suma con signo de las transacciones de la cuenta, sin la apertura."""
    return BalanceCalculator.recompute(
        Money.zero(account.currency),
        [
            (Money(row.amount, account.currency), TransactionType.from_value(row.type))
            for row in account.transactions.all()
        ],
    )


class TestCreacion:
    """La apertura y el saldo vivo arrancan iguales."""

    def test_apertura_y_balance_coinciden_al_crear(self, account):
        assert account.opening_balance == APERTURA
        assert account.balance == APERTURA

    def test_se_persisten_ambos(self, account):
        guardada = Account.objects.get(pk=account.pk)

        assert guardada.opening_balance == APERTURA
        assert guardada.balance == APERTURA

    def test_apertura_por_defecto_es_cero(self, user, accounts):
        cuenta = accounts.create_account(user, "Efectivo", "cash", currency="COP")

        assert cuenta.opening_balance == Decimal("0.00")
        assert cuenta.balance == Decimal("0.00")

    def test_la_apertura_es_decimal(self, account):
        assert isinstance(Account.objects.get(pk=account.pk).opening_balance, Decimal)

    def test_una_cuenta_de_credito_puede_abrir_en_negativo(self, user, accounts):
        cuenta = accounts.create_account(
            user, "Tarjeta", "credit", initial_balance=Money("-500000", "COP")
        )

        assert cuenta.opening_balance == Decimal("-500000.00")


class TestInmutabilidad:
    """`opening_balance` no vuelve a moverse tras la creacion."""

    def test_registrar_una_transaccion_no_toca_la_apertura(
        self, user, account, service
    ):
        antes = account.opening_balance

        registrar(service, user, account, "120000", "expense")

        account.refresh_from_db()
        assert account.opening_balance == antes
        assert account.balance != antes

    def test_varias_transacciones_no_tocan_la_apertura(self, user, account, service):
        for monto, tipo in [("50000", "expense"), ("30000", "expense")]:
            registrar(service, user, account, monto, tipo)
        registrar(service, user, account, "10000", "income", category_name="Salario")

        account.refresh_from_db()
        assert account.opening_balance == APERTURA

    def test_eliminar_una_transaccion_no_toca_la_apertura(
        self, user, account, service
    ):
        movimiento = registrar(service, user, account, "120000", "expense")

        service.delete_transaction(user, movimiento.pk)

        account.refresh_from_db()
        assert account.opening_balance == APERTURA
        assert account.balance == APERTURA

    def test_recategorizar_no_toca_la_apertura(self, user, account, service):
        movimiento = registrar(service, user, account, "120000", "expense")

        service.recategorize(user, movimiento.pk, "Transporte")

        account.refresh_from_db()
        assert account.opening_balance == APERTURA

    def test_archivar_no_toca_la_apertura(self, user, accounts, account):
        accounts.archive_account(user, account.pk)

        account.refresh_from_db()
        assert account.opening_balance == APERTURA

    def test_recompute_no_toca_la_apertura(self, user, accounts, account, service):
        registrar(service, user, account, "120000", "expense")

        accounts.recompute_balance(user, account.pk)

        account.refresh_from_db()
        assert account.opening_balance == APERTURA


class TestRecomputeIncluyeLaApertura:
    """El nucleo de la correccion C-17."""

    def test_devuelve_apertura_mas_suma_no_solo_suma(
        self, user, accounts, account, service
    ):
        registrar(service, user, account, "500000", "income", category_name="Salario")
        registrar(service, user, account, "120000", "expense")
        registrar(service, user, account, "35000", "expense")

        reparada = accounts.recompute_balance(user, account.pk)
        suma = suma_de_movimientos(account)

        assert suma.amount == Decimal("345000.00")
        assert reparada.balance == APERTURA + suma.amount == Decimal("1345000.00")
        assert reparada.balance != suma.amount

    def test_repara_un_balance_corrompido_incluyendo_la_apertura(
        self, user, accounts, account, service
    ):
        registrar(service, user, account, "120000", "expense")
        account.refresh_from_db()
        correcto = account.balance

        Account.objects.filter(pk=account.pk).update(balance=Decimal("-77777.77"))

        reparada = accounts.recompute_balance(user, account.pk)

        assert reparada.balance == correcto == Decimal("880000.00")

    def test_sin_movimientos_devuelve_la_apertura(self, user, accounts, account):
        assert accounts.recompute_balance(user, account.pk).balance == APERTURA

    def test_sobre_una_cuenta_abierta_en_cero_sigue_funcionando(
        self, user, accounts, service
    ):
        cuenta = accounts.create_account(user, "Efectivo", "cash", currency="COP")
        registrar(service, user, cuenta, "5000", "income", category_name="Salario")

        assert accounts.recompute_balance(user, cuenta.pk).balance == Decimal("5000.00")


class TestInv07ConAperturaDistintaDeCero:
    """INV-07 sobre una cuenta con apertura real y varios movimientos."""

    MOVIMIENTOS = [
        ("500000", "income", "Salario"),
        ("120000", "expense", None),
        ("35000", "expense", None),
        ("250000", "income", "Freelance"),
        ("899000", "expense", None),
        ("1200.55", "expense", None),
    ]

    @pytest.fixture
    def poblada(self, user, account, service):
        for monto, tipo, categoria in self.MOVIMIENTOS:
            registrar(service, user, account, monto, tipo, category_name=categoria)
        account.refresh_from_db()
        return account

    def test_hay_al_menos_cinco_movimientos(self, poblada):
        assert poblada.transactions.count() >= 5

    def test_el_balance_es_apertura_mas_suma(self, poblada):
        esperado = BalanceCalculator.recompute(
            Money(poblada.opening_balance, poblada.currency),
            [
                (
                    Money(row.amount, poblada.currency),
                    TransactionType.from_value(row.type),
                )
                for row in poblada.transactions.all()
            ],
        )

        assert poblada.balance == esperado.amount

    def test_el_valor_exacto(self, poblada):
        assert poblada.balance == Decimal("694799.45")

    def test_recompute_confirma_el_mismo_valor(self, user, accounts, poblada):
        antes = poblada.balance

        assert accounts.recompute_balance(user, poblada.pk).balance == antes

    def test_la_apertura_sigue_intacta(self, poblada):
        assert poblada.opening_balance == APERTURA


class TestConstraintDeSigno:
    """`ck_account_opening_balance_sign`: INV-14 en el instante de creacion.

    Cada asercion va en su propio bloque atomico: un `IntegrityError` deja la
    transaccion de PostgreSQL abortada y contaminaria las siguientes.
    """

    @pytest.mark.parametrize("account_type", ["cash", "bank"])
    def test_apertura_negativa_rechazada_por_la_base(self, user, account_type):
        """Insercion directa, saltandose el servicio: la base defiende igual."""
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                Account.objects.create(
                    user=user,
                    name=f"Rara {account_type}",
                    type=account_type,
                    opening_balance=Decimal("-0.01"),
                )

    def test_apertura_negativa_aceptada_en_credito(self, user):
        cuenta = Account.objects.create(
            user=user,
            name="Tarjeta",
            type="credit",
            opening_balance=Decimal("-500000.00"),
            balance=Decimal("-500000.00"),
        )

        assert cuenta.opening_balance == Decimal("-500000.00")

    @pytest.mark.parametrize("account_type", ["cash", "bank", "credit"])
    def test_apertura_en_cero_valida_en_los_tres_tipos(self, user, account_type):
        cuenta = Account.objects.create(
            user=user, name=f"Cuenta {account_type}", type=account_type
        )

        assert cuenta.opening_balance == Decimal("0.00")

    @pytest.mark.parametrize("account_type", ["cash", "bank", "credit"])
    def test_apertura_positiva_valida_en_los_tres_tipos(self, user, account_type):
        cuenta = Account.objects.create(
            user=user,
            name=f"Cuenta {account_type}",
            type=account_type,
            opening_balance=Decimal("1.00"),
        )

        assert cuenta.opening_balance == Decimal("1.00")

    def test_el_balance_vivo_si_puede_ser_negativo_en_cualquier_tipo(self, user):
        """La constraint restringe la apertura, no el saldo vivo.

        INV-14 sobre el saldo vivo depende de estado variable y se verifica en el
        servicio bajo bloqueo, no en la base.
        """
        cuenta = Account.objects.create(
            user=user, name="Efectivo", type="cash", balance=Decimal("-100.00")
        )

        assert cuenta.balance == Decimal("-100.00")


class TestModeloSigueAnemico:
    """La columna nueva no trajo logica al modelo."""

    def test_no_sobreescribe_save_clean_ni_delete(self):
        for metodo in ("save", "clean", "delete"):
            assert metodo not in Account.__dict__

    def test_no_declara_properties_calculadas(self):
        propiedades = [
            nombre
            for nombre, valor in Account.__dict__.items()
            if isinstance(valor, property)
        ]
        assert propiedades == []

    def test_ninguna_transaccion_referencia_la_apertura(self, user, account, service):
        """`Transaction` no sabe nada del saldo de apertura."""
        registrar(service, user, account, "1000", "expense")

        assert not any(
            "opening" in field.name for field in Transaction._meta.get_fields()
        )
