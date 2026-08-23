"""Traduccion de excepciones de dominio a respuestas HTTP (anillo externo).

Este es el unico punto del sistema donde un `DomainError` se convierte en un
codigo de estado HTTP. Gracias a el, los services lanzan excepciones puras de
dominio y las views no traducen nada a mano (CLAUDE.md, regla 3).
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

from core.domain.exceptions import (
    AuthenticationError,
    BusinessRuleError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

# Mapeo explicito de excepcion de dominio a codigo HTTP. El orden importa: se
# recorre de la subclase mas especifica a la mas general.
DOMAIN_ERROR_STATUS = (
    (ValidationError, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (BusinessRuleError, status.HTTP_409_CONFLICT),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (PermissionDeniedError, status.HTTP_403_FORBIDDEN),
    # Un fallo de credenciales no es un conflicto ni una peticion malformada:
    # es una peticion no autenticada.
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
)


def _status_for(exc):
    """Devuelve el codigo HTTP correspondiente a una excepcion de dominio."""
    for error_class, http_status in DOMAIN_ERROR_STATUS:
        if isinstance(exc, error_class):
            return http_status
    return status.HTTP_400_BAD_REQUEST


def domain_exception_handler(exc, context):
    """Handler global registrado en `REST_FRAMEWORK["EXCEPTION_HANDLER"]`.

    Las excepciones de dominio se serializan con el formato uniforme
    `{"error": {"code": ..., "message": ...}}`. Cualquier otra excepcion se
    delega al handler por defecto de DRF.
    """
    if isinstance(exc, DomainError):
        # Deshace la transaccion abierta, igual que hace DRF con sus propias
        # excepciones; necesario para los casos de uso atomicos.
        set_rollback()
        return Response(
            {"error": {"code": exc.code, "message": exc.message}},
            status=_status_for(exc),
        )

    return drf_exception_handler(exc, context)
