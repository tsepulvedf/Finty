"""Notificaciones por correo de las suscripciones (E2-M7, ADR-15).

Dos avisos, cada uno a lo sumo una vez por usuario, tipo y periodo de la
suscripcion (`current_period_end`); lo garantiza una restriccion unica en la
base (`sent_notification`):

- **PREMIUM_WELCOME**: al activarse la suscripcion.
- **SUBSCRIPTION_EXPIRING**: cuando faltan `days_before` dias o menos para el
  fin del periodo. No hay renovacion automatica (D-26), asi que aplica tanto a
  una ACTIVE como a una CANCELED.

El texto del correo sale del idioma del contacto; lo arma un adaptador de
`infra/`.
"""
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from domain.value_objects import SubscriptionStatus

DEFAULT_DAYS_BEFORE_EXPIRY = 3
SUPPORTED_LANGUAGES = ("es", "en")
DEFAULT_LANGUAGE = "es"


class NotificationKind(StrEnum):
    PREMIUM_WELCOME = "premium_welcome"
    SUBSCRIPTION_EXPIRING = "subscription_expiring"


@dataclass(frozen=True)
class Contact:
    """A quien se le escribe y en que idioma (lo da identity)."""

    email: str
    display_name: str
    language: str

    def __post_init__(self):
        if self.language not in SUPPORTED_LANGUAGES:
            object.__setattr__(self, "language", DEFAULT_LANGUAGE)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


def deserves_welcome(subscription, now):
    """La bienvenida solo tiene sentido si la suscripcion da acceso ahora."""
    return subscription.grants_premium(now)


def expiring_window(now, days_before=DEFAULT_DAYS_BEFORE_EXPIRY):
    """`(desde, hasta)`: las suscripciones cuyo fin cae en este intervalo se avisan."""
    return now, now + timedelta(days=days_before)


def is_expiring(subscription, now, days_before=DEFAULT_DAYS_BEFORE_EXPIRY):
    """Da acceso ahora y su periodo termina dentro de `days_before` dias."""
    if not subscription.grants_premium(now):
        return False
    start, end = expiring_window(now, days_before)
    return start < subscription.current_period_end <= end


def is_expired(subscription, now):
    """ACTIVE o CANCELED con el periodo ya terminado: pasa a EXPIRED (§6.7)."""
    return (
        subscription.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED)
        and subscription.effective_status(now) is SubscriptionStatus.EXPIRED
    )
