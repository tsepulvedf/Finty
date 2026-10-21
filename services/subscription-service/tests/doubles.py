"""Dobles de subscription-service: pasarela configurable y reloj controlable."""
from datetime import datetime, timedelta, timezone

from domain.interfaces import PaymentGateway, PaymentOutcome
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
