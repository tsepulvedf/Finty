"""Excepciones del dominio de categorizacion.

Subconjunto de las de `finance-service`: la clasificacion solo puede rechazar un
tipo de transaccion invalido. Heredan de `domain.shared.exceptions`.
"""
from domain.shared.exceptions import ValidationError


class InvalidTransactionTypeError(ValidationError):
    """El tipo de transaccion no pertenece al conjunto valido (INV-09)."""

    default_code = "invalid_transaction_type"
    default_message = "El tipo de transaccion no es valido."
