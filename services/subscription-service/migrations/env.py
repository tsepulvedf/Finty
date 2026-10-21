"""Entorno de Alembic para finty_subscription.

La URL sale de `sqlalchemy.url` si quien invoca la fijo (los tests lo hacen) o,
si no, de `DATABASE_URL`. Las migraciones se escriben a mano y no se generan
desde `models.py`: igual que en el monolito, una migracion es un artefacto
historico y no debe depender de la forma actual del codigo.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


def _database_url():
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL: la URL de finty_subscription que debe migrar Alembic."
        )
    return url


def run_migrations_offline():
    """Genera el SQL sin conectarse (`alembic upgrade head --sql`)."""
    context.configure(url=_database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Aplica las migraciones contra la base."""
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
