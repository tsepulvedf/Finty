"""Persistencia del contexto `identity` (anillo externo).

Modelos anemicos por ADR-03: solo campos, `Meta`, constraints, relaciones y
`__str__`. Ningun metodo de negocio.
"""
from uuid import uuid4

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Manager de `User` basado en email en lugar de username."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        """Crea un usuario normal identificado por su email."""
        if not email:
            raise ValueError("El email es obligatorio.")
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Crea un superusuario identificado por su email."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superusuario debe tener is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Usuario de Finty. El email es el identificador de acceso (INV-10)."""

    username = None

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.email


class UserProfile(models.Model):
    """Preferencias y datos de presentacion del usuario.

    Excepcion deliberada a la convencion de UUID como clave primaria: la clave
    de `UserProfile` **es** la clave de su `User`. El perfil no tiene identidad
    propia, existe solo como extension del usuario, y una clave sustituta
    adicional seria redundante y permitiria estados imposibles (dos perfiles
    para un mismo usuario).

    Modelo anemico (ADR-03): lo crea `ProfileService` dentro de la misma
    transaccion que el `User`, nunca un signal `post_save`.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        primary_key=True,
    )
    display_name = models.CharField(max_length=120)
    preferred_currency = models.CharField(max_length=3, default="COP")
    onboarding_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perfil de usuario"
        verbose_name_plural = "perfiles de usuario"

    def __str__(self):
        return f"{self.display_name} ({self.user_id})"
