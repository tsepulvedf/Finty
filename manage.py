#!/usr/bin/env python
"""Utilidad de linea de comandos de Django para tareas administrativas."""
import os
import sys


def main():
    """Ejecuta la tarea administrativa solicitada."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Verifica que este instalado y que el "
            "entorno virtual este activo."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
