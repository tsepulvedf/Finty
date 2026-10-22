"""Casos de uso del contexto `identity` (anillo de Servicios).

`ProfileService` orquesta el registro, la autenticacion y la gestion del perfil.
Es la unica capa de este contexto donde vive logica: las views solo traducen a
HTTP y los serializers solo validan sintaxis (RULES.md, reglas 3 y 4).

Puede importar Django, pero traduce toda falla del framework a excepciones de
dominio antes de devolver el control: ninguna `ValidationError` de Django ni
`IntegrityError` escapa hacia la capa externa.
"""
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db import transaction as db_transaction
from rest_framework.authtoken.models import Token

from core.domain.exceptions import ValidationError
from core.domain.value_objects import validate_currency_code
from identity.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    MissingCredentialsError,
    ProfileNotFoundError,
    TokenHeaderInvalidCharactersError,
    TokenHeaderWithoutCredentialsError,
    TokenHeaderWithSpacesError,
    WeakPasswordError,
)
from identity.models import User, UserProfile

# Idiomas en que Finty le escribe al usuario (los de `settings.LANGUAGES`).
SUPPORTED_LANGUAGES = ("es", "en")
DEFAULT_LANGUAGE = "es"

# Esquema de la cabecera `Authorization`, el mismo de `TokenAuthentication`.
TOKEN_KEYWORD = b"token"
# Codificacion con la que WSGI entrega las cabeceras (`HTTP_HEADER_ENCODING`).
HEADER_ENCODING = "iso-8859-1"


