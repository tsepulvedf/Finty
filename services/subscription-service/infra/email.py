"""Envio de correos (E2-M7): sin servidor SMTP en esta entrega.

`EMAIL_BACKEND` elige el adaptador, como `PAYMENT_GATEWAY` elige la pasarela:

- `console` (por defecto): escribe el correo completo en la salida del worker
  (`docker compose logs subscription-worker`).
- `file`: ademas lo guarda como `.eml` en `EMAIL_FILE_DIR`
  (`/tmp/finty-mail` por defecto).

Un valor desconocido impide arrancar.
"""
import logging
import os
import sys
from datetime import datetime, timezone
from email.message import EmailMessage as MimeMessage
from pathlib import Path
from uuid import uuid4

from domain.interfaces import EmailSender
from infra.configuration import ConfigurationError

logger = logging.getLogger(__name__)

FROM_ADDRESS = "Finty <no-responder@finty.local>"
DEFAULT_FILE_DIR = "/tmp/finty-mail"


def _mime(message):
    mime = MimeMessage()
    mime["From"] = FROM_ADDRESS
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    mime.set_content(message.body)
    return mime


class ConsoleEmailSender(EmailSender):
    name = "console"

    def __init__(self, stream=None):
        self._stream = stream

    def send(self, message):
        """Legible en el log: cabeceras sin codificar MIME (el .eml si las codifica)."""
        stream = self._stream or sys.stdout
        separator = "-" * 72
        stream.write(
            f"{separator}\n[correo] From: {FROM_ADDRESS}\nTo: {message.to}\n"
            f"Subject: {message.subject}\n\n{message.body}\n{separator}\n"
        )
        stream.flush()


class FileEmailSender(EmailSender):
    name = "file"

    def __init__(self, directory):
        self._directory = Path(directory)

    def send(self, message):
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.eml"
        path.write_text(_mime(message).as_string(), encoding="utf-8")
        ConsoleEmailSender().send(message)
        logger.info("correo guardado en %s", path)


def email_sender_from_environment(environ=os.environ):
    backend = environ.get("EMAIL_BACKEND", "console").strip().lower()
    if backend == "console":
        return ConsoleEmailSender()
    if backend == "file":
        return FileEmailSender(environ.get("EMAIL_FILE_DIR", DEFAULT_FILE_DIR))
    raise ConfigurationError(f"EMAIL_BACKEND desconocido: {backend!r}. Use 'console' o 'file'.")
