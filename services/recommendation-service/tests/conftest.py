"""Fixtures compartidas de la suite de recommendation-service.

Los tests de `tests/domain/` no piden ninguna fixture
de base de datos y corren sin PostgreSQL.

Los demas necesitan `RECOMMENDATION_TEST_DATABASE_URL`, la URL de una base **de
pruebas** cuyo nombre termine en `_test`. Al iniciar la sesion de pytest la base
se borra, se recrea y se migra con Alembic hasta `head`, asi que las migraciones
tambien quedan probadas. Cada test corre dentro de una transaccion que se
revierte al terminar: lo que un servicio "confirma" solo libera un savepoint.

    RECOMMENDATION_TEST_DATABASE_URL=postgresql+psycopg2://finty:<clave>@localhost:5432/finty_recommendation_test
"""
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

SERVICE_ROOT = Path(__file__).resolve().parent.parent
TEST_DATABASE_ENV = "RECOMMENDATION_TEST_DATABASE_URL"
TEST_DATABASE_SUFFIX = "_test"
USER_ID_HEADER = "X-User-Id"


@pytest.fixture(scope="session")
def database_url():
    """URL de la base de pruebas, validada antes de tocar nada."""
    raw = os.environ.get(TEST_DATABASE_ENV)
    if not raw:
        pytest.fail(
            f"Falta {TEST_DATABASE_ENV}: la URL de una base de pruebas de "
            f"PostgreSQL (su nombre debe terminar en '{TEST_DATABASE_SUFFIX}')."
        )
    url = make_url(raw)
    if not (url.database or "").endswith(TEST_DATABASE_SUFFIX):
        pytest.fail(
            f"{TEST_DATABASE_ENV} apunta a '{url.database}'. La suite borra y "
            f"recrea la base, asi que solo acepta nombres terminados en "
            f"'{TEST_DATABASE_SUFFIX}'."
        )
    return url


def _recreate_database(url):
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


def _migrate(url):
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    # `%` se escapa porque el .ini pasa por la interpolacion de configparser.
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def engine(database_url):
    """Engine sobre la base de pruebas, recien creada y migrada."""
    _recreate_database(database_url)
    _migrate(database_url)
    test_engine = create_engine(database_url)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def connection(engine):
    """Conexion con una transaccion externa que se revierte al final del test."""
    conn = engine.connect()
    outer = conn.begin()
    yield conn
    outer.rollback()
    conn.close()


def _session_on(connection):
    """Sesion cuyos `commit()` solo liberan savepoints de la transaccion externa."""
    return Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )


@pytest.fixture
def session(connection):
    """Sesion para los tests de servicios y de persistencia."""
    test_session = _session_on(connection)
    yield test_session
    test_session.close()


@pytest.fixture
def adapters():
    """Dobles de los puertos: analytics, API de tasas, cache, respaldo y reloj."""
    from tests.doubles import FakeAnalytics, FakeRateProvider, MemoryRateCache, fixed_clock
    from infra.exchange_rates import FixedExchangeRateProvider

    return {
        "analytics": FakeAnalytics(),
        "provider": FakeRateProvider(),
        "cache": MemoryRateCache(),
        "fallback": FixedExchangeRateProvider("3200"),
        "clock": fixed_clock(),
    }


@pytest.fixture
def app(connection, adapters):
    """Aplicacion Flask cuyas peticiones usan la conexion del test y los dobles."""
    from api import context
    from app import create_app

    application = create_app(
        session_factory=lambda: _session_on(connection),
        adapters={
            context.ANALYTICS_READER_KEY: adapters["analytics"],
            context.RATE_PROVIDER_KEY: adapters["provider"],
            context.RATE_CACHE_KEY: adapters["cache"],
            context.RATE_FALLBACK_KEY: adapters["fallback"],
            context.CLOCK_KEY: adapters["clock"],
        },
    )
    application.testing = True
    return application


class UserClient:
    """Cliente HTTP de pruebas que se identifica con `X-User-Id`.

    Hace el papel del Gateway: en produccion esa cabecera la pone Nginx tras
    verificar el token contra Django (ADR-09). `user_id=None` no la envia.
    """

    def __init__(self, client, user_id):
        self._client = client
        self.user_id = user_id

    def _headers(self, extra=None):
        headers = {USER_ID_HEADER: str(self.user_id)} if self.user_id else {}
        headers.update(extra or {})
        return headers

    def get(self, url, headers=None):
        return self._client.get(url, headers=self._headers(headers))

    def delete(self, url, headers=None):
        return self._client.delete(url, headers=self._headers(headers))

    def post(self, url, payload=None, headers=None, **kwargs):
        return self._send("post", url, payload, headers, **kwargs)

    def put(self, url, payload=None, headers=None, **kwargs):
        return self._send("put", url, payload, headers, **kwargs)

    def patch(self, url, payload=None, headers=None, **kwargs):
        return self._send("patch", url, payload, headers, **kwargs)

    def _send(self, method, url, payload, headers, **kwargs):
        send = getattr(self._client, method)
        if payload is not None:
            kwargs["json"] = payload
        return send(url, headers=self._headers(headers), **kwargs)


@pytest.fixture
def client_for(app):
    """Fabrica de clientes: `client_for(user_id)`."""

    def _build(user_id):
        return UserClient(app.test_client(), user_id)

    return _build


@pytest.fixture
def ana(client_for):
    return client_for(uuid4())


@pytest.fixture
def juan(client_for):
    return client_for(uuid4())


@pytest.fixture
def anonimo(client_for):
    return client_for(None)
