"""Adaptadores de los correos (E2-M7): identity, plantillas y envio. Sin base."""
import io
import json
import urllib.error
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from domain.interfaces import ContactNotFound, ContactUnavailable
from domain.notifications import Contact, EmailMessage, NotificationKind
from infra import contacts as contacts_module
from infra.configuration import ConfigurationError
from infra.contacts import HttpContactDirectory
from infra.email import ConsoleEmailSender, FileEmailSender, email_sender_from_environment
from infra.email_templates import TemplateEmailComposer, format_date

END = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestContactoDeIdentity:
    def test_lee_el_contacto(self, monkeypatch):
        calls = []

        def urlopen(url, timeout):
            calls.append((url, timeout))
            return FakeResponse(json.dumps({"email": "ana@finty.co", "display_name": "Ana", "language": "en"}).encode())

        monkeypatch.setattr(contacts_module.urllib.request, "urlopen", urlopen)
        user_id = uuid4()
        contact = HttpContactDirectory("http://django:8000/", timeout=2).contact(user_id)

        assert contact == Contact("ana@finty.co", "Ana", "en")
        assert calls == [(f"http://django:8000/internal/users/{user_id}/contact/", 2)]

    def test_404_es_contacto_inexistente(self, monkeypatch):
        def urlopen(url, timeout):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        monkeypatch.setattr(contacts_module.urllib.request, "urlopen", urlopen)
        with pytest.raises(ContactNotFound):
            HttpContactDirectory("http://django:8000").contact(uuid4())

    @pytest.mark.parametrize("error", [
        urllib.error.URLError("conexion rechazada"),
        urllib.error.HTTPError("x", 502, "Bad Gateway", {}, None),
        TimeoutError("lento"),
    ])
    def test_red_o_5xx_es_transitorio(self, monkeypatch, error):
        def urlopen(url, timeout):
            raise error

        monkeypatch.setattr(contacts_module.urllib.request, "urlopen", urlopen)
        with pytest.raises(ContactUnavailable):
            HttpContactDirectory("http://django:8000").contact(uuid4())

    def test_respuesta_fuera_de_contrato_es_transitoria(self, monkeypatch):
        monkeypatch.setattr(contacts_module.urllib.request, "urlopen", lambda url, timeout: FakeResponse(b"{}"))
        with pytest.raises(ContactUnavailable):
            HttpContactDirectory("http://django:8000").contact(uuid4())

    def test_un_idioma_no_soportado_cae_en_espanol(self):
        assert Contact("a@b.co", "A", "fr").language == "es"


class TestPlantillas:
    @pytest.mark.parametrize("language, fecha", [("es", "21 de noviembre de 2026"), ("en", "November 21, 2026")])
    def test_fecha_en_la_zona_del_proceso(self, language, fecha):
        assert format_date(END, language) == fecha

    @pytest.mark.parametrize("kind, language, asunto", [
        (NotificationKind.PREMIUM_WELCOME, "es", "¡Bienvenido a Finty Premium!"),
        (NotificationKind.PREMIUM_WELCOME, "en", "Welcome to Finty Premium!"),
        (NotificationKind.SUBSCRIPTION_EXPIRING, "es", "Tu plan Premium termina el 21 de noviembre de 2026"),
        (NotificationKind.SUBSCRIPTION_EXPIRING, "en", "Your Premium plan ends on November 21, 2026"),
    ])
    def test_cada_aviso_en_cada_idioma(self, kind, language, asunto):
        message = TemplateEmailComposer().compose(kind, Contact("ana@finty.co", "Ana Restrepo", language), END)
        assert message.to == "ana@finty.co"
        assert message.subject == asunto
        assert ("Hola, Ana:" if language == "es" else "Hi Ana,") in message.body


class TestEnvio:
    MESSAGE = EmailMessage("ana@finty.co", "Asunto con tilde: ¡Hola!", "Cuerpo del correo.")

    def test_consola(self):
        stream = io.StringIO()
        ConsoleEmailSender(stream).send(self.MESSAGE)
        output = stream.getvalue()
        assert "To: ana@finty.co" in output and "Cuerpo del correo." in output
        assert "Subject: Asunto con tilde: ¡Hola!" in output, "el asunto se lee sin codificar"

    def test_archivo(self, tmp_path, capsys):
        FileEmailSender(tmp_path).send(self.MESSAGE)
        [eml] = list(tmp_path.glob("*.eml"))
        assert "To: ana@finty.co" in eml.read_text(encoding="utf-8")

    def test_por_entorno(self, tmp_path):
        assert isinstance(email_sender_from_environment({}), ConsoleEmailSender)
        assert isinstance(email_sender_from_environment({"EMAIL_BACKEND": "file", "EMAIL_FILE_DIR": str(tmp_path)}), FileEmailSender)
        with pytest.raises(ConfigurationError):
            email_sender_from_environment({"EMAIL_BACKEND": "smtp"})
