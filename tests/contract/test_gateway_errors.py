"""Errores propios del Gateway cuando un servicio no responde (E2-M9c, ADR-09).

Nginx no deja pasar el 502 en HTML ni el 500 de `auth_request`: responde 503 con
la misma forma que sus 401 y 429, un `code` estable y `X-Finty-Route` con el
bloque que fallo. Tampoco deja la peticion colgada: con el contenedor detenido,
la respuesta llega en pocos segundos (timeouts cortos y DNS en tiempo de
ejecucion, sin reiniciar Nginx).

Opcionales, cada uno con su servicio detenido y corridos aparte:

    docker compose stop django
    CONTRACT_IDENTITY_DOWN=1 CONTRACT_BASE_URL=http://localhost python -m pytest test_gateway_errors.py -v

    docker compose stop subscription-service
    CONTRACT_SUBSCRIPTION_DOWN=1 CONTRACT_BASE_URL=http://localhost python -m pytest test_gateway_errors.py -v

    docker compose stop analytics-service
    CONTRACT_ANALYTICS_DOWN=1 CONTRACT_BASE_URL=http://localhost python -m pytest test_gateway_errors.py -v

Con Django detenido no se pueden crear usuarios: esos tests usan un token
cualquiera, que nadie alcanza a verificar.
"""
import os
import time

import pytest

IDENTITY_DOWN_ENV = "CONTRACT_IDENTITY_DOWN"
SUBSCRIPTION_DOWN_ENV = "CONTRACT_SUBSCRIPTION_DOWN"
ANALYTICS_DOWN_ENV = "CONTRACT_ANALYTICS_DOWN"

UNAVAILABLE = {
    "detail": "El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.",
    "code": "service_unavailable",
}
# Con el contenedor detenido, el Gateway responde dentro de sus timeouts (2 s de
# conexion o de DNS), nunca tras el minuto por defecto de Nginx.
MAX_SECONDS = 5

AUTHENTICATED_BLOCKS = [
    ("/api/v1/accounts/", "finance"),
    ("/api/v1/analytics/dashboard/", "analytics"),
    ("/api/v1/recommendations/", "recommendation"),
    ("/api/v1/subscriptions/plans/", "subscription"),
]


def only_with(env, what):
    return pytest.mark.skipif(os.environ.get(env) != "1", reason=f"activar con {env}=1 y {what} detenido")


def timed(client, path):
    start = time.monotonic()
    response = client.get(path)
    return response, time.monotonic() - start


def assert_unavailable(response, elapsed, route):
    assert response.status == 503, response.text
    assert response.header("Content-Type").startswith("application/json")
    assert response.json == UNAVAILABLE
    assert response.header("X-Finty-Route") == route
    assert elapsed < MAX_SECONDS, f"{elapsed:.1f} s"


@only_with(IDENTITY_DOWN_ENV, "django")
class TestIdentityCaido:
    """Sin Django nadie verifica el token: 503 en JSON, nunca un 500 ni la peticion sin verificar."""

    @pytest.mark.parametrize("path, route", AUTHENTICATED_BLOCKS)
    def test_lo_autenticado_responde_503(self, anonimo, path, route):
        client = anonimo.with_token("0" * 40)
        assert_unavailable(*timed(client, path), route)

    def test_las_rutas_del_monolito_responden_503(self, anonimo):
        assert_unavailable(*timed(anonimo, "/api/v1/health/"), "monolith")

    def test_el_endpoint_publico_sigue(self, anonimo):
        response = anonimo.get("/api/v1/public/spending-summary/")
        assert response.status == 200, response.text


@only_with(SUBSCRIPTION_DOWN_ENV, "subscription-service")
class TestSubscriptionCaido:
    def test_sus_rutas_responden_503(self, lucia):
        assert_unavailable(*timed(lucia.client, "/api/v1/subscriptions/me/"), "subscription")


@only_with(ANALYTICS_DOWN_ENV, "analytics-service")
class TestAnalyticsCaido:
    def test_sus_rutas_responden_503(self, lucia):
        assert_unavailable(*timed(lucia.client, "/api/v1/analytics/dashboard/"), "analytics")

    def test_el_endpoint_publico_responde_503(self, anonimo):
        assert_unavailable(*timed(anonimo, "/api/v1/public/spending-summary/"), "public")
