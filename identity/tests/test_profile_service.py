"""Tests de `ProfileService`: la capa donde vive la logica de identidad."""
import pytest

from core.domain.exceptions import ValidationError
from identity.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    ProfileNotFoundError,
    WeakPasswordError,
)
from identity.models import User, UserProfile
from identity.services import ProfileService

pytestmark = pytest.mark.django_db

PASSWORD = "Contrasena-Segura-2026"


@pytest.fixture
def service():
    """Instancia del servicio bajo prueba."""
    return ProfileService()


@pytest.fixture
def registered_user(service):
    """Usuario ya registrado con su perfil."""
    user, _ = service.register_user("ana@finty.co", PASSWORD, "Ana Restrepo")
    return user


class TestRegistro:
    """`register_user`."""

    def test_crea_usuario_y_perfil_en_la_misma_operacion(self, service):
        user, token = service.register_user("ana@finty.co", PASSWORD, "Ana Restrepo")

        assert User.objects.filter(pk=user.pk).exists()
        assert UserProfile.objects.filter(user=user).exists()
        assert user.profile.display_name == "Ana Restrepo"
        assert token

    def test_normaliza_el_email(self, service):
        user, _ = service.register_user("  Ana@Finty.CO ", PASSWORD, "Ana")
        assert user.email == "ana@finty.co"

    def test_el_perfil_arranca_con_valores_por_defecto(self, registered_user):
        assert registered_user.profile.preferred_currency == "COP"
        assert registered_user.profile.onboarding_completed is False

    def test_la_contrasena_queda_hasheada(self, registered_user):
        assert registered_user.password != PASSWORD
        assert registered_user.check_password(PASSWORD)

    def test_email_duplicado_lanza_error_de_negocio(self, service, registered_user):
        with pytest.raises(EmailAlreadyRegisteredError):
            service.register_user("ana@finty.co", PASSWORD, "Ana Impostora")

    def test_email_duplicado_no_deja_usuario_huerfano(self, service, registered_user):
        with pytest.raises(EmailAlreadyRegisteredError):
            service.register_user("ana@finty.co", PASSWORD, "Ana Impostora")

        assert User.objects.filter(email="ana@finty.co").count() == 1
        assert UserProfile.objects.count() == 1

    def test_email_duplicado_ignorando_mayusculas(self, service, registered_user):
        with pytest.raises(EmailAlreadyRegisteredError):
            service.register_user("ANA@FINTY.CO", PASSWORD, "Ana Impostora")

    @pytest.mark.parametrize("weak", ["123", "password", "abc", "12345678"])
    def test_contrasena_debil_lanza_error(self, service, weak):
        with pytest.raises(WeakPasswordError):
            service.register_user("nueva@finty.co", weak, "Nueva")

    def test_contrasena_debil_no_crea_nada(self, service):
        with pytest.raises(WeakPasswordError):
            service.register_user("nueva@finty.co", "123", "Nueva")

        assert not User.objects.filter(email="nueva@finty.co").exists()


