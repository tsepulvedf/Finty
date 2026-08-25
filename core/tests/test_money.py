"""Tests del Value Object `Money`.

Dominio puro: ningun test de este modulo lleva la marca `django_db`, asi que
pytest-django bloquea cualquier acceso a base de datos. Si un dia `Money`
empezara a tocar la base, estos tests fallarian.
"""
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from core.domain.exceptions import CurrencyMismatchError, ValidationError
from core.domain.value_objects import Money, validate_currency_code


class TestConstruccion:
    """Construccion y normalizacion del monto."""

    def test_acepta_decimal(self):
        assert Money(Decimal("1500.00"), "COP").amount == Decimal("1500.00")

    def test_acepta_int(self):
        assert Money(1500, "COP").amount == Decimal("1500.00")

    def test_acepta_cadena_numerica(self):
        assert Money("1500.50", "COP").amount == Decimal("1500.50")

    def test_rechaza_float(self):
        with pytest.raises(ValidationError) as error:
            Money(1500.5, "COP")
        assert "Decimal" in str(error.value)

    def test_rechaza_booleano(self):
        with pytest.raises(ValidationError):
            Money(True, "COP")

    def test_rechaza_cadena_no_numerica(self):
        with pytest.raises(ValidationError):
            Money("mil quinientos", "COP")

    def test_zero_construye_la_cantidad_nula(self):
        assert Money.zero("COP") == Money(Decimal("0.00"), "COP")


class TestCuantizacion:
    """El monto se cuantiza a dos decimales con ROUND_HALF_UP."""

    def test_completa_dos_decimales(self):
        assert Money(Decimal("10"), "COP").amount == Decimal("10.00")

    def test_redondea_hacia_arriba_en_el_medio(self):
        assert Money("10.005", "COP").amount == Decimal("10.01")

    def test_redondea_hacia_abajo_bajo_el_medio(self):
        assert Money("10.004", "COP").amount == Decimal("10.00")

    def test_redondea_negativos_alejandose_del_cero(self):
        assert Money("-10.005", "COP").amount == Decimal("-10.01")


class TestMoneda:
    """Normalizacion y validacion del codigo de moneda."""

    def test_normaliza_a_mayusculas(self):
        assert Money(1, "cop").currency == "COP"

    def test_ignora_espacios_sobrantes(self):
        assert Money(1, " usd ").currency == "USD"

    @pytest.mark.parametrize("codigo", ["CO", "COPS", "C0P", "", "12"])
    def test_rechaza_codigo_invalido(self, codigo):
        with pytest.raises(ValidationError):
            Money(1, codigo)

    def test_rechaza_codigo_que_no_es_cadena(self):
        with pytest.raises(ValidationError):
            Money(1, 170)

    def test_validate_currency_code_normaliza(self):
        assert validate_currency_code("usd") == "USD"

    def test_validate_currency_code_rechaza_invalido(self):
        with pytest.raises(ValidationError):
            validate_currency_code("PESO")


class TestOperaciones:
    """Aritmetica dentro de una misma moneda."""

    def test_add(self):
        assert Money("10.50", "COP").add(Money("4.50", "COP")) == Money("15.00", "COP")

    def test_operador_suma(self):
        assert Money(10, "COP") + Money(5, "COP") == Money(15, "COP")

    def test_subtract(self):
        assert Money("10.50", "COP").subtract(Money("0.50", "COP")) == Money("10.00", "COP")

    def test_operador_resta(self):
        assert Money(10, "COP") - Money(15, "COP") == Money(-5, "COP")

    def test_negate(self):
        assert Money("1500.00", "COP").negate() == Money("-1500.00", "COP")

    def test_negate_de_negativo_devuelve_positivo(self):
        assert Money("-1500.00", "COP").negate() == Money("1500.00", "COP")

    def test_is_zero(self):
        assert Money.zero("COP").is_zero()
        assert not Money("0.01", "COP").is_zero()

    def test_is_negative(self):
        assert Money("-0.01", "COP").is_negative()
        assert not Money.zero("COP").is_negative()
        assert not Money("0.01", "COP").is_negative()

    def test_las_operaciones_no_mutan_los_operandos(self):
        original = Money("10.00", "COP")
        original.add(Money("5.00", "COP"))
        assert original == Money("10.00", "COP")


class TestMonedasDistintas:
    """INV-11: operar monedas distintas es un error de dominio."""

    def test_suma_entre_monedas_distintas(self):
        with pytest.raises(CurrencyMismatchError):
            Money(10, "COP") + Money(10, "USD")

    def test_resta_entre_monedas_distintas(self):
        with pytest.raises(CurrencyMismatchError):
            Money(10, "COP") - Money(10, "USD")

    def test_comparacion_entre_monedas_distintas(self):
        with pytest.raises(CurrencyMismatchError):
            Money(10, "COP") < Money(10, "USD")

    def test_currency_mismatch_es_una_validacion(self):
        assert issubclass(CurrencyMismatchError, ValidationError)

    def test_operar_con_algo_que_no_es_money(self):
        with pytest.raises(ValidationError):
            Money(10, "COP").add(10)


class TestInmutabilidad:
    """El value object es inmutable de verdad."""

    def test_asignar_monto_falla(self):
        dinero = Money("10.00", "COP")
        with pytest.raises(FrozenInstanceError):
            dinero.amount = Decimal("20.00")

    def test_asignar_moneda_falla(self):
        dinero = Money("10.00", "COP")
        with pytest.raises(FrozenInstanceError):
            dinero.currency = "USD"

    def test_es_hasheable(self):
        assert len({Money(10, "COP"), Money(10, "COP")}) == 1


class TestComparaciones:
    """Orden total dentro de una misma moneda."""

    def test_menor_que(self):
        assert Money(10, "COP") < Money(20, "COP")

    def test_menor_o_igual(self):
        assert Money(10, "COP") <= Money(10, "COP")

    def test_mayor_que(self):
        assert Money(20, "COP") > Money(10, "COP")

    def test_mayor_o_igual(self):
        assert Money(20, "COP") >= Money(20, "COP")

    def test_igualdad_por_valor_y_moneda(self):
        assert Money(10, "COP") == Money("10.00", "COP")
        assert Money(10, "COP") != Money(10, "USD")

    def test_ordenamiento(self):
        montos = [Money(30, "COP"), Money(10, "COP"), Money(20, "COP")]
        assert sorted(montos) == [Money(10, "COP"), Money(20, "COP"), Money(30, "COP")]


class TestRepresentacion:
    """Representacion legible."""

    def test_str(self):
        assert str(Money("1500", "cop")) == "1500.00 COP"

    def test_str_negativo(self):
        assert str(Money("-1500.5", "USD")) == "-1500.50 USD"
