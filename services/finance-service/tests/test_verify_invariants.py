"""Tests de la auditoria de invariantes y de `flask verify-invariants`.

Portados de `finance/tests/test_verify_invariants.py` del monolito (E2-M3a), con
las mismas clases y aserciones. Lo unico que cambia es la identidad del
propietario: `user_id` en lugar de email (ADR-10), asi que `--user` recibe un
UUID y el reporte muestra el UUID.

Tocan la base de datos de pruebas.
"""
from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from domain.shared.value_objects import Money
from infra.categorizers import MockCategorizer
from models import Account, Transaction
from services import (
    MISSING_CATEGORY,
    MISSING_SOURCE,
    AccountService,
    BalanceAuditResult,
    TransactionService,
)

YESTERDAY = date.today() - timedelta(days=1)
APERTURA = Decimal("2000000.00")


@pytest.fixture
def accounts(session):
    return AccountService(session)


@pytest.fixture
def service(session):
    return TransactionService(session, MockCategorizer("Alimentación", 0.9))


@pytest.fixture
def ana():
    return uuid4()


@pytest.fixture
def juan():
    return uuid4()


def registrar(service, user_id, account, amount, transaction_type="expense", **extra):
    """Atajo para registrar una transaccion valida."""
    return service.register_transaction(
        user_id=user_id,
        account_id=account.id,
        amount=Decimal(amount),
        transaction_type=transaction_type,
        occurred_on=YESTERDAY,
        **extra,
    )


@pytest.fixture
def cuenta(ana, accounts, service):
    """Cuenta con apertura distinta de cero y tres movimientos."""
    creada = accounts.create_account(
        ana, "Cuenta corriente", "bank", initial_balance=Money(APERTURA, "COP")
    )
    registrar(service, ana, creada, "320000", "expense")
    registrar(service, ana, creada, "45000", "expense")
    registrar(service, ana, creada, "850000", "income", category_name="Salario")
    return creada


def recargar(session, model, pk):
    """Lee la fila desde la base, sin el mapa de identidad de la sesion."""
    session.expire_all()
    return session.get(model, pk)


def corromper(session, account, valor="9999.99"):
    """Escribe un balance incorrecto saltandose la capa de servicios."""
    session.execute(
        update(Account).where(Account.id == account.id).values(balance=Decimal(valor))
    )
    session.commit()


def actualizar_transaccion(session, movement_id, **valores):
    session.execute(update(Transaction).where(Transaction.id == movement_id).values(**valores))
    session.commit()


def primera_transaccion(session, account):
    return session.execute(
        select(Transaction).where(Transaction.account_id == account.id).order_by(Transaction.id)
    ).scalars().first()


@pytest.fixture
def ejecutar(app):
    """Corre el comando y devuelve `(codigo_de_salida, salida)`."""
    runner = app.test_cli_runner()

    def _run(*args):
        result = runner.invoke(args=["verify-invariants", *args])
        return result.exit_code, result.output

    return _run


# ---------------------------------------------------------------------------
# audit_balances
# ---------------------------------------------------------------------------


