"""Dobles de los puertos del reporte mensual (E2-M7)."""
from domain.interfaces import ReportQueue, ReportRenderer


class MemoryReportQueue(ReportQueue):
    """Guarda los ids encolados; con `down`, falla como un broker caido."""

    def __init__(self):
        self.enqueued = []
        self.down = False

    def enqueue(self, report_id):
        if self.down:
            raise ConnectionError("broker caido")
        self.enqueued.append(report_id)


class BrokenRenderer(ReportRenderer):
    """Un renderizador que no puede armar el archivo."""

    media_type = "text/plain"
    extension = "txt"

    def render(self, report, language):
        raise ValueError("no se pudo armar")

    def filename(self, period, language):
        return "x.txt"
