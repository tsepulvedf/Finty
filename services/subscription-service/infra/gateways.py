"""Implementaciones de `PaymentGateway` (ADR-14).

En E2-M6a solo existe `MockPaymentGateway`. `WompiSandboxGateway` llega en E2-M6b.
"""
from domain.interfaces import PaymentGateway, PaymentOutcome
from domain.value_objects import PaymentStatus


class MockPaymentGateway(PaymentGateway):
    """Aprueba siempre, de forma sincrona y determinista. Nunca sale a la red.

    Es el gateway de la demo y de la suite de contrato. Los pagos rechazados y con
    error se prueban con dobles en los tests del servicio.
    """

    name = "mock"

    def submit(self, request):
        return PaymentOutcome(PaymentStatus.APPROVED, f"mock aprobo {request.reference}")
