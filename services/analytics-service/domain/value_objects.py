"""Tipos de transaccion y procedencia, copiados de finance-service sin cambios.

Llegan en el payload de los eventos (§10.5). Este modulo no importa Flask.
"""
from enum import StrEnum

from domain.shared.exceptions import ValidationError
from domain.exceptions import InvalidTransactionTypeError

class TransactionType(StrEnum):
    """Sentido de un movimiento financiero. Conjunto cerrado (INV-09)."""

    INCOME = "income"
    EXPENSE = "expense"

    @classmethod
    def from_value(cls, raw):
        """Normaliza un valor externo a un miembro del enum (INV-09)."""
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, str):
            raise InvalidTransactionTypeError(
                f"El tipo de transaccion debe ser una cadena, no "
                f"{type(raw).__name__}."
            )
        try:
            return cls(raw.strip().lower())
        except ValueError as exc:
            valid = ", ".join(member.value for member in cls)
            raise InvalidTransactionTypeError(
                f"'{raw}' no es un tipo de transaccion valido. "
                f"Opciones: {valid}."
            ) from exc

    def sign(self):
        """Devuelve el signo con que el movimiento afecta un balance.

        `+1` para ingreso, `-1` para gasto. Es la unica fuente de verdad sobre
        como un movimiento altera el balance: `BalanceCalculator` la consume y
        nadie mas replica el signo. Si un dia apareciera un tercer tipo, este
        es el unico punto a tocar.
        """
        return 1 if self is TransactionType.INCOME else -1


class CategorizationSource(StrEnum):
    """Origen de la categoria asignada a una transaccion.

    Mapea al campo `categorization_source` de ARCHITECTURE.md 5.2.

    Cada valor identifica **el mecanismo que realmente clasifico**, no el que se
    pidio (A-14). Por eso `MOCK` existe como valor propio: un doble de pruebas
    reportandose como `RULE` dejaria una traza de auditoria falsa. Por la misma
    razon, cuando el clasificador de proveedor externo degrada a su respaldo, la
    procedencia registrada es la del respaldo y no la suya.
    """

    AI = "ai"
    RULE = "rule"
    MANUAL = "manual"
    MOCK = "mock"
