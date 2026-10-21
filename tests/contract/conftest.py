"""Suite de contrato de `/api/v1/` para los bloques finance y analytics (A-20).

Caja negra: solo habla HTTP con `CONTRACT_BASE_URL` (por ejemplo,
`http://localhost` o la IP elastica de la EC2), a traves del Gateway. No sabe si
detras responde Django o `finance-service`, y por eso es la prueba de la
conmutacion: tiene que dar el mismo resultado antes y despues (ADR-08).

    CONTRACT_BASE_URL=http://localhost python -m pytest tests/contract -v

Crea sus propios usuarios con `/api/v1/auth/register/` y `/api/v1/auth/login/`,
con emails aleatorios, asi que puede correr contra un stack con datos. Solo usa
la biblioteca estandar y pytest.

**Cuotas.** El cliente reintenta las respuestas 429 de `limit_req`: una rafaga
de la propia suite no es un fallo del contrato. Los tests que si verifican el
429 estan marcados `throttle` y solo corren con `CONTRACT_THROTTLE=1`. Cada
corrida hace 6 peticiones anonimas (registro y login de tres usuarios), que
cuentan contra la cuota anonima de DRF (60/h por IP).
"""
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

import pytest

BASE_URL_ENV = "CONTRACT_BASE_URL"
THROTTLE_ENV = "CONTRACT_THROTTLE"
PASSWORD = "Contrasena-Contrato-2026"

THROTTLE_RETRIES = 20
THROTTLE_BACKOFF_SECONDS = 0.25


@dataclass
class Response:
    """Respuesta HTTP ya leida."""

    status: int
    headers: dict
    text: str

    @property
    def json(self):
        return json.loads(self.text) if self.text else None

    def header(self, name):
        return self.headers.get(name.lower())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Las redirecciones son parte del contrato: se observan, no se siguen."""

    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


class Client:
    """Cliente HTTP minimo contra el Gateway."""

    def __init__(self, base_url, token=None, retry_throttled=True):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.retry_throttled = retry_throttled

    def with_token(self, token):
        return Client(self.base_url, token, self.retry_throttled)

    def request(self, method, path, body=None, raw=None, content_type=None, headers=None):
        data = raw if raw is not None else (
            json.dumps(body).encode("utf-8") if body is not None else None
        )
        all_headers = dict(headers or {})
        if self.token and "Authorization" not in all_headers:
            all_headers["Authorization"] = f"Token {self.token}"
        if data is not None:
            all_headers.setdefault("Content-Type", content_type or "application/json")

        for _ in range(THROTTLE_RETRIES):
            response = self._send(method, path, data, all_headers)
            if response.status != 429 or not self.retry_throttled:
                return response
            time.sleep(THROTTLE_BACKOFF_SECONDS)
        return response

    def _send(self, method, path, data, headers):
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method, headers=headers
        )
        try:
            with _OPENER.open(request, timeout=30) as raw:
                return Response(raw.status, _lower(raw.headers), raw.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return Response(error.code, _lower(error.headers), error.read().decode("utf-8"))

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, body=None, **kwargs):
        return self.request("POST", path, body=body, **kwargs)

    def put(self, path, body=None, **kwargs):
        return self.request("PUT", path, body=body, **kwargs)

    def patch(self, path, body=None, **kwargs):
        return self.request("PATCH", path, body=body, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)


def _lower(headers):
    return {name.lower(): value for name, value in headers.items()}


@dataclass
class User:
    """Usuario de la suite: su cliente autenticado y su identidad."""

    client: Client
    user_id: str
    email: str


def unique(prefix):
    """Nombre unico para que las corridas no choquen entre si."""
    return f"{prefix} {uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def base_url():
    value = os.environ.get(BASE_URL_ENV)
    if not value:
        pytest.fail(f"Falta {BASE_URL_ENV}, por ejemplo http://localhost")
    return value.rstrip("/")


@pytest.fixture(scope="session")
def host(base_url):
    """`esquema://host[:puerto]` con el que el servidor arma los enlaces."""
    parts = urlsplit(base_url)
    return f"{parts.scheme}://{parts.netloc}"


@pytest.fixture(scope="session")
def anonimo(base_url):
    return Client(base_url)


def _register_and_login(anonimo, name):
    email = f"contrato-{name}-{uuid.uuid4().hex[:10]}@finty.co"
    registro = anonimo.post(
        "/api/v1/auth/register/",
        {"email": email, "password": PASSWORD, "display_name": name},
    )
    assert registro.status == 201, registro.text
    login = anonimo.post("/api/v1/auth/login/", {"email": email, "password": PASSWORD})
    assert login.status == 200, login.text
    assert login.json["user_id"] == registro.json["user_id"]
    return User(anonimo.with_token(login.json["token"]), login.json["user_id"], email)


@pytest.fixture(scope="session")
def ana(anonimo):
    return _register_and_login(anonimo, "ana")


@pytest.fixture(scope="session")
def juan(anonimo):
    return _register_and_login(anonimo, "juan")


@pytest.fixture(scope="session")
def eva(anonimo):
    """Tercer usuario: el k-anonimato del resumen publico necesita k = 3."""
    return _register_and_login(anonimo, "eva")


def pytest_collection_modifyitems(config, items):
    if os.environ.get(THROTTLE_ENV) == "1":
        return
    skip = pytest.mark.skip(reason=f"agota cuotas; activar con {THROTTLE_ENV}=1")
    for item in items:
        if "throttle" in item.keywords:
            item.add_marker(skip)
