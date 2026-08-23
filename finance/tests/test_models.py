"""Tests de la capa de persistencia de `finance`.

**Estos tests se saltan el dominio a proposito.** Usan `Model.objects.create()`
directo, sin builders ni services, porque lo que verifican es que la base de
datos defiende aunque alguien evada la capa de servicios: el shell de Django, una
migracion de datos o un proceso batch. Es la mitad "red de seguridad" de la
defensa en profundidad; la mitad autoritativa vive en `finance/domain/` y ya esta
cubierta por `test_transaction_rules.py`.

Cada asercion de `IntegrityError` va dentro de su propio bloque atomico: un
`IntegrityError` deja la transaccion de PostgreSQL abortada y toda consulta
posterior fallaria con `InFailedSqlTransaction`, contaminando el resto del test.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.db import DataError, IntegrityError
from django.db import transaction as db_transaction
from django.db.models import ProtectedError

from finance.models import Account, Category, Transaction
from identity.models import User

pytestmark = pytest.mark.django_db

TODAY = date(2026, 8, 23)


@pytest.fixture
def user():
    """Usuario dueno de las cuentas de prueba."""
    return User.objects.create_user(email="ana@finty.co", password="Contrasena-Segura-2026")


@pytest.fixture
def other_user():
    """Segundo usuario, para verificar aislamiento entre propietarios."""
    return User.objects.create_user(email="juan@finty.co", password="Contrasena-Segura-2026")


@pytest.fixture
def account(user):
    """Cuenta de efectivo en pesos."""
    return Account.objects.create(user=user, name="Efectivo", type="cash")


@pytest.fixture
def category():
    """Categoria de gasto tomada del catalogo sembrado."""
    return Category.objects.get(name="Alimentación")


def make_transaction(account, **overrides):
    """Crea una transaccion valida, permitiendo sobreescribir campos."""
    campos = {
        "account": account,
        "amount": Decimal("50.00"),
        "type": "expense",
        "occurred_on": TODAY,
    }
    campos.update(overrides)
    return Transaction.objects.create(**campos)


class TestCatalogoDeCategorias:
    """La migracion de datos dejo el catalogo sembrado."""

    GASTOS = [
        "Alimentación",
        "Transporte",
        "Vivienda",
        "Servicios públicos",
        "Salud",
        "Educación",
        "Entretenimiento",
        "Compras",
        "Deudas y créditos",
        "Otros gastos",
    ]
    INGRESOS = [
        "Salario",
        "Freelance",
        "Inversiones",
        "Reembolsos",
        "Otros ingresos",
    ]

    def test_existen_quince_categorias(self):
        assert Category.objects.count() == 15

    @pytest.mark.parametrize("name", GASTOS)
    def test_categorias_de_gasto(self, name):
        assert Category.objects.get(name=name).applies_to == "expense"

    @pytest.mark.parametrize("name", INGRESOS)
    def test_categorias_de_ingreso(self, name):
        assert Category.objects.get(name=name).applies_to == "income"

    def test_las_categorias_de_respaldo_existen(self):
        """Contrato con M4: `RuleBasedCategorizer` cae en estas dos."""
        assert Category.objects.filter(name="Otros gastos").exists()
        assert Category.objects.filter(name="Otros ingresos").exists()

    def test_reparto_entre_gastos_e_ingresos(self):
        assert Category.objects.filter(applies_to="expense").count() == 10
        assert Category.objects.filter(applies_to="income").count() == 5

    def test_nombre_duplicado_lanza_integrity_error(self):
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                Category.objects.create(name="Alimentación", applies_to="expense")

    def test_applies_to_invalido_lanza_integrity_error(self):
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                Category.objects.create(name="Inventada", applies_to="transfer")

    def test_ordering_por_applies_to_y_nombre(self):
        nombres = list(Category.objects.values_list("applies_to", "name"))
        assert nombres == sorted(nombres)


class TestAccountDefaults:
    """Valores por defecto de `Account`."""

    def test_balance_arranca_en_cero_decimal(self, account):
        assert account.balance == Decimal("0.00")
        assert isinstance(account.balance, Decimal)

    def test_moneda_por_defecto_es_cop(self, account):
        assert account.currency == "COP"

    def test_no_arranca_archivada(self, account):
        assert account.is_archived is False

    def test_el_id_es_uuid(self, account):
        from uuid import UUID

        assert isinstance(account.id, UUID)

    def test_related_name_accounts(self, user, account):
        assert list(user.accounts.all()) == [account]


class TestAccountConstraints:
    """Constraints de `Account`."""

    def test_tipo_invalido_lanza_integrity_error(self, user):
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                Account.objects.create(user=user, name="Rara", type="crypto")

    @pytest.mark.parametrize("account_type", ["cash", "bank", "credit"])
    def test_los_tres_tipos_validos_se_persisten(self, user, account_type):
        cuenta = Account.objects.create(
            user=user, name=f"Cuenta {account_type}", type=account_type
        )
        assert cuenta.type == account_type

    @pytest.mark.parametrize("currency", ["CO", "C", ""])
    def test_moneda_mas_corta_lanza_integrity_error(self, user, currency):
        """La rechaza el `CheckConstraint` de longitud."""
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                Account.objects.create(
                    user=user, name="Rara", type="cash", currency=currency
                )

    @pytest.mark.parametrize("currency", ["COPS", "DOLARES"])
    def test_moneda_mas_larga_lanza_data_error(self, user, currency):
        """La rechaza el ancho de la columna antes de llegar al CHECK.

        `varchar(3)` no admite cuatro caracteres, asi que PostgreSQL corta en
        `DataError` y la constraint nunca llega a evaluarse. Sigue siendo la base
        defendiendo, pero por otra via: por eso no es un `IntegrityError`.
        """
        with pytest.raises(DataError):
            with db_transaction.atomic():
                Account.objects.create(
                    user=user, name="Rara", type="cash", currency=currency
                )

    def test_moneda_de_tres_caracteres_es_valida(self, user):
        cuenta = Account.objects.create(
            user=user, name="En dolares", type="bank", currency="USD"
        )
        assert cuenta.currency == "USD"

    def test_nombre_duplicado_para_el_mismo_usuario_lanza_integrity_error(
        self, user, account
    ):
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                Account.objects.create(user=user, name="Efectivo", type="bank")

    def test_el_mismo_nombre_para_usuarios_distintos_es_valido(
        self, user, other_user, account
    ):
        ajena = Account.objects.create(user=other_user, name="Efectivo", type="cash")

        assert ajena.pk != account.pk
        assert Account.objects.filter(name="Efectivo").count() == 2

    def test_balance_negativo_se_persiste(self, user):
        """La base no juzga el signo: INV-14 es una regla de dominio."""
        cuenta = Account.objects.create(
            user=user, name="Tarjeta", type="credit", balance=Decimal("-500.00")
        )
        assert cuenta.balance == Decimal("-500.00")


class TestTransactionConstraints:
    """Constraints de `Transaction`: INV-04 e INV-09 en capa de base de datos."""

    def test_monto_cero_lanza_integrity_error(self, account):
        """INV-04, red de seguridad."""
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                make_transaction(account, amount=Decimal("0.00"))

    def test_monto_positivo_es_valido(self, account):
        assert make_transaction(account, amount=Decimal("0.01")).amount == Decimal("0.01")

    def test_tipo_invalido_lanza_integrity_error(self, account):
        """INV-09, red de seguridad."""
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                make_transaction(account, type="transfer")

    @pytest.mark.parametrize("transaction_type", ["income", "expense"])
    def test_los_dos_tipos_validos_se_persisten(self, account, transaction_type):
        assert make_transaction(account, type=transaction_type).type == transaction_type

    @pytest.mark.parametrize("confidence", [1.5, -0.1, 2.0, -1.0])
    def test_confianza_fuera_de_rango_lanza_integrity_error(self, account, confidence):
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                make_transaction(account, categorization_confidence=confidence)

    @pytest.mark.parametrize("confidence", [None, 0.0, 1.0, 0.5])
    def test_confianza_valida_se_persiste(self, account, confidence):
        creada = make_transaction(account, categorization_confidence=confidence)
        assert creada.categorization_confidence == confidence

    def test_la_cuenta_es_obligatoria(self, account):
        """INV-02: no hay transaccion sin cuenta."""
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                Transaction.objects.create(
                    account=None,
                    amount=Decimal("10.00"),
                    type="expense",
                    occurred_on=TODAY,
                )

    def test_la_categoria_es_opcional(self, account):
        assert make_transaction(account).category is None

    def test_una_fecha_futura_se_persiste(self, account):
        """INV-12 no tiene constraint: PostgreSQL rechaza CURRENT_DATE en un CHECK.

        La base acepta la fila; quien la rechaza es
        `TransactionRules.ensure_date_not_future`, en el dominio.
        """
        futura = make_transaction(account, occurred_on=date.today() + timedelta(days=30))
        assert futura.occurred_on > date.today()


class TestTiposDePersistencia:
    """El dinero viaja como `Decimal` en los dos sentidos."""

    def test_el_monto_se_persiste_como_decimal(self, account):
        make_transaction(account, amount=Decimal("1234.56"))

        recuperada = Transaction.objects.get(account=account)

        assert isinstance(recuperada.amount, Decimal)
        assert not isinstance(recuperada.amount, float)
        assert recuperada.amount == Decimal("1234.56")

    def test_el_balance_se_recupera_como_decimal(self, user):
        Account.objects.create(
            user=user, name="Ahorros", type="bank", balance=Decimal("999999.99")
        )

        recuperada = Account.objects.get(name="Ahorros")

        assert isinstance(recuperada.balance, Decimal)
        assert recuperada.balance == Decimal("999999.99")

    def test_la_confianza_si_es_float(self, account):
        """`categorization_confidence` es una medida estadistica, no dinero."""
        make_transaction(account, categorization_confidence=0.85)

        assert isinstance(
            Transaction.objects.get(account=account).categorization_confidence, float
        )


class TestIntegridadReferencial:
    """`PROTECT` en las tres relaciones."""

    def test_borrar_una_cuenta_con_transacciones_lanza_protected_error(self, account):
        """INV-13."""
        make_transaction(account)

        with pytest.raises(ProtectedError):
            with db_transaction.atomic():
                account.delete()

    def test_una_cuenta_sin_transacciones_si_se_borra(self, account):
        account.delete()
        assert not Account.objects.filter(pk=account.pk).exists()

    def test_borrar_una_categoria_en_uso_lanza_protected_error(self, account, category):
        make_transaction(account, category=category)

        with pytest.raises(ProtectedError):
            with db_transaction.atomic():
                category.delete()

    def test_borrar_un_usuario_con_cuentas_lanza_protected_error(self, user, account):
        with pytest.raises(ProtectedError):
            with db_transaction.atomic():
                user.delete()

    def test_borrar_una_transaccion_no_afecta_a_la_cuenta(self, account):
        movimiento = make_transaction(account)

        movimiento.delete()

        assert Account.objects.filter(pk=account.pk).exists()


class TestOrdering:
    """`Meta.ordering` de `Transaction`."""

    def test_devuelve_primero_la_mas_reciente(self, account):
        antigua = make_transaction(account, occurred_on=date(2026, 1, 1))
        reciente = make_transaction(account, occurred_on=date(2026, 8, 1))
        intermedia = make_transaction(account, occurred_on=date(2026, 5, 1))

        assert list(Transaction.objects.all()) == [reciente, intermedia, antigua]

    def test_desempata_por_created_at_descendente(self, account):
        """A igual `occurred_on`, primero la creada mas tarde.

        `created_at` se fija por `update()` en lugar de confiar en dos llamadas
        seguidas a `objects.create()`: la resolucion del reloj de Windows es de
        unos 15 ms y ambas filas podrian caer en el mismo instante, dejando el
        desempate sin nada que ordenar.
        """
        primera = make_transaction(account, occurred_on=TODAY)
        segunda = make_transaction(account, occurred_on=TODAY)

        Transaction.objects.filter(pk=primera.pk).update(
            created_at=datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
        )
        Transaction.objects.filter(pk=segunda.pk).update(
            created_at=datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
        )

        assert [t.pk for t in Transaction.objects.all()] == [segunda.pk, primera.pk]

    def test_ordering_de_account_por_nombre(self, user):
        Account.objects.create(user=user, name="Zeta", type="cash")
        Account.objects.create(user=user, name="Alfa", type="bank")

        assert [a.name for a in Account.objects.all()] == ["Alfa", "Zeta"]


class TestModelosAnemicos:
    """ADR-03: los modelos no tienen metodos de negocio."""

    @pytest.mark.parametrize("model", [Account, Transaction, Category])
    def test_no_sobreescriben_save_clean_ni_delete(self, model):
        for metodo in ("save", "clean", "delete"):
            assert metodo not in model.__dict__, (
                f"{model.__name__}.{metodo}() esta sobreescrito; ADR-03 lo prohibe"
            )

    @pytest.mark.parametrize("model", [Account, Transaction, Category])
    def test_no_declaran_properties_calculadas(self, model):
        propiedades = [
            nombre
            for nombre, valor in model.__dict__.items()
            if isinstance(valor, property)
        ]
        assert propiedades == []

    def test_str_de_cada_modelo(self, account, category):
        movimiento = make_transaction(account)

        assert str(account) == "Efectivo"
        assert str(category) == "Alimentación"
        assert str(movimiento) == f"expense 50.00 {TODAY}"
