"""Tests de `TransactionBuilder` y `AccountBuilder`.

Dominio puro: ningun test lleva la marca `django_db`, asi que pytest-django
bloquea el acceso a base de datos. Corren sin PostgreSQL levantado.
"""
from datetime import date, timedelta
from uuid import uuid4

import pytest

from core.domain.exceptions import CurrencyMismatchError, ValidationError
from core.domain.value_objects import Money
from finance.domain.builders import AccountBuilder, TransactionBuilder
from finance.domain.exceptions import (
    ArchivedAccountError,
    FutureTransactionDateError,
    InvalidTransactionTypeError,
    NegativeAmountError,
    NegativeBalanceNotAllowedError,
    ZeroAmountError,
)
from finance.domain.interfaces import Categorizer
from finance.domain.value_objects import (
    AccountSnapshot,
    AccountType,
    CategorizationSource,
    CategorySuggestion,
    TransactionDraft,
    TransactionType,
)

TODAY = date(2026, 8, 23)
TOMORROW = TODAY + timedelta(days=1)


class CountingCategorizer(Categorizer):
    """Doble que cuenta cuantas veces se le invoca."""

    def __init__(self, category_name="Alimentación", confidence=0.75):
        self.calls = 0
        self.last_arguments = None
        self._category_name = category_name
        self._confidence = confidence

    def categorize(self, description, amount, transaction_type):
        self.calls += 1
        self.last_arguments = (description, amount, transaction_type)
        return CategorySuggestion(
            self._category_name, self._confidence, CategorizationSource.AI
        )


@pytest.fixture
def snapshot():
    """Cuenta de efectivo activa en pesos, con saldo."""
    return AccountSnapshot(
        account_id=uuid4(),
        currency="COP",
        account_type=AccountType.CASH,
        is_archived=False,
        balance=Money("100000", "COP"),
    )


def base_builder(snapshot):
    """Builder con los cuatro campos obligatorios ya puestos."""
    return (
        TransactionBuilder()
        .for_account(snapshot)
        .with_amount(Money("25000", "COP"))
        .of_type(TransactionType.EXPENSE)
        .occurred_on(TODAY)
        .as_of(TODAY)
    )


class TestAccountSnapshot:
    """El value object que transporta la cuenta hacia el dominio."""

    def test_normaliza_el_tipo_de_cuenta(self):
        snap = AccountSnapshot(uuid4(), "COP", "credit", False, Money.zero("COP"))
        assert snap.account_type is AccountType.CREDIT

    def test_normaliza_la_moneda(self):
        snap = AccountSnapshot(uuid4(), "cop", AccountType.CASH, False, Money.zero("COP"))
        assert snap.currency == "COP"

    def test_exige_coherencia_entre_moneda_y_balance(self):
        with pytest.raises(CurrencyMismatchError):
            AccountSnapshot(uuid4(), "COP", AccountType.CASH, False, Money.zero("USD"))

    def test_rechaza_un_balance_que_no_es_money(self):
        with pytest.raises(ValidationError):
            AccountSnapshot(uuid4(), "COP", AccountType.CASH, False, 100)

    def test_es_inmutable(self, snapshot):
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            snapshot.is_archived = True