class TestAuditarBalances:
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

    def test_detecta_un_balance_corrompido(self, session, accounts, cuenta):
        corromper(session, cuenta)

        resultado = accounts.audit_balances()[0]

        assert not resultado.is_consistent()
        assert resultado.persisted == Money("9999.99", "COP")
        assert resultado.calculated == Money("2485000.00", "COP")

    def test_reporta_la_diferencia_exacta(self, session, accounts, cuenta):
        corromper(session, cuenta)

        assert accounts.audit_balances()[0].difference() == Money("-2475000.01", "COP")

    def test_lleva_los_datos_de_identificacion(self, accounts, ana, cuenta):
        resultado = accounts.audit_balances()[0]

        assert resultado.account_id == cuenta.id
        assert resultado.account_name == "Cuenta corriente"
        assert resultado.owner_id == ana

    def test_una_cuenta_sin_movimientos_es_consistente(self, accounts, ana):
        accounts.create_account(ana, "Vacia", "cash", currency="COP")

        assert all(r.is_consistent() for r in accounts.audit_balances())

    def test_restringe_el_alcance_al_usuario(self, accounts, ana, juan, cuenta):
        accounts.create_account(juan, "Suya", "cash", currency="COP")

        assert len(accounts.audit_balances()) == 2
        assert len(accounts.audit_balances(ana)) == 1
        assert accounts.audit_balances(ana)[0].owner_id == ana

    def test_no_escribe_nada(self, session, accounts, cuenta):
        corromper(session, cuenta)

        accounts.audit_balances()

        assert recargar(session, Account, cuenta.id).balance == Decimal("9999.99")

    def test_el_resultado_es_inmutable(self, accounts, cuenta):
        resultado = accounts.audit_balances()[0]

        with pytest.raises(FrozenInstanceError):
            resultado.persisted = Money("0", "COP")

    def test_is_consistent_es_metodo_y_no_propiedad(self):
        assert callable(BalanceAuditResult.is_consistent)
        assert not isinstance(BalanceAuditResult.__dict__["is_consistent"], property)


# ---------------------------------------------------------------------------
# audit_categorization
# ---------------------------------------------------------------------------


class TestAuditarCategorizacion:
    def test_una_base_consistente_no_reporta_nada(self, accounts, cuenta):
        assert accounts.audit_categorization() == []

    def test_detecta_procedencia_sin_categoria(self, session, accounts, cuenta):
        movimiento = primera_transaccion(session, cuenta)
        actualizar_transaccion(session, movimiento.id, category_id=None)

        hallazgos = accounts.audit_categorization()

        assert len(hallazgos) == 1
        assert hallazgos[0].reason == MISSING_CATEGORY
        assert hallazgos[0].transaction_id == movimiento.id
        assert hallazgos[0].category_name is None
        assert hallazgos[0].categorization_source is not None

    def test_detecta_categoria_sin_procedencia(self, session, accounts, cuenta):
        movimiento = primera_transaccion(session, cuenta)
        actualizar_transaccion(
            session, movimiento.id, categorization_source=None, categorization_confidence=None
        )

        hallazgos = accounts.audit_categorization()

        assert len(hallazgos) == 1
        assert hallazgos[0].reason == MISSING_SOURCE
        assert hallazgos[0].category_name is not None
        assert hallazgos[0].categorization_source is None

    def test_una_transaccion_sin_categoria_ni_procedencia_es_coherente(
        self, session, accounts, cuenta
    ):
        movimiento = primera_transaccion(session, cuenta)
        actualizar_transaccion(
            session,
            movimiento.id,
            category_id=None,
            categorization_source=None,
            categorization_confidence=None,
        )

        assert accounts.audit_categorization() == []

    def test_lleva_los_datos_de_identificacion(self, session, accounts, ana, cuenta):
        movimiento = primera_transaccion(session, cuenta)
        actualizar_transaccion(session, movimiento.id, category_id=None)

        hallazgo = accounts.audit_categorization()[0]

        assert hallazgo.account_name == "Cuenta corriente"
        assert hallazgo.owner_id == ana

    def test_restringe_el_alcance_al_usuario(self, session, accounts, service, ana, juan, cuenta):
        ajena = accounts.create_account(juan, "Suya", "cash", currency="COP")
        movimiento_ajeno = registrar(service, juan, ajena, "1000", "income", category_name="Salario")
        actualizar_transaccion(session, movimiento_ajeno.id, category_id=None)
        propio = primera_transaccion(session, cuenta)
        actualizar_transaccion(session, propio.id, category_id=None)

        assert len(accounts.audit_categorization()) == 2
        assert len(accounts.audit_categorization(ana)) == 1
        assert accounts.audit_categorization(ana)[0].owner_id == ana

    def test_no_escribe_nada(self, session, accounts, cuenta):
        movimiento = primera_transaccion(session, cuenta)
        actualizar_transaccion(session, movimiento.id, category_id=None)

        accounts.audit_categorization()

        assert recargar(session, Transaction, movimiento.id).category_id is None


