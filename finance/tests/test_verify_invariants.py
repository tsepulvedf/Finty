"""Tests de la auditoria de invariantes y del comando `verify_invariants`.

La auditoria es la contraparte de lectura de lo que M5 y M5.1 dejaron por
escritura: si INV-07 se sostiene, `audit_balances` no debe encontrar nada, y si
alguien escribe por fuera de los servicios, debe encontrarlo.

Tocan la base de datos: llevan la marca correspondiente.
"""
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.domain.value_objects import Money
from finance.models import Account, Transaction
from finance.services import (
    MISSING_CATEGORY,
    MISSING_SOURCE,
    AccountService,
    BalanceAuditResult,
    TransactionService,
)
from finance.infra.categorizers import MockCategorizer
from identity.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "Contrasena-Segura-2026"
YESTERDAY = date.today() - timedelta(days=1)
APERTURA = Decimal("2000000.00")


@pytest.fixture
def accounts():
    return AccountService()


@pytest.fixture
def service():
    return TransactionService(MockCategorizer("Alimentación", 0.9))


@pytest.fixture
def ana():
    return User.objects.create_user(email="ana@finty.co", password=PASSWORD)


@pytest.fixture
def juan():
    return User.objects.create_user(email="juan@finty.co", password=PASSWORD)


@pytest.fixture
def cuenta(ana, accounts, service):
    """Cuenta con apertura distinta de cero y tres movimientos."""
    creada = accounts.create_account(
        ana, "Cuenta corriente", "bank", initial_balance=Money(APERTURA, "COP")
    )
    registrar(service, ana, creada, "320000", "expense")
    registrar(service, ana, creada, "45000", "expense")
    registrar(service, ana, creada, "850000", "income", category_name="Salario")
    creada.refresh_from_db()
    return creada


def registrar(service, user, account, amount, transaction_type="expense", **extra):
    """Atajo para registrar una transaccion valida."""
    return service.register_transaction(
        user=user,
        account_id=account.pk,
        amount=Decimal(amount),
        transaction_type=transaction_type,
        occurred_on=YESTERDAY,
        **extra,
    )


def corromper(account, valor="9999.99"):
    """Escribe un balance incorrecto saltandose la capa de servicios."""
    Account.objects.filter(pk=account.pk).update(balance=Decimal(valor))
    account.refresh_from_db()


def ejecutar(*args, **kwargs):
    """Corre el comando y devuelve `(codigo_de_salida, salida)`."""
    salida = StringIO()
    try:
        call_command("verify_invariants", *args, stdout=salida, **kwargs)
    except SystemExit as exc:
        return exc.code, salida.getvalue()
    return None, salida.getvalue()


# ---------------------------------------------------------------------------
# audit_balances
# ---------------------------------------------------------------------------


