"""Doble del puerto `EntitlementsReader` para los tests del gating (INV-06)."""
from datetime import datetime, timedelta, timezone

from domain.entitlements import Entitlement
from domain.interfaces import EntitlementsReader, EntitlementsUnavailable


class FakeEntitlements(EntitlementsReader):
    """Premium por defecto, para que los tests de las reglas no dependan del plan."""

    def __init__(self):
        self.premium = True
        self.down = False
        self.calls = []

    def entitlement(self, user_id):
        self.calls.append(user_id)
        if self.down:
            raise EntitlementsUnavailable("subscription-service caido")
        if self.premium:
            return Entitlement(True, datetime.now(timezone.utc) + timedelta(days=30))
        return Entitlement(False, None)
