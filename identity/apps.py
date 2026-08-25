"""Configuracion de la app `identity`."""
from django.apps import AppConfig


class IdentityConfig(AppConfig):
    """UserIdentityContext: identidad y perfil del usuario."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "identity"
