"""Rate limiting del Gateway (D-17): la respuesta 429 tiene la forma del contrato.

Marcados `throttle`: agotan las cuotas de `limit_req` (y la de login cuenta
contra la cuota anonima de DRF), asi que solo corren con `CONTRACT_THROTTLE=1`,
aparte de la suite principal:

    CONTRACT_BASE_URL=http://localhost CONTRACT_THROTTLE=1 python -m pytest tests/contract -m throttle
"""
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import Client
from helpers import CATEGORIES, THROTTLED

pytestmark = pytest.mark.throttle


def burst(client, method, path, count, body=None):
    with ThreadPoolExecutor(max_workers=32) as pool:
        futures = [pool.submit(client.request, method, path, body) for _ in range(count)]
        return [future.result() for future in futures]


def test_la_zona_general_responde_429_en_json(base_url, ana):
    client = Client(base_url, ana.client.token, retry_throttled=False)

    responses = burst(client, "GET", CATEGORIES, 200)

    throttled = [r for r in responses if r.status == 429]
    assert throttled, "200 peticiones simultaneas deberian superar la rafaga de 50"
    assert all(r.json == THROTTLED for r in throttled)
    assert all(r.header("Content-Type").startswith("application/json") for r in throttled)
    assert {r.status for r in responses} <= {200, 429}


def test_la_zona_de_acceso_es_mas_estricta(base_url):
    client = Client(base_url, retry_throttled=False)
    credentials = {"email": "nadie@finty.co", "password": "incorrecta"}

    responses = burst(client, "POST", "/api/v1/auth/login/", 15, credentials)

    throttled = [r for r in responses if r.status == 429]
    assert len(throttled) >= 5, "15 intentos superan la rafaga de 10 de finty_auth"
    assert all(r.json == THROTTLED for r in throttled)