class ProfileService:
    """Casos de uso de identidad: registro, autenticacion y perfil.

    No recibe dependencias por constructor porque no tiene colaboradores
    externos que intercambiar, a diferencia de `TransactionService`, que si
    recibe un `Categorizer` (ARCHITECTURE.md 6.3).
    """

    def register_user(self, email, password, display_name, language=None):
        """Registra un usuario nuevo con su perfil y devuelve `(user, token)`.

        El `User`, el `UserProfile` y el token se crean dentro de la misma
        transaccion: o queda todo o no queda nada. Un registro fallido no puede
        dejar un usuario huerfano sin perfil. `language` es el idioma activo de
        la peticion (`es-co`, `en`...): se guarda como `es` o `en`.
        """
        normalized_email = self._normalize_email(email)

        if User.objects.filter(email=normalized_email).exists():
            raise EmailAlreadyRegisteredError()

        self._validate_password(password)

        try:
            with db_transaction.atomic():
                user = User.objects.create_user(
                    email=normalized_email, password=password
                )
                UserProfile.objects.create(
                    user=user,
                    display_name=display_name.strip(),
                    language=self._supported_language(language),
                )
                token, _ = Token.objects.get_or_create(user=user)
        except IntegrityError as exc:
            # Red de seguridad ante dos registros simultaneos con el mismo
            # email: la constraint unique de INV-10 gana y la transaccion
            # revierte por completo.
            raise EmailAlreadyRegisteredError() from exc

        return user, token.key

    def authenticate_user(self, email, password):
        """Autentica al usuario y devuelve `(user, token)`.

        Email inexistente, contrasena incorrecta y usuario inactivo producen la
        misma excepcion con el mismo mensaje: cualquier diferencia permitiria
        enumerar que correos estan registrados.
        """
        normalized_email = self._normalize_email(email)

        user = authenticate(username=normalized_email, password=password)
        if user is None or not user.is_active:
            raise InvalidCredentialsError()

        token, _ = Token.objects.get_or_create(user=user)
        return user, token.key

    def get_profile(self, user):
        """Devuelve el perfil del usuario o lanza `ProfileNotFoundError`."""
        try:
            return UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist as exc:
            raise ProfileNotFoundError() from exc

    def complete_profile(self, user, display_name=None, preferred_currency=None, language=None):
        """Actualiza parcialmente el perfil y devuelve la version persistida.

        Solo se escriben los campos recibidos. El perfil se marca como
        completado cuando `display_name` y `preferred_currency` quedan ambos
        presentes y no vacios.
        """
        profile = self.get_profile(user)
        updated_fields = []

        if display_name is not None:
            cleaned_name = display_name.strip()
            if not cleaned_name:
                raise ValidationError(
                    "El nombre para mostrar no puede estar vacio."
                )
            profile.display_name = cleaned_name
            updated_fields.append("display_name")

        if preferred_currency is not None:
            profile.preferred_currency = validate_currency_code(preferred_currency)
            updated_fields.append("preferred_currency")

        if language is not None:
            profile.language = self._supported_language(language)
            updated_fields.append("language")

        if not updated_fields:
            return profile

        if not profile.onboarding_completed and self._is_complete(profile):
            profile.onboarding_completed = True
            updated_fields.append("onboarding_completed")

        # `updated_at` es auto_now, pero con update_fields solo se escribe si se
        # nombra explicitamente.
        updated_fields.append("updated_at")
        profile.save(update_fields=updated_fields)
        return profile

    @staticmethod
    def _is_complete(profile):
        """Indica si el perfil tiene los datos minimos del onboarding."""
        return bool(profile.display_name.strip()) and bool(
            profile.preferred_currency.strip()
        )

    def contact(self, user_id):
        """Datos de contacto para los correos de otros servicios (E2-M7).

        Un id inexistente, o de un usuario inactivo, responde como no encontrado.
        """
        try:
            profile = UserProfile.objects.select_related("user").get(
                user_id=user_id, user__is_active=True
            )
        except (UserProfile.DoesNotExist, DjangoValidationError, ValueError) as exc:
            raise ProfileNotFoundError() from exc
        return profile

    @staticmethod
    def _supported_language(code):
        """`en`, `en-us`... → `en`; cualquier otro (o ninguno) → `es`."""
        prefix = (code or "").split("-")[0].lower()
        return prefix if prefix in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    @staticmethod
    def _normalize_email(email):
        """Normaliza un email a minusculas y sin espacios sobrantes.

        Se normaliza la direccion completa, no solo el dominio como hace Django
        por defecto, para que INV-10 se cumpla de verdad: `Ana@finty.co` y
        `ana@finty.co` deben ser el mismo usuario.
        """
        if not isinstance(email, str):
            raise ValidationError("El email debe ser una cadena de texto.")
        return email.strip().lower()

    @staticmethod
    def _validate_password(password):
        """Aplica las politicas de contrasena de Django como regla de dominio.

        Traduce la `ValidationError` de Django a `WeakPasswordError` para que
        ninguna excepcion del framework escape de la capa de servicios.
        """
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise WeakPasswordError(" ".join(exc.messages)) from exc


class TokenVerificationService:
    """Verifica el token de una peticion en nombre del Gateway (ADR-09).

    Es la autenticacion que hacia `TokenAuthentication` de DRF en cada vista de
    `finance`, movida a un solo punto: Nginx la consulta una vez por peticion y,
    si pasa, reenvia el `user_id` al servicio en `X-User-Id`. Reproduce el orden
    y los casos de DRF, para que cada rechazo conserve su mensaje.
    """

    def verify(self, authorization_header):
        """Devuelve el `id` del usuario dueno del token, o lanza un error 401."""
        parts = (authorization_header or "").encode(HEADER_ENCODING).split()

        if not parts or parts[0].lower() != TOKEN_KEYWORD:
            raise MissingCredentialsError()
        if len(parts) == 1:
            raise TokenHeaderWithoutCredentialsError()
        if len(parts) > 2:
            raise TokenHeaderWithSpacesError()

        try:
            key = parts[1].decode()
        except UnicodeError as exc:
            raise TokenHeaderInvalidCharactersError() from exc

        token = Token.objects.select_related("user").filter(key=key).first()
        if token is None:
            raise InvalidTokenError()
        if not token.user.is_active:
            raise InactiveUserError()
        return token.user_id
