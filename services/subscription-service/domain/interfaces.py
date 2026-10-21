"""Puertos de subscription-service (ABC). `infra/` los implementa (ADR-14)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from domain.value_objects import PaymentStatus


@dataclass(frozen=True)
class PaymentRequest:
    """Lo que el gateway necesita para cobrar el periodo. Nada de su API cruza el puerto."""

    reference: str
    amount_in_cents: int
    currency: str
    user_id: UUID


@dataclass(frozen=True)
class PaymentOutcome:
    """Respuesta del gateway en el lenguaje de Finty (§12: `Payment`, no *transaction*)."""

    status: PaymentStatus
    detail: str = ""


class PaymentGateway(ABC):
    """Pasarela de pagos (ADR-14). Un fallo se traduce a ERROR en el servicio.

    El puerto admite un resultado PENDING para una pasarela asincrona; la unica
    implementacion de Finty, `MockPaymentGateway`, resuelve siempre en el acto.
    """

    name = "abstract"

    @abstractmethod
    def submit(self, request):
        """Envia el pago y devuelve un `PaymentOutcome`."""