class TestAuditarBalances:
    """`AccountService.audit_balances`."""

    def test_una_base_consistente_no_reporta_desviaciones(self, accounts, cuenta):
        resultados = accounts.audit_balances()

        assert len(resultados) == 1
        assert all(r.is_consistent() for r in resultados)

    def test_respeta_el_saldo_de_apertura(self, accounts, cuenta):
        """C-17: la invariante es `apertura + suma`, no solo la suma."""
        resultado = accounts.audit_balances()[0]

        assert cuenta.opening_balance == APERTURA
        assert resultado.calculated == Money("2485000.00", "COP")
        assert resultado.is_consistent()

    def test_detecta_un_balance_corrompido(self, accounts, cuenta):
        corromper(cuenta)

        resultado = accounts.audit_balances()[0]

        assert not resultado.is_consistent()
        assert resultado.persisted == Money("9999.99", "COP")
        assert resultado.calculated == Money("2485000.00", "COP")

    def test_reporta_la_diferencia_exacta(self, accounts, cuenta):
        corromper(cuenta)

        assert accounts.audit_balances()[0].difference() == Money("-2475000.01", "COP")

    def test_lleva_los_datos_de_identificacion(self, accounts, ana, cuenta):
        resultado = accounts.audit_balances()[0]

        assert resultado.account_id == cuenta.pk
        assert resultado.account_name == "Cuenta corriente"
        assert resultado.owner_email == ana.email

    def test_una_cuenta_sin_movimientos_es_consistente(self, accounts, ana):
        accounts.create_account(ana, "Vacia", "cash", currency="COP")

        assert all(r.is_consistent() for r in accounts.audit_balances())

    def test_restringe_el_alcance_al_usuario(self, accounts, ana, juan, cuenta):
        accounts.create_account(juan, "Suya", "cash", currency="COP")

        assert len(accounts.audit_balances()) == 2
        assert len(accounts.audit_balances(ana)) == 1
        assert accounts.audit_balances(ana)[0].owner_email == ana.email

    def test_no_escribe_nada(self, accounts, cuenta):
        corromper(cuenta)

        accounts.audit_balances()

        cuenta.refresh_from_db()
        assert cuenta.balance == Decimal("9999.99")

    def test_el_resultado_es_inmutable(self, accounts, cuenta):
        from dataclasses import FrozenInstanceError

        resultado = accounts.audit_balances()[0]

        with pytest.raises(FrozenInstanceError):
            resultado.persisted = Money("0", "COP")

    def test_is_consistent_es_metodo_y_no_propiedad(self):
        """ADR-03 prohibe propiedades calculadas; no se invita a imitarlas."""
        assert callable(BalanceAuditResult.is_consistent)
        assert not isinstance(BalanceAuditResult.__dict__["is_consistent"], property)


# ---------------------------------------------------------------------------
# audit_categorization
# ---------------------------------------------------------------------------


class TestAuditarCategorizacion:
    """`AccountService.audit_categorization`."""

    def test_una_base_consistente_no_reporta_nada(self, accounts, cuenta):
        assert accounts.audit_categorization() == []

    def test_detecta_procedencia_sin_categoria(self, accounts, cuenta):
        """INV-08 violada: algo clasifico pero no quedo categoria."""
        movimiento = Transaction.objects.filter(account=cuenta).first()
        Transaction.objects.filter(pk=movimiento.pk).update(category=None)

        hallazgos = accounts.audit_categorization()

        assert len(hallazgos) == 1
        assert hallazgos[0].reason == MISSING_CATEGORY
        assert hallazgos[0].transaction_id == movimiento.pk
        assert hallazgos[0].category_name is None
        assert hallazgos[0].categorization_source is not None

    def test_detecta_categoria_sin_procedencia(self, accounts, cuenta):
        """Delata una escritura que evadio la capa de servicios."""
        movimiento = Transaction.objects.filter(account=cuenta).first()
        Transaction.objects.filter(pk=movimiento.pk).update(
            categorization_source=None, categorization_confidence=None
        )

        hallazgos = accounts.audit_categorization()

        assert len(hallazgos) == 1
        assert hallazgos[0].reason == MISSING_SOURCE
        assert hallazgos[0].category_name is not None
        assert hallazgos[0].categorization_source is None

    def test_una_transaccion_sin_categoria_ni_procedencia_es_coherente(
        self, accounts, cuenta
    ):
        """Ambos nulos es un estado legitimo: nunca se invoco la categorizacion."""
        movimiento = Transaction.objects.filter(account=cuenta).first()
        Transaction.objects.filter(pk=movimiento.pk).update(
            category=None, categorization_source=None, categorization_confidence=None
        )

        assert accounts.audit_categorization() == []

    def test_lleva_los_datos_de_identificacion(self, accounts, ana, cuenta):
        movimiento = Transaction.objects.filter(account=cuenta).first()
        Transaction.objects.filter(pk=movimiento.pk).update(category=None)

        hallazgo = accounts.audit_categorization()[0]

        assert hallazgo.account_name == "Cuenta corriente"
        assert hallazgo.owner_email == ana.email

    def test_restringe_el_alcance_al_usuario(
        self, accounts, service, ana, juan, cuenta
    ):
        ajena = accounts.create_account(juan, "Suya", "cash", currency="COP")
        movimiento_ajeno = registrar(
            service, juan, ajena, "1000", "income", category_name="Salario"
        )
        Transaction.objects.filter(pk=movimiento_ajeno.pk).update(category=None)
        propio = Transaction.objects.filter(account=cuenta).first()
        Transaction.objects.filter(pk=propio.pk).update(category=None)

        assert len(accounts.audit_categorization()) == 2
        assert len(accounts.audit_categorization(ana)) == 1
        assert accounts.audit_categorization(ana)[0].owner_email == ana.email

    def test_no_escribe_nada(self, accounts, cuenta):
        movimiento = Transaction.objects.filter(account=cuenta).first()
        Transaction.objects.filter(pk=movimiento.pk).update(category=None)

        accounts.audit_categorization()

        assert Transaction.objects.get(pk=movimiento.pk).category_id is None