class TestAutenticacion:
    """`authenticate_user`."""

    def test_credenciales_correctas_devuelven_token(self, service, registered_user):
        user, token = service.authenticate_user("ana@finty.co", PASSWORD)

        assert user.pk == registered_user.pk
        assert token

    def test_devuelve_el_mismo_token_del_registro(self, service):
        registered, registration_token = service.register_user(
            "ana@finty.co", PASSWORD, "Ana"
        )
        _, login_token = service.authenticate_user("ana@finty.co", PASSWORD)

        assert login_token == registration_token

    def test_acepta_el_email_con_otra_capitalizacion(self, service, registered_user):
        user, _ = service.authenticate_user("ANA@finty.co", PASSWORD)
        assert user.pk == registered_user.pk

    def test_contrasena_incorrecta_lanza_error(self, service, registered_user):
        with pytest.raises(InvalidCredentialsError):
            service.authenticate_user("ana@finty.co", "otra-contrasena-cualquiera")

    def test_email_inexistente_lanza_error(self, service):
        with pytest.raises(InvalidCredentialsError):
            service.authenticate_user("fantasma@finty.co", PASSWORD)

    def test_usuario_inactivo_lanza_error(self, service, registered_user):
        registered_user.is_active = False
        registered_user.save(update_fields=["is_active"])

        with pytest.raises(InvalidCredentialsError):
            service.authenticate_user("ana@finty.co", PASSWORD)

    def test_email_inexistente_y_contrasena_incorrecta_dicen_lo_mismo(
        self, service, registered_user
    ):
        with pytest.raises(InvalidCredentialsError) as inexistente:
            service.authenticate_user("fantasma@finty.co", PASSWORD)
        with pytest.raises(InvalidCredentialsError) as incorrecta:
            service.authenticate_user("ana@finty.co", "otra-contrasena-cualquiera")

        assert str(inexistente.value) == str(incorrecta.value)
        assert inexistente.value.code == incorrecta.value.code


class TestObtenerPerfil:
    """`get_profile`."""

    def test_devuelve_el_perfil_del_usuario(self, service, registered_user):
        assert service.get_profile(registered_user).pk == registered_user.pk

    def test_perfil_ausente_lanza_not_found(self, service, registered_user):
        UserProfile.objects.filter(user=registered_user).delete()

        with pytest.raises(ProfileNotFoundError):
            service.get_profile(registered_user)


class TestCompletarPerfil:
    """`complete_profile`."""

    def test_actualiza_solo_el_nombre_recibido(self, service, registered_user):
        profile = service.complete_profile(registered_user, display_name="Ana R.")

        assert profile.display_name == "Ana R."
        assert profile.preferred_currency == "COP"

    def test_actualiza_solo_la_moneda_recibida(self, service, registered_user):
        profile = service.complete_profile(registered_user, preferred_currency="USD")

        assert profile.preferred_currency == "USD"
        assert profile.display_name == "Ana Restrepo"

    def test_persiste_el_cambio(self, service, registered_user):
        service.complete_profile(registered_user, display_name="Ana R.")

        assert UserProfile.objects.get(user=registered_user).display_name == "Ana R."

    def test_normaliza_la_moneda_a_mayusculas(self, service, registered_user):
        profile = service.complete_profile(registered_user, preferred_currency="usd")
        assert profile.preferred_currency == "USD"

    def test_recorta_espacios_del_nombre(self, service, registered_user):
        profile = service.complete_profile(registered_user, display_name="  Ana R.  ")
        assert profile.display_name == "Ana R."

    def test_marca_onboarding_completado(self, service, registered_user):
        assert registered_user.profile.onboarding_completed is False

        profile = service.complete_profile(
            registered_user, display_name="Ana R.", preferred_currency="USD"
        )

        assert profile.onboarding_completed is True

    def test_el_onboarding_persiste(self, service, registered_user):
        service.complete_profile(registered_user, display_name="Ana R.")

        assert UserProfile.objects.get(user=registered_user).onboarding_completed

    def test_nombre_vacio_lanza_validacion_de_dominio(self, service, registered_user):
        with pytest.raises(ValidationError):
            service.complete_profile(registered_user, display_name="   ")

    def test_moneda_invalida_lanza_validacion_de_dominio(self, service, registered_user):
        with pytest.raises(ValidationError):
            service.complete_profile(registered_user, preferred_currency="PESO")

    def test_moneda_invalida_no_persiste_nada(self, service, registered_user):
        with pytest.raises(ValidationError):
            service.complete_profile(
                registered_user, display_name="Ana R.", preferred_currency="PESO"
            )

        stored = UserProfile.objects.get(user=registered_user)
        assert stored.display_name == "Ana Restrepo"

    def test_sin_campos_no_cambia_nada(self, service, registered_user):
        profile = service.complete_profile(registered_user)

        assert profile.display_name == "Ana Restrepo"
        assert profile.onboarding_completed is False
