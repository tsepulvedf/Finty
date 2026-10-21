"""Servidor HTTP falso que cumple el contrato de `categorization-service`.

Sirve `POST /v1/suggestions/` en un puerto local. Su `mode` decide la respuesta,
para probar el adaptador y el respaldo sin levantar el servicio real:

- `rule`: clasifica con las mismas reglas que el servicio real (`rule`).
- `mock`: la categoria de respaldo del tipo con confianza 1.0 (`mock`).
- `error`: 503.
- `slow`: tarda `delay` segundos y luego responde como `rule`.
- `garbage`: 200 con un cuerpo que no es JSON.
- `unknown`: una categoria que no existe en el catalogo.
- `wrong_type`: una categoria del catalogo, pero del otro tipo.
- `manual`: procedencia `manual`, que el remoto no puede declarar.
- `bad_confidence`: confianza fuera de [0, 1].
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from domain.value_objects import TransactionType
from infra.categorizers import FALLBACK_BY_TYPE, RuleBasedCategorizer

OTHER_TYPE = {"expense": "Salario", "income": "Alimentación"}


class FakeCategorization:
    """Controla el servidor falso y registra las peticiones recibidas."""

    def __init__(self):
        self.mode = "rule"
        self.delay = 1.0
        self.requests = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.fake = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self):
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def reset(self):
        self.mode = "rule"
        self.delay = 1.0
        self.requests.clear()

    def close(self):
        self._server.shutdown()
        self._server.server_close()


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 — nombre que exige BaseHTTPRequestHandler
        fake = self.server.fake
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        fake.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        kind = body.get("transaction_type", "expense")

        if fake.mode == "error":
            return self._send(503, {"error": {"code": "unavailable", "message": "caido"}})
        if fake.mode == "garbage":
            return self._send_raw(200, b"esto no es json")
        if fake.mode == "slow":
            time.sleep(fake.delay)

        responses = {
            "mock": {"category_name": FALLBACK_BY_TYPE[TransactionType(kind)], "confidence": 1.0, "source": "mock"},
            "unknown": {"category_name": "Criptomonedas", "confidence": 0.9, "source": "rule"},
            "wrong_type": {"category_name": OTHER_TYPE[kind], "confidence": 0.9, "source": "rule"},
            "manual": {"category_name": FALLBACK_BY_TYPE[TransactionType(kind)], "confidence": 1.0, "source": "manual"},
            "bad_confidence": {"category_name": FALLBACK_BY_TYPE[TransactionType(kind)], "confidence": 7, "source": "rule"},
        }
        if fake.mode in responses:
            return self._send(200, responses[fake.mode])

        suggestion = RuleBasedCategorizer().categorize(body.get("description", ""), None, kind)
        return self._send(200, {
            "category_name": suggestion.category_name,
            "confidence": suggestion.confidence,
            "source": suggestion.source.value,
        })

    def _send(self, status, payload):
        self._send_raw(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _send_raw(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass
