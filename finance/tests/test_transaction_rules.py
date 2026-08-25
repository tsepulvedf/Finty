"""Tests de `TransactionRules`: un caso que pasa y uno que falla por regla.

Dominio puro: sin marca `django_db`, corren sin PostgreSQL levantado. Ninguna
regla recibe un modelo de Django; todas trabajan con primitivos y value objects.
"""
from datetime import date, timedelta

import pytest

from core.domain.exceptions import CurrencyMismatchError, ValidationError
from core.domain.value_objects import Money
from finance.domain.exceptions import (
    ArchivedAccountError,
    FutureTransactionDateError,
    NegativeBalanceNotAllowedError,
    UncategorizedTransactionError,
    ZeroAmountError,
)
from finance.domain.logic import TransactionRules
from finance.domain.value_objects import AccountType

TODAY = date(2026, 8, 23)
TOMORROW = TODAY + timedelta(days=1)
YESTERDAY = TODAY - timedelta(days=1)


def cop(amount):
    """Atajo para construir pesos colombianos."""
    return Money(amount, "COP")


class TestMontoNoCero:
    """INV-04."""

    def test_un_monto_positivo_pasa(self):
        TransactionRules.ensure_amount_not_zero(cop("0.01"))

    def test_un_monto_negativo_pasa(self):
        """La regla es sobre el cero, no sobre el signo."""
        TransactionRules.ensure_amount_not_zero(cop("-50"))

    def test_cero_falla(self):
        with pytest.raises(ZeroAmountError):
            TransactionRules.ensure_amount_not_zero(Money.zero("COP"))

    def test_cero_con_decimales_tambien_falla(self):
        with pytest.raises(ZeroAmountError):
            TransactionRules.ensure_amount_not_zero(cop("0.00"))

    def test_el_error_trae_su_codigo(self):
        with pytest.raises(ZeroAmountError) as error:
            TransactionRules.ensure_amount_not_zero(Money.zero("COP"))
        assert error.value.code == "zero_amount"


class TestMonedaCoincide:
    """INV-11."""

    def test_dos_money_de_la_misma_moneda_pasan(self):
        TransactionRules.ensure_currency_matches(cop("100"), cop("50"))

    def test_money_contra_codigo_en_cadena_pasa(self):
        TransactionRules.ensure_currency_matches("COP", cop("50"))

    def test_dos_codigos_en_cadena_pasan(self):
        TransactionRules.ensure_currency_matches("COP", "cop")

    def test_monedas_distintas_fallan(self):
        with pytest.raises(CurrencyMismatchError):
            TransactionRules.ensure_currency_matches(cop("100"), Money("50", "USD"))

    def test_money_contra_codigo_distinto_falla(self):
        with pytest.raises(CurrencyMismatchError):
            TransactionRules.ensure_currency_matches("USD", cop("50"))

    def test_un_codigo_invalido_falla_como_validacion(self):
        """Un codigo mal formado lo rechaza `validate_currency_code` de core."""
        with pytest.raises(ValidationError):
            TransactionRules.ensure_currency_matches("PESO", cop("50"))


class TestFechaNoFutura:
    """INV-12, con `today` inyectado para no depender del reloj."""

    def test_una_fecha_pasada_pasa(self):
        TransactionRules.ensure_date_not_future(YESTERDAY, today=TODAY)

    def test_la_fecha_de_hoy_es_valida(self):
        TransactionRules.ensure_date_not_future(TODAY, today=TODAY)

    def test_manana_falla(self):
        with pytest.raises(FutureTransactionDateError):
            TransactionRules.ensure_date_not_future(TOMORROW, today=TODAY)

    def test_un_futuro_lejano_falla(self):
        with pytest.raises(FutureTransactionDateError):
            TransactionRules.ensure_date_not_future(date(2999, 1, 1), today=TODAY)

    def test_sin_today_usa_la_fecha_del_sistema(self):
        """Por defecto `today` es `date.today()`, de la stdlib, no de Django."""
        TransactionRules.ensure_date_not_future(date(2020, 1, 1))

        with pytest.raises(FutureTransactionDateError):
            TransactionRules.ensure_date_not_future(date.today() + timedelta(days=1))


class TestCuentaActiva:
    """Operar sobre una cuenta archivada."""

    def test_una_cuenta_activa_pasa(self):
        TransactionRules.ensure_account_is_active(is_archived=False)

    def test_una_cuenta_archivada_falla(self):
        with pytest.raises(ArchivedAccountError):
            TransactionRules.ensure_account_is_active(is_archived=True)

    def test_recibe_un_booleano_no_un_modelo(self):
        """El dominio no conoce `Account`: el service extrae el flag y lo pasa."""
        import inspect

        firma = inspect.signature(TransactionRules.ensure_account_is_active)
        assert list(firma.parameters) == ["is_archived"]


class TestCategorizada:
    """INV-08."""

    def test_una_categoria_presente_pasa(self):
        TransactionRules.ensure_categorized("Comida")

    def test_none_falla(self):
        with pytest.raises(UncategorizedTransactionError):
            TransactionRules.ensure_categorized(None)

    @pytest.mark.parametrize("name", ["", "   ", "\t"])
    def test_una_categoria_vacia_falla(self, name):
        with pytest.raises(UncategorizedTransactionError):
            TransactionRules.ensure_categorized(name)


class TestBalanceAdmisible:
    """INV-14."""

    def test_un_saldo_positivo_pasa_en_cualquier_tipo(self):
        for account_type in AccountType:
            TransactionRules.ensure_balance_allowed(account_type, cop("100"))

    def test_un_saldo_cero_pasa_en_cualquier_tipo(self):
        for account_type in AccountType:
            TransactionRules.ensure_balance_allowed(account_type, Money.zero("COP"))

    def test_un_saldo_negativo_se_permite_en_credito(self):
        TransactionRules.ensure_balance_allowed(AccountType.CREDIT, cop("-500"))

    @pytest.mark.parametrize("account_type", [AccountType.CASH, AccountType.BANK])
    def test_un_saldo_negativo_se_rechaza_en_efectivo_y_banco(self, account_type):
        with pytest.raises(NegativeBalanceNotAllowedError):
            TransactionRules.ensure_balance_allowed(account_type, cop("-0.01"))

    def test_el_mensaje_nombra_el_tipo_de_cuenta(self):
        with pytest.raises(NegativeBalanceNotAllowedError) as error:
            TransactionRules.ensure_balance_allowed(AccountType.CASH, cop("-50"))

        assert "cash" in str(error.value)
        assert error.value.code == "negative_balance_not_allowed"


class TestSinEstado:
    """Las reglas son estaticas y no guardan nada entre llamadas."""

    def test_los_metodos_son_estaticos(self):
        metodos = [
            "ensure_amount_not_zero",
            "ensure_currency_matches",
            "ensure_date_not_future",
            "ensure_account_is_active",
            "ensure_categorized",
            "ensure_balance_allowed",
        ]
        for nombre in metodos:
            assert isinstance(
                TransactionRules.__dict__[nombre], staticmethod
            ), f"{nombre} deberia ser staticmethod"

    def test_se_invocan_sin_instanciar(self):
        TransactionRules.ensure_amount_not_zero(cop("1"))
