"""Excepciones del dominio de analytics.

Heredan de `domain.shared.exceptions`; el handler de `api/errors.py` las traduce
a HTTP con el mismo formato que finance-service.
"""
from domain.shared.exceptions import ValidationError


class InvalidTransactionTypeError(ValidationError):
    """El tipo de transaccion no pertenece al conjunto valido (INV-09)."""

    default_code = "invalid_transaction_type"
    default_message = "El tipo de transaccion no es valido."


class InvalidPeriodError(ValidationError):
    """El periodo no tiene la forma AAAA-MM o no es un mes valido."""

    default_code = "invalid_period"
    default_message = "El periodo debe tener la forma AAAA-MM."


class InvalidEventError(ValidationError):
    """Un mensaje del stream no cumple el contrato de eventos (§10.5)."""

    default_code = "invalid_event"
    default_message = "El evento no cumple el contrato."