class TestCaminoFeliz:
    """`TransactionBuilder` produce un draft completo."""

    def test_todos_los_campos_del_draft(self, snapshot):
        draft = base_builder(snapshot).described_as("Almuerzo").build()

        assert isinstance(draft, TransactionDraft)
        assert draft.account_id == snapshot.account_id
        assert draft.amount == Money("25000", "COP")
        assert draft.transaction_type is TransactionType.EXPENSE
        assert draft.occurred_on == TODAY
        assert draft.description == "Almuerzo"

    def test_la_descripcion_se_recorta(self, snapshot):
        draft = base_builder(snapshot).described_as("  Almuerzo  ").build()
        assert draft.description == "Almuerzo"

    def test_la_descripcion_es_opcional(self, snapshot):
        assert base_builder(snapshot).build().description == ""

    def test_descripcion_none_queda_vacia(self, snapshot):
        assert base_builder(snapshot).described_as(None).build().description == ""

    def test_acepta_el_tipo_como_cadena(self, snapshot):
        draft = (
            TransactionBuilder()
            .for_account(snapshot)
            .with_amount(Money("100", "COP"))
            .of_type("EXPENSE")
            .occurred_on(TODAY)
            .as_of(TODAY)
            .build()
        )
        assert draft.transaction_type is TransactionType.EXPENSE

    def test_el_signo_lo_aporta_el_tipo(self, snapshot):
        draft = base_builder(snapshot).build()
        assert draft.signed_amount() == Money("-25000", "COP")


class TestCamposObligatorios:
    """Falta cada campo obligatorio, uno por test."""

    def test_falta_la_cuenta(self, snapshot):
        builder = (
            TransactionBuilder()
            .with_amount(Money("100", "COP"))
            .of_type(TransactionType.EXPENSE)
            .occurred_on(TODAY)
        )
        with pytest.raises(ValidationError):
            builder.build()

    def test_falta_el_monto(self, snapshot):
        builder = (
            TransactionBuilder()
            .for_account(snapshot)
            .of_type(TransactionType.EXPENSE)
            .occurred_on(TODAY)
        )
        with pytest.raises(ValidationError):
            builder.build()

    def test_falta_el_tipo(self, snapshot):
        builder = (
            TransactionBuilder()
            .for_account(snapshot)
            .with_amount(Money("100", "COP"))
            .occurred_on(TODAY)
        )
        with pytest.raises(ValidationError):
            builder.build()

    def test_falta_la_fecha(self, snapshot):
        builder = (
            TransactionBuilder()
            .for_account(snapshot)
            .with_amount(Money("100", "COP"))
            .of_type(TransactionType.EXPENSE)
        )
        with pytest.raises(ValidationError):
            builder.build()

    def test_un_builder_vacio_falla(self):
        with pytest.raises(ValidationError):
            TransactionBuilder().build()


class TestValidacionTemprana:
    """Cada metodo fluido valida su propio argumento de inmediato."""

    def test_for_account_rechaza_lo_que_no_es_snapshot(self):
        with pytest.raises(ValidationError):
            TransactionBuilder().for_account({"id": 1})

    def test_with_amount_rechaza_un_numero_suelto(self):
        with pytest.raises(ValidationError):
            TransactionBuilder().with_amount(25000)

    def test_of_type_rechaza_un_tipo_invalido(self):
        with pytest.raises(InvalidTransactionTypeError):
            TransactionBuilder().of_type("transfer")

    def test_occurred_on_rechaza_lo_que_no_es_fecha(self):
        with pytest.raises(ValidationError):
            TransactionBuilder().occurred_on("2026-08-23")

    def test_described_as_rechaza_lo_que_no_es_texto(self):
        with pytest.raises(ValidationError):
            TransactionBuilder().described_as(42)

    def test_categorized_by_rechaza_lo_que_no_es_categorizer(self):
        with pytest.raises(ValidationError):
            TransactionBuilder().categorized_by(object())

    def test_as_of_rechaza_lo_que_no_es_fecha(self):
        with pytest.raises(ValidationError):
            TransactionBuilder().as_of("hoy")


