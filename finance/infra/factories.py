"""Fabricas de adaptadores de `finance` (anillo externo).

`CategorizerFactory` es el Factory Method del entregable: resuelve que
implementacion de `Categorizer` usar segun la configuracion, y concentra esa
decision en un solo punto.

Su valor se ve en el principio abierto/cerrado. Agregar un proveedor nuevo cuesta
una clase en `categorizers.py` y una entrada en el mapa de abajo; ni
`TransactionService`, ni las views, ni los serializers cambian una linea. Y la
conmutacion es de entorno, no de codigo:

    CATEGORIZER_PROVIDER=MOCK python manage.py runserver

cambia el comportamiento del sistema sin tocar un archivo. Esto tambien evita
consumir cuota de inferencia durante el desarrollo, que es la restriccion HC-06
de Phase 0.

Esta capa si puede importar Django: es infraestructura, no dominio.
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from finance.infra.categorizers import (
    AICategorizer,
    MockCategorizer,
    RuleBasedCategorizer,
)

PROVIDER_RULE = "RULE"
PROVIDER_AI = "AI"
PROVIDER_MOCK = "MOCK"


def _build_rule_based():
    """Construye el categorizador determinista."""
    return RuleBasedCategorizer()


def _build_ai():
    """Construye el categorizador de proveedor externo, con respaldo.

    `client=None` es lo correcto en esta entrega: no hay cliente concreto de
    proveedor y la clase opera en modo degradado, delegando en el respaldo
    determinista. El dia que exista, se inyecta aqui y nada mas cambia.
    """
    return AICategorizer(client=None, fallback=RuleBasedCategorizer())


def _build_mock():
    """Construye el categorizador de pruebas."""
    return MockCategorizer()


# El mapa es la unica tabla de despacho. Agregar un proveedor es agregar una fila.
PROVIDER_BUILDERS = {
    PROVIDER_RULE: _build_rule_based,
    PROVIDER_AI: _build_ai,
    PROVIDER_MOCK: _build_mock,
}


class CategorizerFactory:
    """Resuelve la implementacion de `Categorizer` segun la configuracion."""

    @staticmethod
    def available_providers():
        """Devuelve los valores validos de `CATEGORIZER_PROVIDER`.

        Existe para que el mensaje de error y los tests consuman una sola fuente
        en lugar de repetir la lista.
        """
        return tuple(PROVIDER_BUILDERS)

    @staticmethod
    def get_categorizer():
        """Instancia el categorizador configurado.

        Un valor desconocido **falla ruidosamente** con `ImproperlyConfigured`. En
        una aplicacion financiera, degradar en silencio a un categorizador
        distinto del configurado es peor que no arrancar: una errata en la
        configuracion de produccion pasaria inadvertida durante meses y nadie
        sabria con que criterio se clasificaron las transacciones.

        Devuelve una instancia nueva en cada llamada. Los categorizadores no
        tienen estado mutable, asi que crear uno por peticion es barato y evita
        cualquier problema de concurrencia; no hay memoizacion ni singleton.
        """
        raw_provider = getattr(settings, "CATEGORIZER_PROVIDER", PROVIDER_RULE)
        provider = str(raw_provider).strip().upper()

        try:
            builder = PROVIDER_BUILDERS[provider]
        except KeyError as exc:
            valid = ", ".join(CategorizerFactory.available_providers())
            raise ImproperlyConfigured(
                f"CATEGORIZER_PROVIDER tiene el valor {raw_provider!r}, que no "
                f"corresponde a ningun proveedor conocido. Valores validos: "
                f"{valid}."
            ) from exc

        return builder()
