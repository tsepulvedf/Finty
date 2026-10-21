"""`PaymentGatewayFactory`: Factory Method de la pasarela de pagos (ADR-14).

Mismo patron que `CategorizerFactory` (§6.1): una tabla de despacho, una variable
de entorno (`PAYMENT_GATEWAY`, insensible a mayusculas, `MOCK` por defecto) y un
error ruidoso ante un valor desconocido. Agregar `WOMPI` en E2-M6b es agregar una
fila al mapa; `SubscriptionService` no cambia.

`create_app()` la llama al construir la aplicacion, asi que un valor invalido
impide arrancar el servicio en lugar de fallar en el primer checkout.
"""
import os

from infra.configuration import ConfigurationError
from infra.gateways import MockPaymentGateway

GATEWAY_ENV_VAR = "PAYMENT_GATEWAY"
GATEWAY_MOCK = "MOCK"

GATEWAY_BUILDERS = {
    GATEWAY_MOCK: MockPaymentGateway,
}


class PaymentGatewayFactory:
    @staticmethod
    def available_gateways():
        return tuple(GATEWAY_BUILDERS)

    @staticmethod
    def get_gateway(environ=os.environ):
        raw = environ.get(GATEWAY_ENV_VAR, GATEWAY_MOCK)
        key = str(raw).strip().upper()
        try:
            builder = GATEWAY_BUILDERS[key]
        except KeyError as exc:
            valid = ", ".join(PaymentGatewayFactory.available_gateways())
            raise ConfigurationError(
                f"PAYMENT_GATEWAY tiene el valor {raw!r}, que no corresponde a ninguna "
                f"pasarela conocida. Valores validos: {valid}."
            ) from exc
        return builder()
