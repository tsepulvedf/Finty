"""Tests de los value objects del dominio financiero.

Sin base de datos: corren sin PostgreSQL. Portado del monolito sin cambiar
las aserciones (E2-M2a); solo cambian los imports.
"""
from dataclasses import FrozenInstanceError
from datetime import date
from uuid import uuid4

import pytest

from domain.shared.exceptions import ValidationError
from domain.shared.value_objects import Money
from domain.exceptions import InvalidTransactionTypeError
from domain.value_objects import (
    CategorizationSource,
    CategorySuggestion,
    TransactionType,
)

TODAY = date(2026, 8, 23)


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
        assert CategorizationSource.MOCK.value == "mock"

    def test_existen_cuatro_origenes(self):
        """`mock` se agrega en M7 (C-19) para no falsear la procedencia (A-14)."""
        assert len(list(CategorizationSource)) == 4

    def test_cada_mecanismo_tiene_su_propio_valor(self):
        """A-14: ninguna procedencia se solapa con otra."""
        valores = [member.value for member in CategorizationSource]
        assert len(set(valores)) == len(valores)


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
