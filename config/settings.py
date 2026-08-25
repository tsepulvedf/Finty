"""Configuracion del proyecto Finty.

Toda la configuracion sensible o dependiente del entorno se lee de variables de
entorno cargadas desde un archivo `.env` (ver `.env.example`). No hay valores
sensibles escritos en este archivo.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _env(name, default=None):
    """Lee una variable de entorno; falla si es obligatoria y no esta definida."""
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(
            f"Falta la variable de entorno obligatoria '{name}'. "
            f"Copia .env.example a .env y completala."
        )
    return value


def _env_bool(name, default="False"):
    """Interpreta una variable de entorno como booleano."""
    return _env(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name, default=""):
    """Interpreta una variable de entorno como lista separada por comas."""
    return [item.strip() for item in _env(name, default).split(",") if item.strip()]


# --- Seguridad -------------------------------------------------------------

SECRET_KEY = _env("SECRET_KEY")

DEBUG = _env_bool("DEBUG")

ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS")


# --- Aplicaciones ----------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "core",
    "identity",
    "finance",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # `frontend/` aloja el cliente de demostracion. Se registra como
        # directorio de plantillas solo para que Django pueda servir el archivo:
        # la plantilla no recibe contexto y no interpola ningun dato de negocio.
        # Todo lo que muestra lo pide a /api/v1/, igual que lo haria un cliente
        # externo.
        "DIRS": [BASE_DIR / "frontend"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

ASGI_APPLICATION = "config.asgi.application"


# --- Base de datos ---------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _env("DB_NAME"),
        "USER": _env("DB_USER"),
        "PASSWORD": _env("DB_PASSWORD"),
        "HOST": _env("DB_HOST"),
        "PORT": _env("DB_PORT"),
    }
}


# --- Autenticacion ---------------------------------------------------------

AUTH_USER_MODEL = "identity.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Django REST Framework -------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    # INV-01: por defecto toda operacion exige usuario autenticado.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "core.api.exception_handler.domain_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/hour",
        "user": "1000/hour",
    },
}


# --- Internacionalizacion --------------------------------------------------

LANGUAGE_CODE = "es-co"

TIME_ZONE = "America/Bogota"

USE_I18N = True

USE_TZ = True


# --- Archivos estaticos ----------------------------------------------------

STATIC_URL = "static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Finty -----------------------------------------------------------------

# Proveedor de clasificacion que resolvera CategorizerFactory (M4).
CATEGORIZER_PROVIDER = _env("CATEGORIZER_PROVIDER", "RULE")
