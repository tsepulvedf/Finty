"""Estado por peticion y armado del servicio (anillo externo).

La identidad sale solo de `X-User-Id` (ADR-09). El endpoint interno de derechos
no la pide: lo consultan otros servicios por la red interna con el `user_id` en
la ruta, y Nginx bloquea `/internal/` desde fuera.
"""
from uuid import UUID

from flask import current_app, g, request
from werkzeug.exceptions import MethodNotAllowed

from api.errors import NotAuthenticated
from services import NotificationService, SubscriptionService

SESSION_FACTORY_KEY = "finty.session_factory"
GATEWAY_KEY = "finty.payment_gateway"
CLOCK_KEY = "finty.clock"
NOTIFICATION_QUEUE_KEY = "finty.notification_queue"
CONTACTS_KEY = "finty.contacts"
EMAIL_COMPOSER_KEY = "finty.email_composer"
EMAIL_SENDER_KEY = "finty.email_sender"
USER_ID_HEADER = "X-User-Id"
PUBLIC_ENDPOINTS = {"health", "internal.entitlements"}


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


def subscription_service():
    return SubscriptionService(
        db_session(),
        current_app.extensions[GATEWAY_KEY],
        current_app.config["SUBSCRIPTION_PLANS"],
        current_app.extensions[CLOCK_KEY],
        current_app.extensions.get(NOTIFICATION_QUEUE_KEY),
    )


def notification_service():
    """Casos de uso de los correos (E2-M7), para las tareas de Celery."""
    extensions = current_app.extensions
    return NotificationService(
        db_session(),
        extensions[CONTACTS_KEY],
        extensions[EMAIL_COMPOSER_KEY],
        extensions[EMAIL_SENDER_KEY],
        extensions[CLOCK_KEY],
        current_app.config["NOTIFY_DAYS_BEFORE_EXPIRY"],
    )
