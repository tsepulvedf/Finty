"""`GET /internal/users/<user_id>/contact/` (E2-M7).

Solo para la red interna: Nginx lo bloquea desde fuera (lo verifica la suite de
contrato, `tests/contract/test_internal.py`). Aqui, la respuesta de Django.
"""
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from identity.models import User
from identity.services import ProfileService

pytestmark = pytest.mark.django_db

PASSWORD = "Contrasena-Segura-2026"


def url(user_id):
    return f"/internal/users/{user_id}/contact/"


@pytest.fixture
def ana():
    user, _ = ProfileService().register_user("Ana@Finty.co", PASSWORD, "Ana Restrepo", language="en-us")
    return user


class TestContactoInterno:
    def test_devuelve_correo_nombre_e_idioma(self, ana):
        response = APIClient().get(url(ana.id))

        assert response.status_code == 200
        assert response.json() == {"email": "ana@finty.co", "display_name": "Ana Restrepo", "language": "en"}

    def test_no_exige_token(self, ana):
        """No lleva autenticacion de DRF: la protege la red (Nginx y sin puertos)."""
        assert APIClient().get(url(ana.id)).status_code == 200

    def test_no_lo_limita_el_throttling_anonimo(self, ana):
        client = APIClient()
        assert all(client.get(url(ana.id)).status_code == 200 for _ in range(70))

    def test_usuario_inexistente_404(self):
        response = APIClient().get(url(uuid4()))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "profile_not_found"

    def test_usuario_inactivo_404(self, ana):
        User.objects.filter(pk=ana.pk).update(is_active=False)
        assert APIClient().get(url(ana.id)).status_code == 404

    def test_id_mal_formado_404(self):
        assert APIClient().get("/internal/users/no-es-un-uuid/contact/").status_code == 404

    def test_solo_admite_get(self, ana):
        assert APIClient().post(url(ana.id)).status_code == 405
