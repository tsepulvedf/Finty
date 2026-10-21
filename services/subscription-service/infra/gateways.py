"""Implementaciones de `PaymentGateway` (ADR-14).

`MockPaymentGateway` es la unica: Finty no integra una pasarela real (ADR-14,
C-33). El pago es una simulacion de interfaz; el backend nunca recibe datos de
tarjeta. Una pasarela real se agregaria aqui como otro adaptador del puerto, sin
tocar el dominio ni `SubscriptionService` (OCP).
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
