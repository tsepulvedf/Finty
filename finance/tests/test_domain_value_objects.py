"""Tests de los value objects del dominio financiero.

Dominio puro: ningun test lleva la marca `django_db`, asi que pytest-django
bloquea cualquier acceso a base de datos. Corren sin PostgreSQL levantado.
"""
from dataclasses import FrozenInstanceError
from datetime import date
from uuid import uuid4

import pytest

from core.domain.exceptions import ValidationError
from core.domain.value_objects import Money
from finance.domain.exceptions import InvalidTransactionTypeError
from finance.domain.value_objects import (
    AccountDraft,
    AccountType,
    CategorizationSource,
    CategorySuggestion,
    TransactionDraft,
    TransactionType,
)

TODAY = date(2026, 8, 23)


class TestAccountType:
    """`AccountType`: conjunto cerrado de tipos de cuenta."""

    def test_valores_del_enum(self):
        assert AccountType.CASH.value == "cash"
        assert AccountType.BANK.value == "bank"
        assert AccountType.CREDIT.value == "credit"

    def test_solo_existen_tres_tipos(self):
        assert len(list(AccountType)) == 3

    @pytest.mark.parametrize("raw", ["cash", "CASH", "Cash", "  cash  ", "cAsH"])
    def test_from_value_acepta_variantes_de_mayusculas(self, raw):
        assert AccountType.from_value(raw) is AccountType.CASH

    def test_from_value_acepta_el_propio_miembro(self):
        assert AccountType.from_value(AccountType.BANK) is AccountType.BANK

    @pytest.mark.parametrize("raw", ["wallet", "", "savings", "efectivo"])
    def test_from_value_rechaza_valores_invalidos(self, raw):
        with pytest.raises(ValidationError):
            AccountType.from_value(raw)

    def test_from_value_rechaza_lo_que_no_es_cadena(self):
        with pytest.raises(ValidationError):
            AccountType.from_value(3)

    def test_solo_credit_admite_saldo_negativo(self):
        assert AccountType.CREDIT.allows_negative_balance() is True
        assert AccountType.CASH.allows_negative_balance() is False
        assert AccountType.BANK.allows_negative_balance() is False

    def test_igualdad_por_valor(self):
        assert AccountType.CASH == "cash"
        assert AccountType.from_value("cash") is AccountType.CASH


class TestTransactionType:
    """`TransactionType`: sentido del movimiento (INV-09)."""

    def test_valores_del_enum(self):
        assert TransactionType.INCOME.value == "income"
        assert TransactionType.EXPENSE.value == "expense"

    def test_solo_existen_dos_tipos(self):
        assert len(list(TransactionType)) == 2

    @pytest.mark.parametrize("raw", ["income", "INCOME", " Income "])
    def test_from_value_acepta_variantes_de_mayusculas(self, raw):
        assert TransactionType.from_value(raw) is TransactionType.INCOME

    def test_from_value_acepta_el_propio_miembro(self):
        assert TransactionType.from_value(TransactionType.EXPENSE) is TransactionType.EXPENSE

    @pytest.mark.parametrize("raw", ["transfer", "", "gasto", "in"])
    def test_from_value_invalido_lanza_invalid_transaction_type(self, raw):
        with pytest.raises(InvalidTransactionTypeError):
            TransactionType.from_value(raw)

    def test_from_value_rechaza_lo_que_no_es_cadena(self):
        with pytest.raises(InvalidTransactionTypeError):
            TransactionType.from_value(1)

    def test_invalid_transaction_type_es_una_validacion(self):
        assert issubclass(InvalidTransactionTypeError, ValidationError)

    def test_sign_de_ingreso_es_positivo(self):
        assert TransactionType.INCOME.sign() == 1

    def test_sign_de_gasto_es_negativo(self):
        assert TransactionType.EXPENSE.sign() == -1


class TestCategorizationSource:
    """`CategorizationSource`: origen de la categoria asignada."""

    def test_valores_del_enum(self):
        assert CategorizationSource.AI.value == "ai"
        assert CategorizationSource.RULE.value == "rule"
        assert CategorizationSource.MANUAL.value == "manual"

    def test_solo_existen_tres_origenes(self):
        assert len(list(CategorizationSource)) == 3