# ---------------------------------------------------------------------------
# El comando
# ---------------------------------------------------------------------------


class TestComandoSinDesviaciones:
    """Base consistente."""

    def test_sale_con_cero(self, cuenta):
        codigo, _ = ejecutar()

        assert codigo == 0

    def test_lo_dice_en_la_salida(self, cuenta):
        _, salida = ejecutar()

        assert "CONSISTENTE" in salida
        assert "Todos los balances coinciden" in salida

    def test_informa_cuantas_cuentas_audito(self, cuenta):
        _, salida = ejecutar()

        assert "Cuentas auditadas          : 1" in salida
        assert "Balances desviados         : 0" in salida


class TestComandoConDesviaciones:
    """Balance corrompido a mano."""

    def test_sale_con_uno(self, cuenta):
        corromper(cuenta)

        codigo, _ = ejecutar()

        assert codigo == 1

    def test_la_cuenta_aparece_en_el_reporte(self, cuenta):
        corromper(cuenta)

        _, salida = ejecutar()

        assert "Cuenta corriente" in salida
        assert "ana@finty.co" in salida

    def test_muestra_la_diferencia_exacta(self, cuenta):
        corromper(cuenta)

        _, salida = ejecutar()

        assert "9999.99 COP" in salida
        assert "2485000.00 COP" in salida
        assert "-2475000.01 COP" in salida

    def test_el_resumen_marca_el_estado(self, cuenta):
        corromper(cuenta)

        _, salida = ejecutar()

        assert "INCONSISTENTE" in salida
        assert "Balances desviados         : 1" in salida


class TestComandoConFix:
    """`--fix` recalcula las cuentas desviadas."""

    def test_repara_y_la_segunda_corrida_sale_con_cero(self, cuenta):
        corromper(cuenta)

        codigo_fix, _ = ejecutar("--fix")
        codigo_despues, _ = ejecutar()

        assert codigo_fix == 0
        assert codigo_despues == 0

    def test_el_balance_queda_correcto(self, cuenta):
        corromper(cuenta)

        ejecutar("--fix")

        cuenta.refresh_from_db()
        assert cuenta.balance == Decimal("2485000.00")

    def test_reporta_el_antes_y_el_despues(self, cuenta):
        corromper(cuenta)

        _, salida = ejecutar("--fix")

        assert "Correccion (--fix)" in salida
        assert "9999.99 COP -> 2485000.00" in salida
        assert "Todos los balances quedaron al dia" in salida

    def test_no_altera_el_saldo_de_apertura(self, cuenta):
        corromper(cuenta)

        ejecutar("--fix")

        cuenta.refresh_from_db()
        assert cuenta.opening_balance == APERTURA

    def test_no_altera_las_transacciones(self, cuenta):
        antes = list(
            Transaction.objects.filter(account=cuenta)
            .order_by("pk")
            .values_list("pk", "amount", "type")
        )
        corromper(cuenta)

        ejecutar("--fix")

        despues = list(
            Transaction.objects.filter(account=cuenta)
            .order_by("pk")
            .values_list("pk", "amount", "type")
        )
        assert antes == despues

    def test_sobre_una_base_consistente_no_cambia_nada(self, cuenta):
        antes = cuenta.balance

        codigo, salida = ejecutar("--fix")

        cuenta.refresh_from_db()
        assert codigo == 0
        assert cuenta.balance == antes
        assert "Correccion (--fix)" not in salida


