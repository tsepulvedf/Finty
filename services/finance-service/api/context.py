"""Estado por peticion: la sesion de base de datos y la identidad del usuario."""
from uuid import UUID

from flask import current_app, g, request
from werkzeug.exceptions import MethodNotAllowed

from api.errors import NotAuthenticated

SESSION_FACTORY_KEY = "finty.session_factory"
USER_ID_HEADER = "X-User-Id"

# Rutas que no exigen identidad: la sonda de salud la usa Docker, no un usuario.
PUBLIC_ENDPOINTS = {"health"}


def db_session():
    """Sesion de la peticion actual; se crea al primer uso y se cierra al final."""
    if "db_session" not in g:
        g.db_session = current_app.extensions[SESSION_FACTORY_KEY]()
    return g.db_session


def close_db_session(_exc=None):
    """Cierra la sesion de la peticion. Lo pendiente sin confirmar se revierte."""
    session = g.pop("db_session", None)
    if session is not None:
        session.close()


def current_user_id():
    """`user_id` de la peticion, resuelto por `identify_user()`."""
    return g.user_id


def identify_user():
    """Lee la identidad de `X-User-Id` (ADR-09). Sin ella, 401.

    El servicio **no valida tokens**: confia en la cabecera porque solo la puede
    poner el Gateway, que descarta la del cliente y escribe la que verifico
    Django. El servicio no publica puertos al host, asi que nadie mas lo alcanza.

    Corre antes del despacho, como la autenticacion de DRF: un metodo no
    permitido sin identidad responde 401, no 405. Una ruta inexistente responde
    404 sin pedir identidad, igual que el resolvedor de URLs de Django.
    """
    routing_error = request.routing_exception
    if routing_error is not None and not isinstance(routing_error, MethodNotAllowed):
        return
    if request.endpoint in PUBLIC_ENDPOINTS:
        return

    try:
        g.user_id = UUID(request.headers.get(USER_ID_HEADER, "").strip())
    except ValueError as exc:
        raise NotAuthenticated() from exc