class TestInvariantes:
    """`build()` delega en `TransactionRules`."""

    def test_monto_cero(self, snapshot):
        builder = base_builder(snapshot).with_amount(Money.zero("COP"))
        with pytest.raises(ZeroAmountError):
            builder.build()

    def test_monto_negativo(self, snapshot):
        builder = base_builder(snapshot).with_amount(Money("-25000", "COP"))
        with pytest.raises(NegativeAmountError):
            builder.build()

    def test_moneda_distinta_a_la_de_la_cuenta(self, snapshot):
        builder = base_builder(snapshot).with_amount(Money("25000", "USD"))
        with pytest.raises(CurrencyMismatchError):
            builder.build()

    def test_fecha_futura(self, snapshot):
        builder = base_builder(snapshot).occurred_on(TOMORROW)
        with pytest.raises(FutureTransactionDateError):
            builder.build()

    def test_la_fecha_de_hoy_es_valida(self, snapshot):
        assert base_builder(snapshot).occurred_on(TODAY).build().occurred_on == TODAY

    def test_una_fecha_pasada_es_valida(self, snapshot):
        ayer = TODAY - timedelta(days=1)
        assert base_builder(snapshot).occurred_on(ayer).build().occurred_on == ayer

    def test_cuenta_archivada(self):
        archivada = AccountSnapshot(
            uuid4(), "COP", AccountType.CASH, True, Money("100", "COP")
        )
        with pytest.raises(ArchivedAccountError):
            base_builder(archivada).build()

    def test_no_verifica_inv_14(self):
        """El saldo resultante negativo no es asunto del builder.

        Depende del balance autoritativo bajo bloqueo, que el builder no puede
        conocer. Lo verifica el Service en M5.
        """
        efectivo = AccountSnapshot(
            uuid4(), "COP", AccountType.CASH, False, Money("100", "COP")
        )
        draft = (
            TransactionBuilder()
            .for_account(efectivo)
            .with_amount(Money("999999", "COP"))
            .of_type(TransactionType.EXPENSE)
            .occurred_on(TODAY)
            .as_of(TODAY)
            .build()
        )
        assert draft.amount == Money("999999", "COP")


class TestCategorizacion:
    """Los tres modos: automatica, manual y ninguna."""

    def test_categorized_by_llena_los_tres_campos(self, snapshot):
        categorizer = CountingCategorizer("Transporte", 0.9)

        draft = base_builder(snapshot).categorized_by(categorizer).build()

        assert draft.category_name == "Transporte"
        assert draft.categorization_source is CategorizationSource.AI
        assert draft.confidence == 0.9

    def test_el_categorizador_recibe_los_datos_de_la_transaccion(self, snapshot):
        categorizer = CountingCategorizer()

        base_builder(snapshot).described_as("Taxi").categorized_by(categorizer).build()

        descripcion, monto, tipo = categorizer.last_arguments
        assert descripcion == "Taxi"
        assert monto == Money("25000", "COP")
        assert tipo is TransactionType.EXPENSE

    def test_el_categorizador_se_invoca_exactamente_una_vez(self, snapshot):
        categorizer = CountingCategorizer()

        base_builder(snapshot).categorized_by(categorizer).build()

        assert categorizer.calls == 1

    def test_el_categorizador_no_se_invoca_en_el_metodo_fluido(self, snapshot):
        categorizer = CountingCategorizer()

        base_builder(snapshot).categorized_by(categorizer)

        assert categorizer.calls == 0

    def test_el_categorizador_no_se_invoca_si_una_invariante_falla(self, snapshot):
        """No se gasta una llamada externa en una transaccion invalida."""
        categorizer = CountingCategorizer()
        builder = (
            base_builder(snapshot)
            .with_amount(Money.zero("COP"))
            .categorized_by(categorizer)
        )

        with pytest.raises(ZeroAmountError):
            builder.build()

        assert categorizer.calls == 0

    def test_with_manual_category(self, snapshot):
        draft = base_builder(snapshot).with_manual_category("Compras").build()

        assert draft.category_name == "Compras"
        assert draft.categorization_source is CategorizationSource.MANUAL
        assert draft.confidence == 1.0

    def test_la_categoria_manual_se_recorta(self, snapshot):
        draft = base_builder(snapshot).with_manual_category("  Compras  ").build()
        assert draft.category_name == "Compras"

    @pytest.mark.parametrize("name", ["", "   ", None, 42])
    def test_categoria_manual_vacia_o_invalida(self, snapshot, name):
        with pytest.raises(ValidationError):
            TransactionBuilder().with_manual_category(name)

    def test_sin_categorizacion_los_tres_campos_quedan_none(self, snapshot):
        """INV-08 solo exige categoria despues del procesamiento."""
        draft = base_builder(snapshot).build()

        assert draft.category_name is None
        assert draft.categorization_source is None
        assert draft.confidence is None

    def test_automatica_y_manual_juntas_en_ese_orden(self, snapshot):
        builder = base_builder(snapshot).categorized_by(CountingCategorizer())

        with pytest.raises(ValidationError):
            builder.with_manual_category("Compras")

    def test_manual_y_automatica_juntas_en_el_orden_inverso(self, snapshot):
        builder = base_builder(snapshot).with_manual_category("Compras")

        with pytest.raises(ValidationError):
            builder.categorized_by(CountingCategorizer())