class TestComandoNoCorrigeCategorizacion:
    """`--fix` nunca toca INV-08: eso requiere decision humana."""

    @pytest.fixture
    def descategorizada(self, cuenta):
        movimiento = Transaction.objects.filter(account=cuenta).first()
        Transaction.objects.filter(pk=movimiento.pk).update(category=None)
        return movimiento

    def test_la_reporta(self, descategorizada):
        _, salida = ejecutar()

        assert MISSING_CATEGORY in salida
        assert "Transacciones incoherentes : 1" in salida

    def test_no_la_corrige(self, descategorizada):
        ejecutar("--fix")

        assert Transaction.objects.get(pk=descategorizada.pk).category_id is None

    def test_lo_dice_explicitamente_en_la_salida(self, descategorizada):
        _, salida = ejecutar("--fix")

        assert "--fix NO corrige estas incoherencias" in salida
        assert "decision humana" in salida

    def test_no_afecta_el_codigo_de_salida(self, descategorizada):
        """El codigo refleja desviaciones de balance, no de categorizacion."""
        codigo, _ = ejecutar()

        assert codigo == 0


class TestComandoConUser:
    """`--user` restringe el alcance."""

    @pytest.fixture
    def cuenta_ajena(self, accounts, service, juan):
        creada = accounts.create_account(
            juan, "Cuenta de Juan", "bank", initial_balance=Money("500000", "COP")
        )
        registrar(service, juan, creada, "100000", "expense")
        creada.refresh_from_db()
        return creada

    def test_solo_audita_las_cuentas_del_usuario(self, cuenta, cuenta_ajena):
        _, salida = ejecutar("--user", "ana@finty.co")

        assert "Cuentas auditadas          : 1" in salida
        assert "Cuenta de Juan" not in salida

    def test_la_cuenta_ajena_desviada_no_aparece(self, cuenta, cuenta_ajena):
        corromper(cuenta_ajena, "1.00")

        codigo, salida = ejecutar("--user", "ana@finty.co")

        assert codigo == 0
        assert "Cuenta de Juan" not in salida

    def test_la_cuenta_ajena_desviada_no_se_corrige(self, cuenta, cuenta_ajena):
        corromper(cuenta_ajena, "1.00")

        ejecutar("--user", "ana@finty.co", "--fix")

        cuenta_ajena.refresh_from_db()
        assert cuenta_ajena.balance == Decimal("1.00")

    def test_sin_user_si_la_detecta(self, cuenta, cuenta_ajena):
        corromper(cuenta_ajena, "1.00")

        codigo, salida = ejecutar()

        assert codigo == 1
        assert "Cuenta de Juan" in salida

    def test_corrige_la_propia_sin_tocar_la_ajena(self, cuenta, cuenta_ajena):
        corromper(cuenta)
        corromper(cuenta_ajena, "1.00")

        ejecutar("--user", "ana@finty.co", "--fix")

        cuenta.refresh_from_db()
        cuenta_ajena.refresh_from_db()
        assert cuenta.balance == Decimal("2485000.00")
        assert cuenta_ajena.balance == Decimal("1.00")

    def test_email_inexistente_lanza_command_error(self, cuenta):
        with pytest.raises(CommandError):
            call_command("verify_invariants", "--user", "fantasma@finty.co")

    def test_el_mensaje_nombra_el_email(self, cuenta):
        with pytest.raises(CommandError) as error:
            call_command("verify_invariants", "--user", "fantasma@finty.co")

        assert "fantasma@finty.co" in str(error.value)

    def test_acepta_el_email_con_otra_capitalizacion(self, cuenta):
        codigo, salida = ejecutar("--user", "ANA@Finty.CO")

        assert codigo == 0
        assert "ana@finty.co" in salida


class TestComandoSobreBaseVacia:
    """Sin cuentas, la auditoria es trivialmente consistente."""

    def test_sale_con_cero(self):
        codigo, salida = ejecutar()

        assert codigo == 0
        assert "Cuentas auditadas          : 0" in salida
