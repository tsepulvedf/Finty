"""Adaptador HTTP; no consulta cuentas, usuarios ni transacciones."""
import hmac
import os
from uuid import uuid4

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from core.domain.exceptions import DomainError
from services.categorization.business import CategorizationService


def create_app(service=None, service_token=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    token = service_token or os.environ.get("CATEGORIZATION_SERVICE_TOKEN")
    if not token:
        raise RuntimeError("Falta CATEGORIZATION_SERVICE_TOKEN.")
    business = service or CategorizationService()

    def error(code, message, status):
        return jsonify(error={"code": code, "message": message,
                              "request_id": g.request_id}), status

    @app.before_request
    def identify_and_authorize():
        g.request_id = str(uuid4())
        if request.path != "/healthz" and not hmac.compare_digest(
            request.headers.get("X-Service-Token", ""), token
        ):
            return error("UNAUTHORIZED", "Credencial de servicio invalida.", 401)

    @app.after_request
    def identify_response(response):
        response.headers["X-Request-ID"] = g.request_id
        response.headers["X-Finty-Service"] = "flask-categorization"
        return response

    @app.get("/healthz")
    def health():
        return jsonify(status="ok", service="categorization", version="v2")

    @app.post("/api/v2/categorization/")
    def suggest():
        return jsonify(business.suggest(request.get_json()))

    @app.errorhandler(DomainError)
    def invalid_domain(exc):
        return error("INVALID_INPUT", str(exc), 400)

    @app.errorhandler(HTTPException)
    def invalid_http(exc):
        return error(exc.name.upper().replace(" ", "_"), exc.description, exc.code)

    @app.errorhandler(Exception)
    def unexpected(exc):
        app.logger.error("Error inesperado request_id=%s", g.request_id,
                         exc_info=(type(exc), exc, exc.__traceback__))
        return error("INTERNAL_ERROR", "No fue posible clasificar la transaccion.", 500)

    return app