class TestUnSoloUso:
    """`build()` no se puede llamar dos veces."""

    def test_la_segunda_llamada_falla(self, snapshot):
        builder = base_builder(snapshot)
        builder.build()

        with pytest.raises(ValidationError):
            builder.build()

    def test_la_segunda_llamada_no_reinvoca_al_categorizador(self, snapshot):
        categorizer = CountingCategorizer()
        builder = base_builder(snapshot).categorized_by(categorizer)
        builder.build()

        with pytest.raises(ValidationError):
            builder.build()

        assert categorizer.calls == 1

    def test_un_builder_nuevo_si_construye(self, snapshot):
        base_builder(snapshot).build()

        assert base_builder(snapshot).build() is not None


class TestInterfazFluida:
    """Los metodos devuelven `self` y el orden no importa."""

    def test_cada_metodo_devuelve_el_builder(self, snapshot):
        builder = TransactionBuilder()

        assert builder.for_account(snapshot) is builder
        assert builder.with_amount(Money("1", "COP")) is builder
        assert builder.of_type(TransactionType.INCOME) is builder
        assert builder.occurred_on(TODAY) is builder
        assert builder.described_as("x") is builder
        assert builder.as_of(TODAY) is builder
        assert builder.with_manual_category("Salario") is builder

    def test_el_orden_de_los_pasos_no_altera_el_resultado(self, snapshot):
        directo = (
            TransactionBuilder()
            .for_account(snapshot)
            .with_amount(Money("100", "COP"))
            .of_type(TransactionType.EXPENSE)
            .occurred_on(TODAY)
            .described_as("Cafe")
            .as_of(TODAY)
            .build()
        )
        invertido = (
            TransactionBuilder()
            .as_of(TODAY)
            .described_as("Cafe")
            .occurred_on(TODAY)
            .of_type(TransactionType.EXPENSE)
            .with_amount(Money("100", "COP"))
            .for_account(snapshot)
            .build()
        )

        assert directo == invertido

    def test_el_ultimo_valor_gana(self, snapshot):
        draft = base_builder(snapshot).with_amount(Money("999", "COP")).build()
        assert draft.amount == Money("999", "COP")


