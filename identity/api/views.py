"""Views del contrato REST de `identity` (anillo externo).

Cada view hace exactamente cuatro cosas: validar con el serializer, llamar al
service, serializar la salida y elegir el codigo HTTP. Ningun calculo, ningun
`if` sobre reglas de negocio y ningun `try/except` alrededor del service: las
excepciones de dominio las traduce el handler global (CLAUDE.md, regla 3).
"""
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from identity.api.serializers import (
    AuthOutputSerializer,
    LoginInputSerializer,
    ProfileInputSerializer,
    ProfileOutputSerializer,
    RegisterInputSerializer,
)
from identity.services import ProfileService


def _auth_payload(user, token_key):
    """Arma la representacion de salida de un registro o login."""
    return AuthOutputSerializer(
        {"user_id": user.id, "email": user.email, "token": token_key}
    ).data


class RegisterAPIView(APIView):
    """`POST /api/v1/auth/register/` — alta de un usuario y su perfil."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        """Registra al usuario y devuelve su token de acceso."""
        serializer = RegisterInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user, token_key = ProfileService().register_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            display_name=serializer.validated_data["display_name"],
        )
        return Response(_auth_payload(user, token_key), status=status.HTTP_201_CREATED)


class LoginAPIView(APIView):
    """`POST /api/v1/auth/login/` — emision de token por credenciales."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        """Autentica al usuario y devuelve su token de acceso."""
        serializer = LoginInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user, token_key = ProfileService().authenticate_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        return Response(_auth_payload(user, token_key), status=status.HTTP_200_OK)


class ProfileAPIView(APIView):
    """`GET`/`PUT /api/v1/profile/` — perfil del usuario autenticado.

    Hereda el `IsAuthenticated` global de DRF, que materializa INV-01.
    """

    def get(self, request):
        """Devuelve el perfil del usuario autenticado."""
        profile = ProfileService().get_profile(request.user)
        return Response(ProfileOutputSerializer(profile).data, status=status.HTTP_200_OK)

    def put(self, request):
        """Actualiza parcialmente el perfil del usuario autenticado."""
        serializer = ProfileInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = ProfileService().complete_profile(
            request.user, **serializer.validated_data
        )
        return Response(ProfileOutputSerializer(profile).data, status=status.HTTP_200_OK)
