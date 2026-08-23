"""Configuracion de la app `core`."""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    """App transversal: value objects, excepciones y utilidades compartidas."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