class TestAccountBuilder:
    """`AccountBuilder`."""

    def test_camino_feliz(self):
        user_id = uuid4()

        draft = (
            AccountBuilder()
            .for_user(user_id)
            .named("Cuenta de ahorros")
            .of_type(AccountType.BANK)
            .with_initial_balance(Money("1000000", "COP"))
            .build()
        )

        assert draft.user_id == user_id
        assert draft.name == "Cuenta de ahorros"
        assert draft.account_type is AccountType.BANK
        assert draft.initial_balance == Money("1000000", "COP")

    def test_sin_balance_inicial_arranca_en_cero(self):
        draft = (
            AccountBuilder()
            .for_user(uuid4())
            .named("Efectivo")
            .of_type("cash")
            .in_currency("COP")
            .build()
        )
        assert draft.initial_balance == Money.zero("COP")

    def test_la_moneda_se_deduce_del_balance_inicial(self):
        draft = (
            AccountBuilder()
            .for_user(uuid4())
            .named("En dolares")
            .of_type("bank")
            .with_initial_balance(Money("500", "USD"))
            .build()
        )
        assert draft.initial_balance.currency == "USD"

    def test_moneda_y_balance_incoherentes(self):
        builder = (
            AccountBuilder()
            .for_user(uuid4())
            .named("Rara")
            .of_type("bank")
            .in_currency("USD")
            .with_initial_balance(Money("500", "COP"))
        )
        with pytest.raises(CurrencyMismatchError):
            builder.build()

    def test_sin_moneda_ni_balance(self):
        builder = AccountBuilder().for_user(uuid4()).named("Rara").of_type("cash")
        with pytest.raises(ValidationError):
            builder.build()

    def test_el_nombre_se_recorta(self):
        draft = (
            AccountBuilder()
            .for_user(uuid4())
            .named("  Ahorros  ")
            .of_type("bank")
            .in_currency("COP")
            .build()
        )
        assert draft.name == "Ahorros"

    @pytest.mark.parametrize("name", ["", "   ", "\t\n"])
    def test_nombre_vacio_o_solo_espacios(self, name):
        builder = (
            AccountBuilder().for_user(uuid4()).named(name).of_type("cash").in_currency("COP")
        )
        with pytest.raises(ValidationError):
            builder.build()

    def test_nombre_demasiado_largo(self):
        builder = (
            AccountBuilder()
            .for_user(uuid4())
            .named("x" * 121)
            .of_type("cash")
            .in_currency("COP")
        )
        with pytest.raises(ValidationError):
            builder.build()

    def test_nombre_en_el_limite_exacto(self):
        draft = (
            AccountBuilder()
            .for_user(uuid4())
            .named("x" * 120)
            .of_type("cash")
            .in_currency("COP")
            .build()
        )
        assert len(draft.name) == 120

    @pytest.mark.parametrize("campo", ["user", "name", "type"])
    def test_campos_obligatorios(self, campo):
        builder = AccountBuilder().in_currency("COP")
        if campo != "user":
            builder.for_user(uuid4())
        if campo != "name":
            builder.named("Cuenta")
        if campo != "type":
            builder.of_type("cash")

        with pytest.raises(ValidationError):
            builder.build()

    def test_moneda_invalida(self):
        with pytest.raises(ValidationError):
            AccountBuilder().in_currency("PESO")

    @pytest.mark.parametrize("account_type", [AccountType.CASH, AccountType.BANK])
    def test_saldo_inicial_negativo_rechazado(self, account_type):
        """INV-14 si aplica en la creacion: no hay carrera con la base."""
        builder = (
            AccountBuilder()
            .for_user(uuid4())
            .named("Cuenta")
            .of_type(account_type)
            .with_initial_balance(Money("-1", "COP"))
        )
        with pytest.raises(NegativeBalanceNotAllowedError):
            builder.build()

    def test_saldo_inicial_negativo_aceptado_en_credito(self):
        draft = (
            AccountBuilder()
            .for_user(uuid4())
            .named("Tarjeta")
            .of_type(AccountType.CREDIT)
            .with_initial_balance(Money("-500000", "COP"))
            .build()
        )
        assert draft.initial_balance == Money("-500000", "COP")

    def test_es_reutilizable(self):
        """A diferencia de `TransactionBuilder`: no invoca colaboradores."""
        builder = (
            AccountBuilder().for_user(uuid4()).named("Efectivo").of_type("cash").in_currency("COP")
        )

        assert builder.build() == builder.build()

    def test_cada_metodo_devuelve_el_builder(self):
        builder = AccountBuilder()

        assert builder.for_user(uuid4()) is builder
        assert builder.named("x") is builder
        assert builder.of_type("cash") is builder
        assert builder.with_initial_balance(Money.zero("COP")) is builder
        assert builder.in_currency("COP") is builder
