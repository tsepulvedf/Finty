"""Reglas y servicios de dominio de `finance` (anillo de Dominio, Python puro).

`BalanceCalculator` deriva balances a partir de movimientos (INV-07).
`TransactionRules` agrupa las comprobaciones que no pertenecen a ninguna entidad
concreta y que consumen los builders (M4) y los services (M5).

Ambas clases son **sin estado**: todos sus metodos son estaticos y reciben por
argumento cuanto necesitan. No guardan referencias, no consultan nada y no
producen efectos de lado.

Reciben tipos primitivos y objetos de valor, **nunca modelos de Django**.
`ensure_account_is_active` recibe un booleano, no un `Account`; asi el dominio
permanece ignorante del ORM y estas reglas se prueban sin base de datos.

Este modulo no importa Django. Para la fecha de hoy usa `datetime.date` de la
stdlib, nunca la utilidad de zona horaria del framework.
"""
from datetime import date

from core.domain.exceptions import CurrencyMismatchError
from core.domain.value_objects import Money, validate_currency_code
from finance.domain.exceptions import (
    ArchivedAccountError,
    FutureTransactionDateError,
    NegativeBalanceNotAllowedError,
    UncategorizedTransactionError,
    ZeroAmountError,
)


class BalanceCalculator:
    """Aritmetica de balances (INV-07).

    **Calcula, no juzga.** Un balance resultante negativo es un valor legitimo
    de `Money` y esta clase lo devuelve sin objetar. Quien decide si ese saldo es
    admisible para el tipo de cuenta es `TransactionRules.ensure_balance_allowed`
    (INV-14). Separar las dos responsabilidades permite que un service calcule el
    saldo hipotetico primero y decida despues.
    """

    @staticmethod
    def apply(current_balance, amount, transaction_type):
        """Aplica un movimiento a un balance y devuelve el balance resultante.

        El signo lo decide `TransactionType.sign()`; aqui no se replica. Operar
        monedas distintas lanza `CurrencyMismatchError` (INV-11), porque la suma
        la hace `Money`.
        """
        if transaction_type.sign() > 0:
            return current_balance.add(amount)
        return current_balance.subtract(amount)

    @staticmethod
    def revert(current_balance, amount, transaction_type):
        """Deshace un movimiento previamente aplicado.

        Es la operacion exactamente inversa de `apply`: aplicar y luego revertir
        el mismo movimiento devuelve el balance original. La usa M5 al eliminar
        una transaccion, para no tener que recalcular la cuenta entera.
        """
        if transaction_type.sign() > 0:
            return current_balance.subtract(amount)
        return current_balance.add(amount)

    @staticmethod
    def recompute(initial_balance, movements):
        """Recalcula un balance desde cero sobre una secuencia de movimientos.

        `movements` es un iterable de tuplas `(Money, TransactionType)`. Es la
        referencia contra la que se verifica INV-07: el balance persistido de una
        cuenta debe coincidir con lo que devuelve este metodo sobre todas sus
        transacciones.
        """
        balance = initial_balance
        for amount, transaction_type in movements:
            balance = BalanceCalculator.apply(balance, amount, transaction_type)
        return balance


class TransactionRules:
    """Invariantes de transaccion y de cuenta que no viven en una entidad.

    Cada metodo o no hace nada, o lanza la excepcion de dominio que corresponde a
    su invariante. Ninguno devuelve un booleano: el resultado de una regla
    violada es una excepcion, no un valor que el llamador pueda ignorar por
    descuido.
    """

    @staticmethod
    def ensure_amount_not_zero(amount):
        """INV-04: el monto de una transaccion no puede ser cero."""
        if amount.is_zero():
            raise ZeroAmountError()

    @staticmethod
    def ensure_currency_matches(expected, actual):
        """INV-11: la moneda de la transaccion es la de la cuenta.

        Acepta indistintamente `Money` o el codigo de moneda como cadena, para
        poder compararse tanto entre dos montos como contra la moneda declarada
        de una cuenta.
        """
        expected_currency = TransactionRules._currency_of(expected)
        actual_currency = TransactionRules._currency_of(actual)
        if expected_currency != actual_currency:
            raise CurrencyMismatchError(
                f"La moneda esperada es {expected_currency} y se recibio "
                f"{actual_currency}."
            )

    @staticmethod
    def ensure_date_not_future(occurred_on, today=None):
        """INV-12: la fecha de la transaccion no puede estar en el futuro.

        `today` es inyectable por dos razones: el dominio no puede usar la
        utilidad de zona horaria del framework, y un test que dependa del reloj
        del sistema falla solo el dia equivocado. Hoy es una fecha valida.
        """
        reference_date = today if today is not None else date.today()
        if occurred_on > reference_date:
            raise FutureTransactionDateError(
                f"La fecha {occurred_on.isoformat()} es posterior a "
                f"{reference_date.isoformat()}."
            )

    @staticmethod
    def ensure_account_is_active(is_archived):
        """No se puede operar sobre una cuenta archivada.

        Recibe un booleano y no un `Account` a proposito: el dominio no conoce el
        modelo. El service extrae el flag y lo pasa.
        """
        if is_archived:
            raise ArchivedAccountError()

    @staticmethod
    def ensure_categorized(category_name):
        """INV-08: tras la categorizacion debe quedar una categoria asignada."""
        if category_name is None or not str(category_name).strip():
            raise UncategorizedTransactionError()

    @staticmethod
    def ensure_balance_allowed(account_type, resulting_balance):
        """INV-14: el saldo resultante debe ser admisible para el tipo de cuenta.

        Delega en `AccountType.allows_negative_balance()`; que un credito admita
        numeros rojos es conocimiento del tipo de cuenta, no de esta regla.
        """
        if resulting_balance.is_negative() and not account_type.allows_negative_balance():
            raise NegativeBalanceNotAllowedError(
                f"Una cuenta de tipo '{account_type.value}' no puede quedar en "
                f"{resulting_balance}."
            )

    @staticmethod
    def _currency_of(value):
        """Extrae el codigo de moneda de un `Money` o de una cadena."""
        if isinstance(value, Money):
            return value.currency
        return validate_currency_code(value)
