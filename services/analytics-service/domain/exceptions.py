"""Excepciones del dominio de analytics.

Heredan de `domain.shared.exceptions`; el handler de `api/errors.py` las traduce
a HTTP con el mismo formato que finance-service.
"""
from domain.shared.exceptions import BusinessRuleError, NotFoundError, ValidationError


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


class ReportNotFoundError(NotFoundError):
    """El reporte no existe o es de otro usuario (D-08: no se distingue)."""

    default_code = "report_not_found"
    default_message = "No encontramos ese reporte."


class ReportNotReadyError(BusinessRuleError):
    """Se pidio el archivo de un reporte que aun no esta listo, o que fallo."""

    default_code = "report_not_ready"
    default_message = "El reporte todavia no esta listo."
