"""Fixtures de categorization-service. Sin base de datos: todo corre en memoria."""
import pytest


@pytest.fixture
def app(monkeypatch):
    from app import create_app

    monkeypatch.setenv("CATEGORIZER_PROVIDER", "RULE")
    application = create_app()
    application.testing = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()
