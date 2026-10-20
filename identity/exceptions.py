"""Excepciones del contexto `identity`.

Modulo plano, sin carpeta `domain/`: en el mapa de bounded contexts
(ARCHITECTURE.md 3) `UserIdentityContext` es un contexto **Generic**, no Core.
No tiene entidades de dominio propias ni reglas que justifiquen un anillo de
dominio completo; su unica pieza conceptual son estas excepciones. `finance`, que
si es el contexto Core, tiene su `domain/` con value objects, logica y builders.

Python puro: ninguna de estas clases importa Django. La traduccion a HTTP la
hace `core/api/exception_handler.py` a partir de la superclase de cada una.
"""
from core.domain.exceptions import (
    AuthenticationError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)


class EmailAlreadyRegisteredError(BusinessRuleError):
    """El email ya pertenece a una cuenta existente (INV-10). HTTP 409."""

    default_code = "email_already_registered"
    default_message = "Ya existe una cuenta registrada con ese email."


class WeakPasswordError(ValidationError):
    """La contrasena no cumple las politicas de seguridad. HTTP 422."""

    default_code = "weak_password"
    default_message = "La contrasena no cumple los requisitos de seguridad."


class ProfileNotFoundError(NotFoundError):
    """El usuario no tiene perfil asociado. HTTP 404."""

    default_code = "profile_not_found"
    default_message = "El usuario no tiene un perfil asociado."


class InvalidCredentialsError(AuthenticationError):
    """Credenciales invalidas. HTTP 401.

    El mensaje es deliberadamente generico e identico tanto si el email no
    existe como si la contrasena es incorrecta: distinguir ambos casos revelaria
    que correos estan registrados en Finty.
    """

    default_code = "invalid_credentials"
    default_message = "El email o la contrasena son incorrectos."


# --- Verificacion del token para el Gateway (ADR-09) -------------------------
#
# Una clase por cada rechazo que distinguia `TokenAuthentication` de DRF, con su
# mismo texto. El `code` es lo que el endpoint interno le devuelve a Nginx en
# `X-Auth-Error`, y Nginx lo traduce al mismo `{"detail": ...}` que respondia
# DRF, para que el cliente no note que la autenticacion se movio al Gateway.


class MissingCredentialsError(AuthenticationError):
    """No hay cabecera `Authorization` con esquema `Token`. HTTP 401."""

    default_code = "not_authenticated"
    default_message = "Las credenciales de autenticación no se proveyeron."


class TokenHeaderWithoutCredentialsError(AuthenticationError):
    """`Authorization: Token` sin la clave. HTTP 401."""

    default_code = "token_header_without_credentials"
    default_message = "Cabecera token inválida. Las credenciales no fueron suministradas."


class TokenHeaderWithSpacesError(AuthenticationError):
    """La clave del token contiene espacios. HTTP 401."""

    default_code = "token_header_with_spaces"
    default_message = "Cabecera token inválida. La cadena token no debe contener espacios."


class TokenHeaderInvalidCharactersError(AuthenticationError):
    """La clave del token no es texto valido. HTTP 401."""

    default_code = "token_header_invalid_characters"
    default_message = (
        "Cabecera token inválida. La cadena token no debe contener caracteres inválidos."
    )


class InvalidTokenError(AuthenticationError):
    """La clave no corresponde a ningun token emitido. HTTP 401."""

    default_code = "invalid_token"
    default_message = "Token inválido."


class InactiveUserError(AuthenticationError):
    """El token es de un usuario desactivado. HTTP 401."""

    default_code = "inactive_user"
    default_message = "Usuario inactivo o borrado."
