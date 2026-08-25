"""Test de humo del endpoint de salud del API Gateway."""
from rest_framework.test import APIClient


def test_health_endpoint_responde_ok():
    """`/api/v1/health/` responde 200 y el contrato esperado sin autenticacion."""
    response = APIClient().get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "v1"}
