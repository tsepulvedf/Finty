"""Tests de la verificacion de token que consume el Gateway (ADR-09).

`TokenVerificationService` reproduce los casos de `TokenAuthentication` de DRF y
`/internal/auth/verify/` los traduce a cabeceras: 200 con `X-User-Id` o 401 con
`X-Auth-Error`, siempre sin cuerpo, porque Nginx no lee el cuerpo de una
subpeticion `auth_request`.
"""
import pytest
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from identity.exceptions import (
    InactiveUserError,
    InvalidTokenError,
    MissingCredentialsError,
    TokenHeaderInvalidCharactersError,
    TokenHeaderWithoutCredentialsError,
    TokenHeaderWithSpacesError,
)
from identity.models import User
from identity.services import TokenVerificationService

pytestmark = pytest.mark.django_db

VERIFY_URL = "/internal/auth/verify/"


@pytest.fixture
def user():
    return User.objects.create_user(email="ana@finty.co", password="Contrasena-Segura-2026")


@pytest.fixture
def token(user):
    return Token.objects.create(user=user).key


def verify(header):
    return TokenVerificationService().verify(header)


class TestServicio:
    def test_un_token_valido_devuelve_el_id_del_usuario(self, user, token):
        assert verify(f"Token {token}") == user.id

    def test_el_esquema_no_distingue_mayusculas(self, user, token):
        assert verify(f"token {token}") == user.id

    @pytest.mark.parametrize("header", ["", None, "Bearer abc", "Basic dXNlcjpwYXNz"])
    def test_sin_esquema_token_faltan_credenciales(self, header):
        with pytest.raises(MissingCredentialsError):
            verify(header)

    def test_token_sin_clave(self):
        with pytest.raises(TokenHeaderWithoutCredentialsError):
            verify("Token")

    def test_token_con_espacios(self):
        with pytest.raises(TokenHeaderWithSpacesError):
            verify("Token abc def")

    def test_token_con_bytes_que_no_son_utf8(self):
        with pytest.raises(TokenHeaderInvalidCharactersError):
            verify("Token \xff\xfe")

    def test_token_inexistente(self, token):
        with pytest.raises(InvalidTokenError):
            verify("Token " + "0" * 40)

    def test_usuario_inactivo(self, user, token):
        user.is_active = False
        user.save(update_fields=["is_active"])

        with pytest.raises(InactiveUserError):
            verify(f"Token {token}")


class TestEndpoint:
    @pytest.fixture
    def client(self):
        return APIClient()

    def test_200_con_x_user_id_y_sin_cuerpo(self, client, user, token):
        respuesta = client.get(VERIFY_URL, HTTP_AUTHORIZATION=f"Token {token}")

        assert respuesta.status_code == 200
        assert respuesta["X-User-Id"] == str(user.id)
        assert respuesta.content == b""

    @pytest.mark.parametrize(
        "header,code",
        [
            (None, "not_authenticated"),
            ("Token", "token_header_without_credentials"),
            ("Token a b", "token_header_with_spaces"),
            ("Token " + "0" * 40, "invalid_token"),
        ],
    )
    def test_401_con_el_motivo_en_x_auth_error(self, client, header, code):
        extra = {"HTTP_AUTHORIZATION": header} if header is not None else {}

        respuesta = client.get(VERIFY_URL, **extra)

        assert respuesta.status_code == 401
        assert respuesta["X-Auth-Error"] == code
        assert respuesta.content == b""
        assert "X-User-Id" not in respuesta

    def test_usuario_inactivo_da_401(self, client, user, token):
        user.is_active = False
        user.save(update_fields=["is_active"])

        respuesta = client.get(VERIFY_URL, HTTP_AUTHORIZATION=f"Token {token}")

        assert respuesta.status_code == 401
        assert respuesta["X-Auth-Error"] == "inactive_user"

    def test_no_le_aplican_los_throttles(self, client, user, token, settings):
        """El Gateway la llama en cada peticion: una cuota la cortaria sola."""
        settings.REST_FRAMEWORK = {
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {"anon": "2/hour", "user": "2/hour"},
        }
        cache.clear()

        codigos = {
            client.get(VERIFY_URL, HTTP_AUTHORIZATION=f"Token {token}").status_code
            for _ in range(5)
        }

        assert codigos == {200}

    def test_post_no_esta_permitido(self, client, token):
        """Nginx la consulta siempre con GET (`proxy_method GET`)."""
        respuesta = client.post(VERIFY_URL, HTTP_AUTHORIZATION=f"Token {token}")
        assert respuesta.status_code == 405
