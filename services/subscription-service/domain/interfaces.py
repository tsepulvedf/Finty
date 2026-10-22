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


# --- Notificaciones (E2-M7) -----------------------------------------------------


class ContactUnavailable(Exception):
    """identity no respondio: es transitorio, la tarea reintenta."""


class ContactNotFound(Exception):
    """identity no conoce al usuario (o esta inactivo): no hay a quien escribirle."""


class ContactDirectory(ABC):
    """Datos de contacto de un usuario, que viven en identity (ADR-10)."""

    @abstractmethod
    def contact(self, user_id):
        """`Contact`, o `ContactUnavailable` / `ContactNotFound`."""


class EmailComposer(ABC):
    """Arma el correo de una notificacion en el idioma del contacto."""

    @abstractmethod
    def compose(self, kind, contact, period_end):
        """`EmailMessage` para `kind` (`NotificationKind`)."""


class EmailSender(ABC):
    """Envia un correo (en esta entrega, a la consola o a un archivo)."""

    @abstractmethod
    def send(self, message):
        """Envia `message` (`EmailMessage`)."""


class NotificationQueue(ABC):
    """Cola de las tareas de notificacion (Celery, ADR-15)."""

    @abstractmethod
    def premium_activated(self, subscription_id):
        """Encola la bienvenida. Puede fallar si el broker no responde."""
