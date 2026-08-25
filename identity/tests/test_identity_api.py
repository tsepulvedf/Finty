"""Tests del contrato REST de identidad.

Verifican los codigos HTTP del handler global: un `BusinessRuleError` sale como
409, un `ValidationError` como 422 y un `AuthenticationError` como 401, sin que
ninguna view traduzca nada a mano.
"""
import pytest
from rest_framework.test import APIClient

from identity.models import UserProfile
from identity.services import ProfileService

pytestmark = pytest.mark.django_db

PASSWORD = "Contrasena-Segura-2026"

REGISTER_URL = "/api/v1/auth/register/"
LOGIN_URL = "/api/v1/auth/login/"
PROFILE_URL = "/api/v1/profile/"


@pytest.fixture
def client():
    """Cliente HTTP sin autenticar."""
    return APIClient()


@pytest.fixture
def registered(client):
    """Usuario registrado a traves del endpoint; devuelve el cuerpo de la respuesta."""
    response = client.post(
        REGISTER_URL,
        {"email": "ana@finty.co", "password": PASSWORD, "display_name": "Ana Restrepo"},
        format="json",
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def auth_client(registered):
    """Cliente autenticado con el token del usuario registrado."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {registered['token']}")
    return client


class TestRegistro:
    """`POST /api/v1/auth/register/`."""

    def test_devuelve_201_con_token(self, registered):
        assert registered["email"] == "ana@finty.co"
        assert registered["token"]
        assert registered["user_id"]

    def test_no_devuelve_la_contrasena(self, registered):
        assert "password" not in registered

    def test_crea_el_perfil(self, registered):
        profile = UserProfile.objects.get(user_id=registered["user_id"])
        assert profile.display_name == "Ana Restrepo"

    def test_duplicado_devuelve_409(self, client, registered):
        response = client.post(
            REGISTER_URL,
            {"email": "ana@finty.co", "password": PASSWORD, "display_name": "Otra Ana"},
            format="json",
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_already_registered"

    def test_contrasena_debil_devuelve_422(self, client):
        response = client.post(
            REGISTER_URL,
            {"email": "nueva@finty.co", "password": "123", "display_name": "Nueva"},
            format="json",
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "weak_password"

    def test_email_con_formato_invalido_devuelve_400(self, client):
        response = client.post(
            REGISTER_URL,
            {"email": "no-es-un-email", "password": PASSWORD, "display_name": "Nueva"},
            format="json",
        )

        assert response.status_code == 400

    def test_campos_faltantes_devuelve_400(self, client):
        response = client.post(REGISTER_URL, {"email": "nueva@finty.co"}, format="json")
        assert response.status_code == 400


class TestLogin:
    """`POST /api/v1/auth/login/`."""

    def test_credenciales_correctas_devuelven_200(self, client, registered):
        response = client.post(
            LOGIN_URL, {"email": "ana@finty.co", "password": PASSWORD}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["token"] == registered["token"]

    def test_contrasena_incorrecta_devuelve_401(self, client, registered):
        response = client.post(
            LOGIN_URL,
            {"email": "ana@finty.co", "password": "otra-contrasena-cualquiera"},
            format="json",
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_email_inexistente_devuelve_401(self, client):
        response = client.post(
            LOGIN_URL, {"email": "fantasma@finty.co", "password": PASSWORD}, format="json"
        )

        assert response.status_code == 401

    def test_no_revela_si_el_email_existe(self, client, registered):
        inexistente = client.post(
            LOGIN_URL, {"email": "fantasma@finty.co", "password": PASSWORD}, format="json"
        )
        incorrecta = client.post(
            LOGIN_URL,
            {"email": "ana@finty.co", "password": "otra-contrasena-cualquiera"},
            format="json",
        )

        assert inexistente.json() == incorrecta.json()


class TestPerfilLectura:
    """`GET /api/v1/profile/`."""

    def test_sin_token_devuelve_401(self, client):
        assert client.get(PROFILE_URL).status_code == 401

    def test_con_token_invalido_devuelve_401(self, client):
        client.credentials(HTTP_AUTHORIZATION="Token no-es-un-token")
        assert client.get(PROFILE_URL).status_code == 401

    def test_con_token_devuelve_200(self, auth_client, registered):
        response = auth_client.get(PROFILE_URL)

        assert response.status_code == 200
        assert response.json() == {
            "user_id": registered["user_id"],
            "email": "ana@finty.co",
            "display_name": "Ana Restrepo",
            "preferred_currency": "COP",
            "onboarding_completed": False,
        }


class TestPerfilEscritura:
    """`PUT /api/v1/profile/`."""

    def test_actualiza_y_devuelve_el_perfil(self, auth_client):
        response = auth_client.put(
            PROFILE_URL,
            {"display_name": "Ana R.", "preferred_currency": "USD"},
            format="json",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["display_name"] == "Ana R."
        assert body["preferred_currency"] == "USD"
        assert body["onboarding_completed"] is True

    def test_actualizacion_parcial(self, auth_client):
        response = auth_client.put(
            PROFILE_URL, {"preferred_currency": "EUR"}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["preferred_currency"] == "EUR"
        assert response.json()["display_name"] == "Ana Restrepo"

    def test_el_cambio_se_ve_en_el_get(self, auth_client):
        auth_client.put(PROFILE_URL, {"display_name": "Ana R."}, format="json")

        assert auth_client.get(PROFILE_URL).json()["display_name"] == "Ana R."

    def test_moneda_invalida_devuelve_422(self, auth_client):
        response = auth_client.put(
            PROFILE_URL, {"preferred_currency": "123"}, format="json"
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_moneda_de_longitud_incorrecta_devuelve_400(self, auth_client):
        response = auth_client.put(
            PROFILE_URL, {"preferred_currency": "PESO"}, format="json"
        )

        assert response.status_code == 400

    def test_cuerpo_vacio_devuelve_400(self, auth_client):
        assert auth_client.put(PROFILE_URL, {}, format="json").status_code == 400

    def test_sin_token_devuelve_401(self, client):
        response = client.put(PROFILE_URL, {"display_name": "Ana R."}, format="json")
        assert response.status_code == 401


class TestFlujoCompleto:
    """Recorrido de extremo a extremo: registro, login, lectura y escritura."""

    def test_registro_login_perfil(self, client):
        registro = client.post(
            REGISTER_URL,
            {"email": "juan@finty.co", "password": PASSWORD, "display_name": "Juan P."},
            format="json",
        )
        assert registro.status_code == 201

        login = client.post(
            LOGIN_URL, {"email": "juan@finty.co", "password": PASSWORD}, format="json"
        )
        assert login.status_code == 200

        autenticado = APIClient()
        autenticado.credentials(HTTP_AUTHORIZATION=f"Token {login.json()['token']}")

        assert autenticado.get(PROFILE_URL).status_code == 200

        actualizado = autenticado.put(
            PROFILE_URL, {"preferred_currency": "usd"}, format="json"
        )
        assert actualizado.status_code == 200
        assert actualizado.json()["preferred_currency"] == "USD"

    def test_cada_usuario_solo_ve_su_perfil(self, client):
        """INV-01/INV-03: el perfil se resuelve desde `request.user`, no desde la URL."""
        service = ProfileService()
        _, token_ana = service.register_user("ana@finty.co", PASSWORD, "Ana")
        _, token_juan = service.register_user("juan@finty.co", PASSWORD, "Juan")

        cliente_ana = APIClient()
        cliente_ana.credentials(HTTP_AUTHORIZATION=f"Token {token_ana}")
        cliente_juan = APIClient()
        cliente_juan.credentials(HTTP_AUTHORIZATION=f"Token {token_juan}")

        assert cliente_ana.get(PROFILE_URL).json()["email"] == "ana@finty.co"
        assert cliente_juan.get(PROFILE_URL).json()["email"] == "juan@finty.co"