# ---------------------------------------------------------------------------
# El comando
# ---------------------------------------------------------------------------


class TestComandoSinDesviaciones:
    def test_sale_con_cero(self, ejecutar, cuenta):
        codigo, _ = ejecutar()

        assert codigo == 0

    def test_lo_dice_en_la_salida(self, ejecutar, cuenta):
        _, salida = ejecutar()

        assert "CONSISTENTE" in salida
        assert "Todos los balances coinciden" in salida

    def test_informa_cuantas_cuentas_audito(self, ejecutar, cuenta):
        _, salida = ejecutar()

        assert "Cuentas auditadas          : 1" in salida
        assert "Balances desviados         : 0" in salida


class TestComandoConDesviaciones:
    def test_sale_con_uno(self, session, ejecutar, cuenta):
        corromper(session, cuenta)

        codigo, _ = ejecutar()

        assert codigo == 1

    def test_la_cuenta_aparece_en_el_reporte(self, session, ejecutar, ana, cuenta):
        corromper(session, cuenta)

        _, salida = ejecutar()

        assert "Cuenta corriente" in salida
        assert str(ana) in salida

    def test_muestra_la_diferencia_exacta(self, session, ejecutar, cuenta):
        corromper(session, cuenta)

        _, salida = ejecutar()

        assert "9999.99 COP" in salida
        assert "2485000.00 COP" in salida
        assert "-2475000.01 COP" in salida

    def test_el_resumen_marca_el_estado(self, session, ejecutar, cuenta):
        corromper(session, cuenta)

        _, salida = ejecutar()

        assert "INCONSISTENTE" in salida
        assert "Balances desviados         : 1" in salida


class TestComandoConFix:
    def test_repara_y_la_segunda_corrida_sale_con_cero(self, session, ejecutar, cuenta):
        corromper(session, cuenta)

        codigo_fix, _ = ejecutar("--fix")
        codigo_despues, _ = ejecutar()

        assert codigo_fix == 0
        assert codigo_despues == 0

    def test_el_balance_queda_correcto(self, session, ejecutar, cuenta):
        corromper(session, cuenta)

        ejecutar("--fix")

        assert recargar(session, Account, cuenta.id).balance == Decimal("2485000.00")

    def test_reporta_el_antes_y_el_despues(self, session, ejecutar, cuenta):
        corromper(session, cuenta)

        _, salida = ejecutar("--fix")

        assert "Correccion (--fix)" in salida
        assert "9999.99 COP -> 2485000.00" in salida
        assert "Todos los balances quedaron al dia" in salida

    def test_no_altera_el_saldo_de_apertura(self, session, ejecutar, cuenta):
        corromper(session, cuenta)

        ejecutar("--fix")

        assert recargar(session, Account, cuenta.id).opening_balance == APERTURA

    def test_no_altera_las_transacciones(self, session, ejecutar, cuenta):
        def movimientos():
            session.expire_all()
            return session.execute(
                select(Transaction.id, Transaction.amount, Transaction.type)
                .where(Transaction.account_id == cuenta.id)
                .order_by(Transaction.id)
            ).all()

        antes = movimientos()
        corromper(session, cuenta)

        ejecutar("--fix")

        assert movimientos() == antes

    def test_sobre_una_base_consistente_no_cambia_nada(self, session, ejecutar, cuenta):
        antes = cuenta.balance

        codigo, salida = ejecutar("--fix")

        assert codigo == 0
        assert recargar(session, Account, cuenta.id).balance == antes
        assert "Correccion (--fix)" not in salida


