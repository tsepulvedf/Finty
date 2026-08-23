"""Tests de `BalanceCalculator` (INV-07).

Dominio puro: sin marca `django_db`, corren sin PostgreSQL levantado.
"""
import pytest

from core.domain.exceptions import CurrencyMismatchError
from core.domain.value_objects import Money
from finance.domain.exceptions import NegativeBalanceNotAllowedError
from finance.domain.logic import BalanceCalculator, TransactionRules
from finance.domain.value_objects import AccountType, TransactionType

INCOME = TransactionType.INCOME
EXPENSE = TransactionType.EXPENSE


def cop(amount):
    """Atajo para construir pesos colombianos."""
    return Money(amount, "COP")


class TestApply:
    """`apply`: efecto de un movimiento sobre un balance."""

    def test_un_ingreso_suma(self):
        assert BalanceCalculator.apply(cop("100"), cop("50"), INCOME) == cop("150.00")

    def test_un_gasto_resta(self):
        assert BalanceCalculator.apply(cop("100"), cop("30"), EXPENSE) == cop("70.00")

    def test_sobre_balance_cero(self):
        assert BalanceCalculator.apply(Money.zero("COP"), cop("25.50"), INCOME) == cop("25.50")

    def test_conserva_los_decimales(self):
        assert BalanceCalculator.apply(cop("100.01"), cop("0.99"), INCOME) == cop("101.00")

    def test_no_muta_los_operandos(self):
        balance = cop("100")
        movimiento = cop("30")

        BalanceCalculator.apply(balance, movimiento, EXPENSE)

        assert balance == cop("100.00")
        assert movimiento == cop("30.00")

    def test_devuelve_un_money_nuevo(self):
        balance = cop("100")
        assert BalanceCalculator.apply(balance, cop("0.01"), INCOME) is not balance


class TestRevert:
    """`revert`: operacion inversa de `apply`."""

    def test_revertir_un_ingreso_resta(self):
        assert BalanceCalculator.revert(cop("150"), cop("50"), INCOME) == cop("100.00")

    def test_revertir_un_gasto_suma(self):
        assert BalanceCalculator.revert(cop("70"), cop("30"), EXPENSE) == cop("100.00")

    @pytest.mark.parametrize("transaction_type", [INCOME, EXPENSE])
    @pytest.mark.parametrize("monto", ["0.01", "30", "1500.75", "999999.99"])
    def test_apply_y_revert_son_exactamente_inversas(self, transaction_type, monto):
        """Aplicar y luego revertir el mismo movimiento devuelve el original."""
        original = cop("1000.00")

        aplicado = BalanceCalculator.apply(original, cop(monto), transaction_type)
        revertido = BalanceCalculator.revert(aplicado, cop(monto), transaction_type)

        assert revertido == original

    def test_revert_y_luego_apply_tambien_son_inversas(self):
        original = cop("1000.00")

        revertido = BalanceCalculator.revert(original, cop("250.25"), EXPENSE)
        aplicado = BalanceCalculator.apply(revertido, cop("250.25"), EXPENSE)

        assert aplicado == original


class TestRecompute:
    """`recompute`: referencia autoritativa de INV-07."""

    def test_sin_movimientos_devuelve_el_balance_inicial(self):
        assert BalanceCalculator.recompute(cop("100"), []) == cop("100.00")

    def test_suma_ingresos_y_resta_gastos(self):
        movimientos = [
            (cop("1000"), INCOME),
            (cop("250"), EXPENSE),
            (cop("100"), EXPENSE),
            (cop("50"), INCOME),
        ]

        assert BalanceCalculator.recompute(Money.zero("COP"), movimientos) == cop("700.00")

    def test_coincide_con_aplicar_uno_a_uno(self):
        """INV-07: recalcular desde cero da lo mismo que ir aplicando."""
        movimientos = [
            (cop("500.33"), INCOME),
            (cop("120.99"), EXPENSE),
            (cop("75.01"), EXPENSE),
            (cop("1000.00"), INCOME),
            (cop("0.01"), EXPENSE),
        ]
        inicial = cop("250.00")

        uno_a_uno = inicial
        for monto, tipo in movimientos:
            uno_a_uno = BalanceCalculator.apply(uno_a_uno, monto, tipo)

        assert BalanceCalculator.recompute(inicial, movimientos) == uno_a_uno

    def test_acepta_cualquier_iterable(self):
        movimientos = ((cop("10"), INCOME) for _ in range(3))
        assert BalanceCalculator.recompute(Money.zero("COP"), movimientos) == cop("30.00")

    def test_el_orden_no_altera_el_resultado(self):
        movimientos = [(cop("100"), INCOME), (cop("30"), EXPENSE), (cop("5"), INCOME)]

        assert BalanceCalculator.recompute(
            Money.zero("COP"), movimientos
        ) == BalanceCalculator.recompute(Money.zero("COP"), list(reversed(movimientos)))


class TestMonedas:
    """INV-11: la aritmetica de balances no cruza monedas."""

    def test_apply_con_moneda_distinta(self):
        with pytest.raises(CurrencyMismatchError):
            BalanceCalculator.apply(cop("100"), Money("50", "USD"), INCOME)

    def test_apply_con_moneda_distinta_en_un_gasto(self):
        with pytest.raises(CurrencyMismatchError):
            BalanceCalculator.apply(cop("100"), Money("50", "USD"), EXPENSE)

    def test_revert_con_moneda_distinta(self):
        with pytest.raises(CurrencyMismatchError):
            BalanceCalculator.revert(cop("100"), Money("50", "USD"), INCOME)

    def test_recompute_con_una_moneda_intrusa(self):
        movimientos = [(cop("100"), INCOME), (Money("50", "USD"), EXPENSE)]

        with pytest.raises(CurrencyMismatchError):
            BalanceCalculator.recompute(Money.zero("COP"), movimientos)


class TestCalculaPeroNoJuzga:
    """Separacion entre calcular un balance y decidir si es admisible.

    `BalanceCalculator` es aritmetica pura: un saldo negativo es un `Money`
    perfectamente valido y lo devuelve sin objetar. Quien decide si ese saldo es
    admisible para el tipo de cuenta es `TransactionRules.ensure_balance_allowed`
    (INV-14). Son dos responsabilidades distintas, en dos clases distintas.
    """

    def test_apply_devuelve_un_balance_negativo_sin_objetar(self):
        resultante = BalanceCalculator.apply(cop("100"), cop("150"), EXPENSE)

        assert resultante == cop("-50.00")
        assert resultante.is_negative()

    def test_recompute_tambien_devuelve_negativos(self):
        movimientos = [(cop("100"), INCOME), (cop("500"), EXPENSE)]

        assert BalanceCalculator.recompute(Money.zero("COP"), movimientos) == cop("-400.00")

    def test_la_regla_acepta_ese_negativo_en_una_cuenta_de_credito(self):
        resultante = BalanceCalculator.apply(cop("100"), cop("150"), EXPENSE)

        TransactionRules.ensure_balance_allowed(AccountType.CREDIT, resultante)

    def test_la_regla_rechaza_ese_mismo_negativo_en_efectivo(self):
        resultante = BalanceCalculator.apply(cop("100"), cop("150"), EXPENSE)

        with pytest.raises(NegativeBalanceNotAllowedError):
            TransactionRules.ensure_balance_allowed(AccountType.CASH, resultante)
