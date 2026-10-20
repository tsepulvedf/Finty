"""Fabricas de adaptadores de `finance-service` (anillo externo).

`CategorizerFactory` es el Factory Method del servicio: resuelve que
implementacion de `Categorizer` usar segun la configuracion, y concentra esa
decision en un solo punto. Es el mismo del monolito; solo cambia de donde lee la
configuracion: la variable de entorno `CATEGORIZER_PROVIDER` en lugar de los
settings de Django.

Su valor se ve en el principio abierto/cerrado. Agregar un proveedor nuevo cuesta
una clase en `categorizers.py` y una entrada en el mapa de abajo; ni
`TransactionService`, ni los blueprints, ni los esquemas cambian una linea. Y la
conmutacion es de entorno, no de codigo:

    CATEGORIZER_PROVIDER=MOCK gunicorn "app:create_app()"

Los categorizadores viven aqui solo hasta E2-M3, cuando pasan a
`categorization-service` (ARCHITECTURE.md 6.1).
"""
import os

from infra.categorizers import (
    AICategorizer,
    MockCategorizer,
    RuleBasedCategorizer,
)

PROVIDER_ENV_VAR = "CATEGORIZER_PROVIDER"

PROVIDER_RULE = "RULE"
PROVIDER_AI = "AI"
PROVIDER_MOCK = "MOCK"


class ConfigurationError(RuntimeError):
    """La configuracion del servicio es invalida.

    Equivale al `ImproperlyConfigured` de Django. No es un `DomainError`: no la
    provoca el usuario sino quien desplego el servicio, y por eso no se traduce a
    un 4xx sino que revienta.
    """


def _build_rule_based():
    """Construye el categorizador determinista."""
    return RuleBasedCategorizer()


def _build_ai():
    """Construye el categorizador de proveedor externo, con respaldo.

    `client=None` es lo correcto en esta entrega: no hay cliente concreto de
    proveedor y la clase opera en modo degradado, delegando en el respaldo
    determinista (D-07).
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
        """Devuelve los valores validos de `CATEGORIZER_PROVIDER`."""
        return tuple(PROVIDER_BUILDERS)

    @staticmethod
    def get_categorizer():
        """Instancia el categorizador configurado.

        Sin la variable, el proveedor es `RULE`, igual que el default de
        `settings.py` en el monolito. Un valor desconocido **falla ruidosamente**
        con `ConfigurationError`: degradar en silencio a un categorizador distinto
        del configurado dejaria pasar una errata de despliegue durante meses.

        Devuelve una instancia nueva en cada llamada; no hay memoizacion.
        """
        raw_provider = os.environ.get(PROVIDER_ENV_VAR, PROVIDER_RULE)
        provider = str(raw_provider).strip().upper()
        try:
            builder = PROVIDER_BUILDERS[provider]
        except KeyError as exc:
            valid = ", ".join(CategorizerFactory.available_providers())
            raise ConfigurationError(
                f"CATEGORIZER_PROVIDER tiene el valor {raw_provider!r}, que no "
                f"corresponde a ningun proveedor conocido. Valores validos: "
                f"{valid}."
            ) from exc
        return builder()