class TestComandoNoCorrigeCategorizacion:
    @pytest.fixture
    def descategorizada(self, session, cuenta):
        movimiento = primera_transaccion(session, cuenta)
        actualizar_transaccion(session, movimiento.id, category_id=None)
        return movimiento

    def test_la_reporta(self, ejecutar, descategorizada):
        _, salida = ejecutar()

        assert MISSING_CATEGORY in salida
        assert "Transacciones incoherentes : 1" in salida

    def test_no_la_corrige(self, session, ejecutar, descategorizada):
        ejecutar("--fix")

        assert recargar(session, Transaction, descategorizada.id).category_id is None

    def test_lo_dice_explicitamente_en_la_salida(self, ejecutar, descategorizada):
        _, salida = ejecutar("--fix")

        assert "--fix NO corrige estas incoherencias" in salida
        assert "decision humana" in salida

    def test_no_afecta_el_codigo_de_salida(self, ejecutar, descategorizada):
        codigo, _ = ejecutar()

        assert codigo == 0


class TestComandoConUser:
    @pytest.fixture
    def cuenta_ajena(self, accounts, service, juan):
        creada = accounts.create_account(
            juan, "Cuenta de Juan", "bank", initial_balance=Money("500000", "COP")
        )
        registrar(service, juan, creada, "100000", "expense")
        return creada

    def test_solo_audita_las_cuentas_del_usuario(self, ejecutar, ana, cuenta, cuenta_ajena):
        _, salida = ejecutar("--user", str(ana))

        assert "Cuentas auditadas          : 1" in salida
        assert "Cuenta de Juan" not in salida

    def test_la_cuenta_ajena_desviada_no_aparece(self, session, ejecutar, ana, cuenta, cuenta_ajena):
        corromper(session, cuenta_ajena, "1.00")

        codigo, salida = ejecutar("--user", str(ana))

        assert codigo == 0
        assert "Cuenta de Juan" not in salida

    def test_la_cuenta_ajena_desviada_no_se_corrige(self, session, ejecutar, ana, cuenta, cuenta_ajena):
        corromper(session, cuenta_ajena, "1.00")

        ejecutar("--user", str(ana), "--fix")

        assert recargar(session, Account, cuenta_ajena.id).balance == Decimal("1.00")

    def test_sin_user_si_la_detecta(self, session, ejecutar, cuenta, cuenta_ajena):
        corromper(session, cuenta_ajena, "1.00")

        codigo, salida = ejecutar()

        assert codigo == 1
        assert "Cuenta de Juan" in salida

    def test_corrige_la_propia_sin_tocar_la_ajena(self, session, ejecutar, ana, cuenta, cuenta_ajena):
        corromper(session, cuenta)
        corromper(session, cuenta_ajena, "1.00")

        ejecutar("--user", str(ana), "--fix")

        assert recargar(session, Account, cuenta.id).balance == Decimal("2485000.00")
        assert recargar(session, Account, cuenta_ajena.id).balance == Decimal("1.00")

    def test_un_user_mal_formado_es_un_error_de_uso(self, ejecutar, cuenta):
        """Equivale al `CommandError` del email inexistente: sale distinto de 0."""
        codigo, salida = ejecutar("--user", "fantasma@finty.co")

        assert codigo == 2
        assert "fantasma@finty.co" in salida

    def test_un_usuario_sin_cuentas_audita_cero(self, ejecutar, cuenta):
        """Sin acceso a `finty_identity`, un UUID desconocido no es un error."""
        codigo, salida = ejecutar("--user", str(uuid4()))

        assert codigo == 0
        assert "Cuentas auditadas          : 0" in salida

    def test_acepta_el_uuid_en_mayusculas(self, ejecutar, ana, cuenta):
        codigo, salida = ejecutar("--user", str(ana).upper())

        assert codigo == 0
        assert str(ana) in salida


class TestComandoSobreBaseVacia:
    def test_sale_con_cero(self, ejecutar):
        codigo, salida = ejecutar()

        assert codigo == 0
        assert "Cuentas auditadas          : 0" in salida
