"""Traduccion de errores a respuestas HTTP del contrato interno.

Toda respuesta de error tiene la forma `{"error": {"code": ..., "message": ...}}`,
la misma de los errores de dominio de Finty. Un 400 agrega `fields` con los
errores por campo. Es el unico punto donde un error se convierte en codigo de
estado, asi que el blueprint no tiene `try` (RULES.md, regla 3).
"""
import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException, MethodNotAllowed, NotFound

import messages
from domain.shared.exceptions import DomainError
from infra.factories import ConfigurationError

logger = logging.getLogger(__name__)


class InvalidRequest(Exception):
    """El cuerpo no cumple el contrato (400)."""

    def __init__(self, fields=None, message=messages.INVALID_REQUEST):
        super().__init__(message)
        self.message = message
        self.fields = fields or {}


def _error(code, message, status, **extra):
    return jsonify({"error": {"code": code, "message": message, **extra}}), status


def _handle_invalid_request(exc):
    return _error("invalid_request", exc.message, 400, fields=exc.fields)


def _handle_domain_error(exc):
    return _error(exc.code, exc.message, 400)


def _handle_not_found(exc):
    return _error("not_found", messages.NOT_FOUND, 404)


def _handle_method_not_allowed(exc):
    body, status = _error("method_not_allowed", messages.METHOD_NOT_ALLOWED, 405)
    return body, status, {"Allow": ", ".join(exc.valid_methods or [])}


def _handle_configuration_error(exc):
    logger.error("Configuracion invalida: %s", exc)
    return _error("configuration_error", messages.CONFIGURATION_ERROR, 500)


def _handle_http_exception(exc):
    return _error("http_error", exc.description, exc.code)


def _handle_unexpected(exc):
    logger.exception("Error no controlado")
    return _error("server_error", messages.SERVER_ERROR, 500)


def register_error_handlers(app):
    """Registra los traductores de error en la aplicacion."""
    app.register_error_handler(InvalidRequest, _handle_invalid_request)
    app.register_error_handler(DomainError, _handle_domain_error)
    app.register_error_handler(ConfigurationError, _handle_configuration_error)
    app.register_error_handler(NotFound, _handle_not_found)
    app.register_error_handler(MethodNotAllowed, _handle_method_not_allowed)
    app.register_error_handler(HTTPException, _handle_http_exception)
    app.register_error_handler(Exception, _handle_unexpected)
