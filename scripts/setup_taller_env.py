"""Genera una configuracion local sin sobrescribir secretos existentes."""
from pathlib import Path
import secrets


def main():
    root = Path(__file__).resolve().parent.parent
    content = (root / ".env.docker.example").read_text(encoding="utf-8")
    for name in ("SECRET_KEY", "DB_PASSWORD", "CATEGORIZATION_SERVICE_TOKEN"):
        content = content.replace(name + "=\n", name + "=" + secrets.token_hex(32) + "\n")
    try:
        with (root / ".env.docker").open("x", encoding="utf-8") as output:
            output.write(content)
    except FileExistsError:
        raise SystemExit(".env.docker ya existe; se conserva. Revisalo antes de continuar.")
    print("Configuracion .env.docker creada. Puedes iniciar Docker Compose.")


if __name__ == "__main__":
    main()
