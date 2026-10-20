"""Traduccion de errores a respuestas HTTP (anillo externo).

Es el equivalente de `core/api/exception_handler.py` del monolito mas el manejo
de errores que alli hacia DRF por su cuenta. Es el unico punto del servicio
donde un error se convierte en codigo de estado, asi que ningun blueprint
contiene un `try` (RULES.md, regla 3).

Formatos de respuesta, los mismos del monolito:
- Error de dominio: `{"error": {"code": ..., "message": ...}}`.
- Error de validacion: `{"campo": ["mensaje", ...]}`.
- Cualquier otro error HTTP: `{"detail": "..."}`.
"""
import logging
from uuid import UUID

from flask import jsonify, request
from werkzeug.exceptions import HTTPException, MethodNotAllowed
from werkzeug.exceptions import NotFound as RouteNotFound

import messages
from domain.shared.exceptions import (
    AuthenticationError,
    BusinessRuleError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

logger = logging.getLogger(__name__)

# Mismo mapeo que el monolito, de la subclase mas especifica a la mas general.
DOMAIN_ERROR_STATUS = (
    (ValidationError, 422),
    (BusinessRuleError, 409),
    (NotFoundError, 404),
    (PermissionDeniedError, 403),
    (AuthenticationError, 401),
)
DEFAULT_DOMAIN_STATUS = 400


class ApiError(Exception):
    """Error del contrato HTTP que no nace en el dominio."""

    status = 400
    headers = {}

    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail

    def body(self):
        """Cuerpo JSON de la respuesta."""
        return {"detail": self.detail}


class InvalidInput(ApiError):
    """La entrada no paso la validacion sintactica (400, forma de DRF)."""

    def __init__(self, errors):
        super().__init__(errors)

    def body(self):
        return self.detail


class NotAuthenticated(ApiError):
    """Falta `X-User-Id` o no es un UUID (401). INV-01 en el servicio."""

    status = 401
    # Mismo encabezado que respondia DRF con `TokenAuthentication`.
    headers = {"WWW-Authenticate": "Token"}

    def __init__(self):
        super().__init__(messages.NOT_AUTHENTICATED)


class NotFound(ApiError):
    """El recurso no existe para este usuario (404 con `detail`)."""

    status = 404

    def __init__(self, detail=messages.NOT_FOUND):
        super().__init__(detail)


class ParseError(ApiError):
    """El cuerpo no es JSON valido (400)."""


class UnsupportedMediaType(ApiError):
    """El cuerpo no es JSON (415)."""

    status = 415


def or_404(found, model, pk):
    """Devuelve `found` o lanza `NotFound` con el mismo `detail` que el monolito.

    Reproduce `get_object` de DRF sobre `get_object_or_404` de Django: un id con
    forma de UUID que no existe da `No <Modelo> matches the given query.`; un id
    mal formado da `No encontrado.`.
    """
    if found is not None:
        return found
    try:
        UUID(str(pk))
    except ValueError:
        raise NotFound() from None
    raise NotFound(messages.MODEL_NOT_FOUND.format(model=model))


def _status_for(exc):
    """Codigo HTTP de una excepcion de dominio."""
    for error_class, http_status in DOMAIN_ERROR_STATUS:
        if isinstance(exc, error_class):
            return http_status
    return DEFAULT_DOMAIN_STATUS


def _handle_domain_error(exc):
    return (
        jsonify({"error": {"code": exc.code, "message": exc.message}}),
        _status_for(exc),
    )


def _handle_api_error(exc):
    return jsonify(exc.body()), exc.status, exc.headers


def _handle_route_not_found(exc):
    return jsonify({"detail": messages.NOT_FOUND}), 404


def _handle_method_not_allowed(exc):
    body = {"detail": messages.METHOD_NOT_ALLOWED.format(method=request.method)}
    return jsonify(body), 405, {"Allow": ", ".join(exc.valid_methods or [])}


def _handle_http_exception(exc):
    return jsonify({"detail": exc.description}), exc.code


def _handle_unexpected(exc):
    logger.exception("Error no controlado en %s %s", request.method, request.path)
    return jsonify({"detail": messages.SERVER_ERROR}), 500


def register_error_handlers(app):
    """Registra los traductores de error en la aplicacion."""
    app.register_error_handler(DomainError, _handle_domain_error)
    app.register_error_handler(ApiError, _handle_api_error)
    app.register_error_handler(RouteNotFound, _handle_route_not_found)
    app.register_error_handler(MethodNotAllowed, _handle_method_not_allowed)
    app.register_error_handler(HTTPException, _handle_http_exception)
    app.register_error_handler(Exception, _handle_unexpected)
