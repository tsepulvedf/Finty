"""Estado por peticion: sesion de base, identidad y periodo pedido.

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
from domain.exceptions import InvalidPeriodError
from domain.period import Period

SESSION_FACTORY_KEY = "finty.session_factory"
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
