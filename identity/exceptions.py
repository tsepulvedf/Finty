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
