"""Estado por peticion: sesion de base, identidad, periodo e idioma pedidos.

La identidad sale solo de `X-User-Id`, que pone el Gateway tras `auth_request`
(ADR-09); el servicio no valida tokens. El resumen publico y la sonda de salud
no la piden.
"""
from datetime import date
from uuid import UUID

from flask import current_app, g, request
from werkzeug.exceptions import MethodNotAllowed

import messages
from api.errors import InvalidInput, NotAuthenticated
from services import ReportService
from domain.exceptions import InvalidPeriodError
from domain.period import Period

SESSION_FACTORY_KEY = "finty.session_factory"
REPORT_RENDERER_KEY = "finty.report_renderer"
REPORT_QUEUE_KEY = "finty.report_queue"
USER_ID_HEADER = "X-User-Id"
PUBLIC_ENDPOINTS = {"health", "public.spending_summary"}


def db_session():
    if "db_session" not in g:
        g.db_session = current_app.extensions[SESSION_FACTORY_KEY]()
    return g.db_session


def close_db_session(_exc=None):
    session = g.pop("db_session", None)
    if session is not None:
        session.close()


def current_user_id():
    return g.user_id


def identify_user():
    """Exige `X-User-Id` en las rutas autenticadas, antes del despacho (como DRF)."""
    routing_error = request.routing_exception
    if routing_error is not None and not isinstance(routing_error, MethodNotAllowed):
        return
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    try:
        g.user_id = UUID(request.headers.get(USER_ID_HEADER, "").strip())
    except ValueError as exc:
        raise NotAuthenticated() from exc


def requested_period():
    """`?period=AAAA-MM`; sin el, el mes actual en la zona del proceso."""
    raw = request.args.getlist("period")
    if not raw or not raw[-1].strip():
        return Period.of(date.today())
    try:
        return Period.parse(raw[-1])
    except InvalidPeriodError as exc:
        raise InvalidInput({"period": [messages.INVALID_PERIOD]}) from exc


def body_period():
    """`{"period": "AAAA-MM"}` del cuerpo JSON (POST /reports/)."""
    body = request.get_json(silent=True)
    raw = body.get("period") if isinstance(body, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidInput({"period": [messages.PERIOD_REQUIRED]})
    try:
        return Period.parse(raw)
    except InvalidPeriodError as exc:
        raise InvalidInput({"period": [messages.INVALID_PERIOD]}) from exc


def requested_language():
    """Primera etiqueta de `Accept-Language` (`en-US,en;q=0.9` → `en-US`); el
    servicio la reduce a `es` o `en`."""
    header = request.headers.get("Accept-Language", "")
    return header.split(",")[0].split(";")[0].strip()


def report_service():
    """`ReportService` con los adaptadores de la aplicacion (web o worker)."""
    extensions = current_app.extensions
    return ReportService(db_session(), extensions[REPORT_RENDERER_KEY], extensions.get(REPORT_QUEUE_KEY))