class TestCategorySuggestion:
    """`CategorySuggestion`: contrato de retorno de `Categorizer`."""

    def test_construccion_valida(self):
        suggestion = CategorySuggestion("Comida", 0.8, CategorizationSource.RULE)

        assert suggestion.category_name == "Comida"
        assert suggestion.confidence == 0.8
        assert suggestion.source is CategorizationSource.RULE

    def test_normaliza_el_nombre_con_strip(self):
        assert CategorySuggestion("  Comida  ", 0.8, CategorizationSource.AI).category_name == "Comida"

    @pytest.mark.parametrize("name", ["", "   ", "\t\n"])
    def test_rechaza_nombre_vacio(self, name):
        with pytest.raises(ValidationError):
            CategorySuggestion(name, 0.8, CategorizationSource.AI)

    def test_rechaza_nombre_que_no_es_cadena(self):
        with pytest.raises(ValidationError):
            CategorySuggestion(None, 0.8, CategorizationSource.AI)

    @pytest.mark.parametrize("confidence", [-0.1, 1.1, 2.0, -1.0])
    def test_rechaza_confianza_fuera_de_rango(self, confidence):
        with pytest.raises(ValidationError):
            CategorySuggestion("Comida", confidence, CategorizationSource.AI)

    @pytest.mark.parametrize("confidence", [0.0, 1.0])
    def test_acepta_los_extremos_del_rango(self, confidence):
        assert CategorySuggestion("Comida", confidence, CategorizationSource.AI).confidence == confidence

    def test_rechaza_confianza_no_numerica(self):
        with pytest.raises(ValidationError):
            CategorySuggestion("Comida", "alta", CategorizationSource.AI)

    def test_is_confident_por_encima_del_umbral(self):
        assert CategorySuggestion("Comida", 0.9, CategorizationSource.AI).is_confident()

    def test_is_confident_por_debajo_del_umbral(self):
        assert not CategorySuggestion("Comida", 0.3, CategorizationSource.AI).is_confident()

    def test_is_confident_en_el_umbral_exacto_es_verdadero(self):
        """El umbral es inclusive: 0.5 con umbral 0.5 cuenta como confiable."""
        assert CategorySuggestion("Comida", 0.5, CategorizationSource.AI).is_confident(0.5)

    def test_is_confident_con_umbral_personalizado(self):
        suggestion = CategorySuggestion("Comida", 0.7, CategorizationSource.AI)

        assert suggestion.is_confident(0.6)
        assert not suggestion.is_confident(0.8)

    def test_igualdad_por_valor(self):
        assert CategorySuggestion("Comida", 0.8, CategorizationSource.AI) == CategorySuggestion(
            "Comida", 0.8, CategorizationSource.AI
        )

    def test_es_inmutable(self):
        suggestion = CategorySuggestion("Comida", 0.8, CategorizationSource.AI)
        with pytest.raises(FrozenInstanceError):
            suggestion.confidence = 0.1


class TestTransactionDraft:
    """`TransactionDraft`: transaccion validada, todavia sin persistir."""

    def _draft(self, transaction_type, amount="50.00"):
        return TransactionDraft(
            account_id=uuid4(),
            amount=Money(amount, "COP"),
            transaction_type=transaction_type,
            occurred_on=TODAY,
            description="Almuerzo",
        )

    def test_los_campos_opcionales_son_none_por_defecto(self):
        draft = self._draft(TransactionType.EXPENSE)

        assert draft.category_name is None
        assert draft.categorization_source is None
        assert draft.confidence is None

    def test_signed_amount_de_un_ingreso_es_positivo(self):
        draft = self._draft(TransactionType.INCOME)
        assert draft.signed_amount() == Money("50.00", "COP")

    def test_signed_amount_de_un_gasto_es_negativo(self):
        draft = self._draft(TransactionType.EXPENSE)
        assert draft.signed_amount() == Money("-50.00", "COP")

    def test_signed_amount_no_muta_el_monto(self):
        draft = self._draft(TransactionType.EXPENSE)
        draft.signed_amount()
        assert draft.amount == Money("50.00", "COP")

    def test_acepta_account_id_como_cadena(self):
        draft = TransactionDraft(
            account_id="8a34b9c9-dca0-4e41-896e-05eb0abda990",
            amount=Money("10", "COP"),
            transaction_type=TransactionType.INCOME,
            occurred_on=TODAY,
            description="Pago",
        )
        assert isinstance(draft.account_id, str)

    def test_acepta_los_campos_de_categorizacion(self):
        draft = TransactionDraft(
            account_id=uuid4(),
            amount=Money("10", "COP"),
            transaction_type=TransactionType.EXPENSE,
            occurred_on=TODAY,
            description="Cafe",
            category_name="Comida",
            categorization_source=CategorizationSource.RULE,
            confidence=0.9,
        )

        assert draft.category_name == "Comida"
        assert draft.categorization_source is CategorizationSource.RULE
        assert draft.confidence == 0.9

    def test_no_valida_en_post_init(self):
        """El draft confia en `.build()`: existir ya significa ser valido.

        Un monto cero viola INV-04, pero el draft lo acepta porque la validacion
        ocurre una sola vez, en el builder (M4). Duplicarla aqui dejaria las dos
        copias libres de divergir.
        """
        draft = TransactionDraft(
            account_id=uuid4(),
            amount=Money.zero("COP"),
            transaction_type=TransactionType.EXPENSE,
            occurred_on=date(2999, 1, 1),
            description="",
        )

        assert draft.amount.is_zero()

    def test_es_inmutable(self):
        draft = self._draft(TransactionType.EXPENSE)
        with pytest.raises(FrozenInstanceError):
            draft.amount = Money("99", "COP")

    def test_igualdad_por_valor(self):
        account_id = uuid4()
        campos = {
            "account_id": account_id,
            "amount": Money("50", "COP"),
            "transaction_type": TransactionType.EXPENSE,
            "occurred_on": TODAY,
            "description": "Almuerzo",
        }
        assert TransactionDraft(**campos) == TransactionDraft(**campos)


class TestAccountDraft:
    """`AccountDraft`: cuenta validada, todavia sin persistir."""

    def _draft(self):
        return AccountDraft(
            user_id=uuid4(),
            name="Cuenta de ahorros",
            account_type=AccountType.BANK,
            initial_balance=Money.zero("COP"),
        )

    def test_construccion(self):
        draft = self._draft()

        assert draft.name == "Cuenta de ahorros"
        assert draft.account_type is AccountType.BANK
        assert draft.initial_balance == Money.zero("COP")

    def test_es_inmutable(self):
        draft = self._draft()
        with pytest.raises(FrozenInstanceError):
            draft.name = "Otro nombre"

    def test_igualdad_por_valor(self):
        user_id = uuid4()
        campos = {
            "user_id": user_id,
            "name": "Efectivo",
            "account_type": AccountType.CASH,
            "initial_balance": Money("100", "COP"),
        }
        assert AccountDraft(**campos) == AccountDraft(**campos)
