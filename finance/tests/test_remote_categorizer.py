"""El fallo remoto no rompe el registro ni acepta categorias incompatibles."""
import io
import json
import threading
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.core.exceptions import ImproperlyConfigured

from core.domain.value_objects import Money
from finance.infra.remote_categorizer import RemoteCategorizer
from finance.infra.factories import CategorizerFactory
from services.categorization.app import create_app
from werkzeug.serving import make_server


def remote():
    return RemoteCategorizer("http://service/api/v2/categorization/", "test-key", timeout=0.1)


def test_success_and_wire_contract():
    data = {"category_name": "Alimentación", "confidence": 0.75, "source": "rule"}
    with patch("finance.infra.remote_categorizer.urlopen", return_value=io.BytesIO(json.dumps(data).encode())) as opening:
        result = remote().categorize("almuerzo", Money("25", "COP"), "expense")
    assert result.confidence == 0.75
    request = opening.call_args.args[0]
    assert json.loads(request.data)["amount"] == "25.00"
    assert opening.call_args.kwargs["timeout"] == 0.1


@pytest.mark.parametrize("failure", [TimeoutError(), ConnectionError(), ValueError()])
def test_failure_falls_back(failure):
    with patch("finance.infra.remote_categorizer.urlopen", side_effect=failure):
        result = remote().categorize("almuerzo", Money("25", "COP"), "expense")
    assert result.category_name == "Alimentación"
    assert result.source == "rule"
    assert result.confidence == 0.20


@pytest.mark.parametrize("data", [
    {"category_name": "Salario", "confidence": 0.75, "source": "rule"},
    {"category_name": "Alimentación", "confidence": 2, "source": "rule"},
    {"category_name": "Alimentación", "confidence": True, "source": "rule"},
    {"category_name": "Alimentación", "confidence": 0.75, "source": "ai"},
    {}, [],
])
def test_invalid_response_falls_back(data):
    with patch("finance.infra.remote_categorizer.urlopen", return_value=io.BytesIO(json.dumps(data).encode())):
        result = remote().categorize("almuerzo", Money("25", "COP"), "expense")
    assert result.category_name == "Alimentación"
    assert result.confidence == 0.20


@override_settings(CATEGORIZER_PROVIDER="REMOTE", CATEGORIZATION_SERVICE_TOKEN="test-key")
def test_factory():
    assert isinstance(CategorizerFactory.get_categorizer(), RemoteCategorizer)


@override_settings(CATEGORIZER_PROVIDER="REMOTE", CATEGORIZATION_SERVICE_TOKEN="")
def test_factory_requires_key():
    with pytest.raises(ImproperlyConfigured):
        CategorizerFactory.get_categorizer()


def test_real_http_between_adapter_and_flask():
    server = make_server("127.0.0.1", 0, create_app(service_token="test-key"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        categorizer = RemoteCategorizer(
            f"http://127.0.0.1:{server.server_port}/api/v2/categorization/", "test-key"
        )
        result = categorizer.categorize("almuerzo", Money("25", "COP"), "expense")
        assert result.category_name == "Alimentación"
        assert result.confidence == 0.75  # El respaldo daria 0.20.
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
