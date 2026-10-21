"""`Entitlement`: el derecho premium de un usuario, segun subscription-service.

Es la vista de este servicio sobre `GET /internal/entitlements/<user_id>` (§10.9).
Copia propia, como el nucleo compartido de D-13: ningun servicio importa codigo de
otro.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Entitlement:
    premium: bool
    until: datetime | None = None

    def is_premium_at(self, now):
        """Premium mientras no termine el periodo pagado."""
        return self.premium and (self.until is None or now < self.until)
