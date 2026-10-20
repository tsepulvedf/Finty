"""Convertidores de ruta con las mismas expresiones que el monolito.

- `lookup`: `[^/.]+`, la expresion por defecto de `DefaultRouter` de DRF para
  `accounts/{pk}/` y `categories/{pk}/`. Un valor que no es UUID llega a la vista
  y responde 404, como en el monolito.
- `django_uuid`: el convertidor `<uuid:pk>` de Django, que solo acepta UUID en
  minusculas. El de Werkzeug acepta mayusculas; con el, `/transactions/{ID}/`
  responderia distinto que el monolito.
"""
from uuid import UUID

from werkzeug.routing import BaseConverter


class LookupConverter(BaseConverter):
    """Segmento sin `/` ni `.`, entregado como cadena."""

    regex = r"[^/.]+"


class DjangoUUIDConverter(BaseConverter):
    """UUID canonico en minusculas, entregado como `UUID`."""

    regex = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

    def to_python(self, value):
        return UUID(value)

    def to_url(self, value):
        return str(value)


CONVERTERS = {"lookup": LookupConverter, "django_uuid": DjangoUUIDConverter}
