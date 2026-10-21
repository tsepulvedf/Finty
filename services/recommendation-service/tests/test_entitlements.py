"""Cliente de derechos premium (INV-06): HTTP con timeout y cache solo de los "si".

Sin base de datos ni red externa: un servidor HTTP local hace de
subscription-service y un doble hace de Redis.
"""
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest

from domain.entitlements import Entitlement
from domain.interfaces import EntitlementsReader, EntitlementsUnavailable
from infra.entitlements import CachedEntitlementsReader, HttpEntitlementsReader

NOW = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)
UNTIL = NOW + timedelta(days=30)


class Server:
    def __init__(self, status=200, body=None):
        self.status, self.body, self.paths = status, body, []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                server.paths.append(self.path)
                data = json.dumps(server.body).encode()
                self.send_response(server.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    s = Server(body={"premium": True, "until": UNTIL.isoformat()})
    yield s
    s.close()


class TestHttpEntitlementsReader:
    def test_lee_el_contrato(self, server):
        user = uuid4()
        assert HttpEntitlementsReader(server.url).entitlement(user) == Entitlement(True, UNTIL)
        assert server.paths == [f"/internal/entitlements/{user}"]

    def test_free(self, server):
        server.body = {"premium": False, "until": None}
        assert HttpEntitlementsReader(server.url).entitlement(uuid4()) == Entitlement(False, None)

    @pytest.mark.parametrize("status, body", [
        (500, {"detail": "x"}), (200, {"premium": "si"}), (200, {"premium": True, "until": None}), (200, {}),
    ])
    def test_fuera_de_contrato_es_unavailable(self, server, status, body):
        server.status, server.body = status, body
        with pytest.raises(EntitlementsUnavailable):
            HttpEntitlementsReader(server.url).entitlement(uuid4())

    def test_inalcanzable_es_unavailable(self):
        with pytest.raises(EntitlementsUnavailable):
            HttpEntitlementsReader("http://127.0.0.1:9", timeout=0.5).entitlement(uuid4())


class FakeRedis:
    def __init__(self):
        self.data, self.ttl = {}, {}
        self.down = False

    def get(self, key):
        if self.down:
            import redis
            raise redis.ConnectionError("caido")
        return self.data.get(key)

    def set(self, key, value, ex=None):
        if self.down:
            import redis
            raise redis.ConnectionError("caido")
        self.data[key], self.ttl[key] = value, ex


class Counting(EntitlementsReader):
    def __init__(self, result):
        self.result, self.calls = result, 0

    def entitlement(self, user_id):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class TestCachedEntitlementsReader:
    def reader(self, inner, client=None, now=NOW):
        return CachedEntitlementsReader(inner, client or FakeRedis(), ttl=30, clock=lambda: now)

    def test_un_si_se_cachea_con_ttl_corto(self):
        inner, client = Counting(Entitlement(True, UNTIL)), FakeRedis()
        reader = self.reader(inner, client)
        user = uuid4()
        assert reader.entitlement(user).premium and reader.entitlement(user).premium
        assert inner.calls == 1 and list(client.ttl.values()) == [30]

    def test_el_ttl_no_pasa_del_fin_del_periodo(self):
        client = FakeRedis()
        self.reader(Counting(Entitlement(True, NOW + timedelta(seconds=10))), client).entitlement(uuid4())
        assert list(client.ttl.values()) == [10]

    def test_un_no_nunca_se_cachea(self):
        inner, client = Counting(Entitlement(False, None)), FakeRedis()
        reader = self.reader(inner, client)
        user = uuid4()
        reader.entitlement(user)
        reader.entitlement(user)
        assert inner.calls == 2 and client.data == {}

    def test_un_si_vencido_en_cache_no_vale(self):
        client = FakeRedis()
        user = uuid4()
        self.reader(Counting(Entitlement(True, NOW + timedelta(seconds=10))), client).entitlement(user)
        later = Counting(Entitlement(False, None))
        assert self.reader(later, client, NOW + timedelta(seconds=11)).entitlement(user).premium is False
        assert later.calls == 1

    def test_redis_caido_consulta_directo(self):
        client = FakeRedis()
        client.down = True
        inner = Counting(Entitlement(True, UNTIL))
        assert self.reader(inner, client).entitlement(uuid4()).premium is True

    def test_servicio_caido_sin_cache_propaga(self):
        with pytest.raises(EntitlementsUnavailable):
            self.reader(Counting(EntitlementsUnavailable("x"))).entitlement(uuid4())


class TestEntitlement:
    def test_premium_solo_hasta_el_fin(self):
        entitlement = Entitlement(True, UNTIL)
        assert entitlement.is_premium_at(UNTIL - timedelta(seconds=1)) and not entitlement.is_premium_at(UNTIL)
        assert not Entitlement(False, None).is_premium_at(NOW)
