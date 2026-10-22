"""Puertos del dominio de analytics (anillo de Dominio, Python puro)."""
from abc import ABC, abstractmethod


class EventSourceUnavailable(Exception):
    """El origen de los eventos no responde. El worker espera y reintenta.

    No es un `DomainError`: no la ve ningun usuario, solo el proceso que consume.
    """


class EventSource(ABC):
    """Origen de los eventos de finance-service, con un grupo de consumidores.

    La implementacion entrega mensajes `(id, campos)` y solo los da por
    procesados cuando se confirman con `ack()`. Un mensaje leido y no confirmado
    queda pendiente y se puede recuperar con `claim_pending()`.
    """

    @abstractmethod
    def ensure_group(self):
        """Crea el grupo si no existe, leyendo el stream desde su inicio."""

    @abstractmethod
    def claim_pending(self):
        """Reclama los mensajes pendientes sin confirmar y los devuelve."""

    @abstractmethod
    def read_new(self):
        """Lee mensajes nuevos para este consumidor; puede esperar un poco."""

    @abstractmethod
    def ack(self, message_id):
        """Confirma un mensaje: ya esta aplicado en la base."""


class EntitlementsUnavailable(Exception):
    """subscription-service no respondio, o respondio fuera de contrato."""


class EntitlementsReader(ABC):
    """Consulta el derecho premium de un usuario (INV-06, D-14)."""

    @abstractmethod
    def entitlement(self, user_id):
        """`Entitlement` del usuario, o `EntitlementsUnavailable`."""


class ReportRenderer(ABC):
    """Convierte un `MonthlyReport` en un archivo, en el idioma pedido."""

    media_type = "application/octet-stream"
    extension = "bin"

    @abstractmethod
    def render(self, report, language):
        """Los bytes del archivo."""

    @abstractmethod
    def filename(self, period, language):
        """Nombre del archivo para descargarlo."""


class ReportQueue(ABC):
    """Cola donde se encarga la generacion de un reporte (Celery, ADR-15)."""

    @abstractmethod
    def enqueue(self, report_id):
        """Encola la generacion. Puede fallar si el broker no responde."""
