"""Traduccion de errores a HTTP, con el mismo formato que finance-service.

- Error de dominio: `{"error": {"code": ..., "message": ...}}`.
- Error de validacion de entrada: `{"campo": ["mensaje"]}` (400).
- Cualquier otro error HTTP: `{"detail": "..."}`.
"""
import logging

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

DOMAIN_ERROR_STATUS = (
    (ValidationError, 422),
    (BusinessRuleError, 409),
    (NotFoundError, 404),
    (PermissionDeniedError, 403),
    (AuthenticationError, 401),
)


class ApiError(Exception):
    status = 400
    headers = {}

    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail

    def body(self):
        return {"detail": self.detail}


class InvalidInput(ApiError):
    """Parametros de entrada con forma invalida (400, `{"campo": [...]}`)."""

    def body(self):
        return self.detail


class ParseError(ApiError):
    """El cuerpo no es JSON valido (400)."""


class UnsupportedMediaType(ApiError):
    """El cuerpo no es JSON (415)."""

    status = 415


class NotAuthenticated(ApiError):
    status = 401
    headers = {"WWW-Authenticate": "Token"}

    def __init__(self):
        super().__init__(messages.NOT_AUTHENTICATED)


def _status_for(exc):
    for error_class, status in DOMAIN_ERROR_STATUS:
        if isinstance(exc, error_class):
            return status
    return 400


def register_error_handlers(app):
    app.register_error_handler(
        DomainError,
        lambda exc: (jsonify({"error": {"code": exc.code, "message": exc.message}}), _status_for(exc)),
    )
    app.register_error_handler(ApiError, lambda exc: (jsonify(exc.body()), exc.status, exc.headers))
    app.register_error_handler(RouteNotFound, lambda exc: (jsonify({"detail": messages.NOT_FOUND}), 404))
    app.register_error_handler(
        MethodNotAllowed,
        lambda exc: (
            jsonify({"detail": messages.METHOD_NOT_ALLOWED.format(method=request.method)}),
            405,
            {"Allow": ", ".join(exc.valid_methods or [])},
        ),
    )
    app.register_error_handler(HTTPException, lambda exc: (jsonify({"detail": exc.description}), exc.code))
    app.register_error_handler(Exception, _handle_unexpected)


def _handle_unexpected(exc):
    logger.exception("Error no controlado en %s %s", request.method, request.path)
    return jsonify({"detail": messages.SERVER_ERROR}), 500


class PremiumRequired(ApiError):
    """INV-06: la funcion es premium y el usuario no tiene el derecho (403)."""

    status = 403

    def __init__(self, message=None):
        super().__init__(message or messages.PREMIUM_REQUIRED)

    def body(self):
        return {"error": {"code": "premium_required", "message": self.detail}}


class EntitlementsUnavailableError(ApiError):
    """No se pudo verificar el derecho: se niega la funcion premium (503)."""

    status = 503

    def __init__(self):
        super().__init__(messages.ENTITLEMENTS_UNAVAILABLE)

    def body(self):
        return {"error": {"code": "entitlements_unavailable", "message": self.detail}}
