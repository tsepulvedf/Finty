"""Errores de configuracion de `finance-service`."""


class ConfigurationError(RuntimeError):
    """La configuracion del servicio es invalida.

    Equivale al `ImproperlyConfigured` de Django. No es un `DomainError`: no la
    provoca el usuario sino quien desplego el servicio, y por eso revienta en
    lugar de traducirse a un 4xx.
    """
