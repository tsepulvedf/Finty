"""Cliente de `GET /internal/users/<user_id>/contact/` de identity (E2-M7).

Por la red interna de Compose (`IDENTITY_URL`, por defecto `http://django:8000`),
con timeout corto. Un 404 es `ContactNotFound` (no hay a quien escribirle); la
red, un 5xx o una respuesta fuera de contrato son `ContactUnavailable`, que la
tarea reintenta. Nunca se llama desde la peticion de checkout: la activacion no
depende de identity.
"""
import json
import urllib.error
import urllib.request

from domain.interfaces import ContactDirectory, ContactNotFound, ContactUnavailable
from domain.notifications import Contact

DEFAULT_TIMEOUT_SECONDS = 2.0


class HttpContactDirectory(ContactDirectory):
    def __init__(self, base_url, timeout=DEFAULT_TIMEOUT_SECONDS):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def contact(self, user_id):
        url = f"{self._base_url}/internal/users/{user_id}/contact/"
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            return Contact(str(body["email"]), str(body.get("display_name") or ""), str(body.get("language") or ""))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ContactNotFound(str(user_id)) from exc
            raise ContactUnavailable(f"HTTP {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001 — red o forma: transitorio, se reintenta
            raise ContactUnavailable(f"{type(exc).__name__}: {exc}") from exc
