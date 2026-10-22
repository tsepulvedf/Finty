"""Dobles de subscription-service: pasarela, reloj, cola, contactos y correo."""
from datetime import datetime, timedelta, timezone

from domain.interfaces import (
    ContactDirectory,
    ContactNotFound,
    ContactUnavailable,
    EmailSender,
    NotificationQueue,
    PaymentGateway,
    PaymentOutcome,
)
from domain.notifications import Contact
from domain.value_objects import PaymentStatus

START = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, now=START):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class FakeGateway(PaymentGateway):
    """Aprueba por defecto; `outcome` o `error` cambian lo que responde."""

    name = "mock"

    def __init__(self):
        self.outcome = PaymentStatus.APPROVED
        self.error = None
        self.requests = []

    def submit(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return PaymentOutcome(self.outcome, "doble")


class MemoryNotificationQueue(NotificationQueue):
    """Guarda lo encolado; con `down`, falla como un broker caido."""

    def __init__(self):
        self.welcomes = []
        self.down = False

    def premium_activated(self, subscription_id):
        if self.down:
            raise ConnectionError("broker caido")
        self.welcomes.append(subscription_id)


class FakeContacts(ContactDirectory):
    """Contacto en espanol por defecto; `down` simula identity caido."""

    def __init__(self):
        self.language = "es"
        self.down = False
        self.missing = set()
        self.calls = []

    def contact(self, user_id):
        self.calls.append(user_id)
        if self.down:
            raise ContactUnavailable("identity caido")
        if user_id in self.missing:
            raise ContactNotFound(str(user_id))
        return Contact(f"{user_id.hex[:8]}@finty.co", "Ana Restrepo", self.language)


class MemoryEmailSender(EmailSender):
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)
