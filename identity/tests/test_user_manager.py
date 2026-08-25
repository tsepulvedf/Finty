"""Tests de `UserManager`.

Cubren el manager que Django exige para un `AUTH_USER_MODEL` personalizado.

**Nada de lo que se prueba aqui es una invariante de Finty.** `create_user` y
`create_superuser` son logica de *persistencia* que el framework obliga a poner
en el manager, y los `ValueError` sobre `is_staff` e `is_superuser` son la
validacion estandar de Django sobre flags de permisos. Las reglas de negocio de
identidad viven en `ProfileService` y se prueban en `test_profile_service.py`;
confundir unas con otras llevaria a buscar reglas de dominio dentro del ORM.

La unica invariante del catalogo que asoma por aqui es INV-10 (email unico), y la
hace cumplir la constraint `unique=True` de la columna, no este manager.
"""
import pytest

from identity.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "Contrasena-Segura-2026"


class TestCrearUsuario:
    """`create_user`."""

    def test_crea_el_usuario(self):
        user = User.objects.create_user(email="ana@finty.co", password=PASSWORD)

        assert User.objects.filter(pk=user.pk).exists()
        assert user.email == "ana@finty.co"

    def test_sin_email_lanza_value_error(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password=PASSWORD)

    def test_con_email_none_lanza_value_error(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email=None, password=PASSWORD)

    def test_normaliza_el_dominio_del_email(self):
        """`normalize_email` de Django pasa el dominio a minusculas."""
        user = User.objects.create_user(email="Ana@FINTY.CO", password=PASSWORD)

        assert user.email.endswith("@finty.co")

    def test_la_contrasena_queda_hasheada(self):
        user = User.objects.create_user(email="ana@finty.co", password=PASSWORD)

        assert user.password != PASSWORD
        assert user.check_password(PASSWORD)

    def test_no_es_staff_ni_superusuario(self):
        user = User.objects.create_user(email="ana@finty.co", password=PASSWORD)

        assert user.is_staff is False
        assert user.is_superuser is False

    def test_nace_activo(self):
        assert User.objects.create_user(email="ana@finty.co", password=PASSWORD).is_active

    def test_acepta_campos_adicionales(self):
        user = User.objects.create_user(
            email="ana@finty.co", password=PASSWORD, first_name="Ana"
        )

        assert user.first_name == "Ana"

    def test_sin_contrasena_no_queda_utilizable(self):
        """Un usuario sin contrasena no puede autenticarse."""
        user = User.objects.create_user(email="ana@finty.co")

        assert not user.check_password("")


class TestCrearSuperusuario:
    """`create_superuser`."""

    def test_deja_los_dos_flags_en_true(self):
        admin = User.objects.create_superuser(
            email="admin@finty.co", password=PASSWORD
        )

        assert admin.is_staff is True
        assert admin.is_superuser is True

    def test_queda_activo(self):
        assert User.objects.create_superuser(
            email="admin@finty.co", password=PASSWORD
        ).is_active

    def test_se_persiste(self):
        admin = User.objects.create_superuser(
            email="admin@finty.co", password=PASSWORD
        )

        assert User.objects.get(pk=admin.pk).is_superuser

    def test_con_is_staff_false_lanza_value_error(self):
        """Validacion estandar de Django sobre flags de permisos."""
        with pytest.raises(ValueError):
            User.objects.create_superuser(
                email="admin@finty.co", password=PASSWORD, is_staff=False
            )

    def test_con_is_superuser_false_lanza_value_error(self):
        with pytest.raises(ValueError):
            User.objects.create_superuser(
                email="admin@finty.co", password=PASSWORD, is_superuser=False
            )

    def test_los_flags_invalidos_no_dejan_usuario_creado(self):
        with pytest.raises(ValueError):
            User.objects.create_superuser(
                email="admin@finty.co", password=PASSWORD, is_staff=False
            )

        assert not User.objects.filter(email="admin@finty.co").exists()

    def test_sin_email_lanza_value_error(self):
        with pytest.raises(ValueError):
            User.objects.create_superuser(email="", password=PASSWORD)

    def test_la_contrasena_queda_hasheada(self):
        admin = User.objects.create_superuser(
            email="admin@finty.co", password=PASSWORD
        )

        assert admin.password != PASSWORD
        assert admin.check_password(PASSWORD)


class TestIdentificadorPorEmail:
    """El email es el identificador de acceso, no un username."""

    def test_username_field_es_email(self):
        assert User.USERNAME_FIELD == "email"

    def test_no_hay_campos_requeridos_adicionales(self):
        assert User.REQUIRED_FIELDS == []

    def test_el_modelo_no_tiene_username(self):
        assert not hasattr(User, "username") or User.username is None

    def test_email_duplicado_lanza_integrity_error(self):
        """INV-10, y la hace cumplir la constraint de la columna."""
        from django.db import IntegrityError
        from django.db import transaction as db_transaction

        User.objects.create_user(email="ana@finty.co", password=PASSWORD)

        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                User.objects.create_user(email="ana@finty.co", password=PASSWORD)

    def test_str_devuelve_el_email(self):
        user = User.objects.create_user(email="ana@finty.co", password=PASSWORD)

        assert str(user) == "ana@finty.co"

    def test_str_del_perfil_nombra_al_usuario(self):
        """`UserProfile.__str__` es el unico metodo que ADR-03 permite ahi."""
        from identity.models import UserProfile

        user = User.objects.create_user(email="ana@finty.co", password=PASSWORD)
        perfil = UserProfile.objects.create(user=user, display_name="Ana Restrepo")

        assert str(perfil) == f"Ana Restrepo ({user.pk})"
