"""Serializers del contrato REST de `identity` (anillo externo).

Responsabilidad exclusivamente sintactica: formato, tipos, longitudes y campos
requeridos. Ninguna regla de negocio y ningun `validate_*()` que consulte la
base de datos: que un email ya este registrado lo decide `ProfileService`, no un
serializer (RULES.md, regla 4).

Los serializers de entrada son `Serializer` plano y no `ModelSerializer` a
proposito: el contrato de la API no debe quedar atado a la forma de la tabla.
"""
from rest_framework import serializers


class RegisterInputSerializer(serializers.Serializer):
    """Datos de entrada del registro de un usuario nuevo."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    display_name = serializers.CharField(max_length=120)


class LoginInputSerializer(serializers.Serializer):
    """Credenciales de acceso."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class ProfileInputSerializer(serializers.Serializer):
    """Datos de entrada de la actualizacion de perfil.

    Ambos campos son opcionales para permitir actualizacion parcial, pero al
    menos uno debe venir: un PUT sin campos es una peticion malformada.
    """

    display_name = serializers.CharField(max_length=120, required=False)
    preferred_currency = serializers.CharField(
        min_length=3, max_length=3, required=False
    )

    def validate(self, attrs):
        """Exige al menos un campo. Regla de forma, no de negocio."""
        if not attrs:
            raise serializers.ValidationError(
                "Envia al menos 'display_name' o 'preferred_currency'."
            )
        return attrs


class ProfileOutputSerializer(serializers.Serializer):
    """Representacion de salida de un `UserProfile`."""

    user_id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    display_name = serializers.CharField(read_only=True)
    preferred_currency = serializers.CharField(read_only=True)
    onboarding_completed = serializers.BooleanField(read_only=True)


class AuthOutputSerializer(serializers.Serializer):
    """Representacion de salida de un registro o un login exitoso."""

    user_id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    token = serializers.CharField(read_only=True)
