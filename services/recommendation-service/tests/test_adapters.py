"""Adaptadores de recommendation-service: TRM, tasa fija, cache y analytics.

Sin red externa. La cadena que los combina esta en `test_exchange_rate_service.py`.

Los adaptadores HTTP se prueban contra un servidor local que responde con la
forma real de cada API (la de la TRM se verifico contra datos.gov.co el
2026-10-21).
"""
import json
import threading
from datetime import date
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
import redis

from domain.interfaces import AnalyticsUnavailable, ExchangeRateUnavailable
from domain.period import Period
from domain.shared.value_objects import Money
from domain.value_objects import ExchangeRateSource
from infra.analytics_client import HttpAnalyticsReader
from infra.exchange_rates import FixedExchangeRateProvider, TrmExchangeRateProvider
from infra.rate_cache import RedisExchangeRateCache, day_key, last_key
from tests.doubles import TODAY, TRM, FakeRateProvider

TRM_ROW = {
    "valor": "3163.76", "unidad": "COP",
    "vigenciadesde": "2026-10-21T00:00:00.000", "vigenciahasta": "2026-10-21T00:00:00.000",
}
UNREACHABLE = "http://127.0.0.1:9"


class Server:
    """Servidor HTTP local: `routes[path] = (status, cuerpo)`; guarda lo recibido."""

    def __init__(self):
        self.routes = {}
        self.requests = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parts = urlsplit(self.path)
                server.requests.append((parts.path, parse_qs(parts.query), dict(self.headers)))
                status, body = server.routes.get(parts.path, (404, {"detail": "No encontrado."}))
                data = json.dumps(body).encode()
                self.send_response(status)
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
    s = Server()
    yield s
    s.close()


# --- TRM oficial ---------------------------------------------------------------


class TestTrmExchangeRateProvider:
    PATH = "/resource/32sa-8pi3.json"

    def provider(self, server):
        return TrmExchangeRateProvider(server.url + self.PATH, timeout=2)

    def test_traduce_la_fila_al_value_object(self, server):
        server.routes[self.PATH] = (200, [TRM_ROW])
        rate = self.provider(server).rate("USD", "COP", TODAY)
        assert (rate.base, rate.target, rate.rate, rate.source) == ("USD", "COP", Decimal("3163.76"), ExchangeRateSource.LIVE)
        assert (rate.valid_from, rate.valid_until, rate.fetched_on) == (TODAY, TODAY, TODAY)

    def test_pide_la_vigente_el_dia(self, server):
        server.routes[self.PATH] = (200, [TRM_ROW])
        self.provider(server).rate("USD", "COP", date(2026, 10, 18))
        _, query, _ = server.requests[0]
        assert query["$where"] == ["vigenciadesde <= '2026-10-18T00:00:00'"]
        assert query["$order"] == ["vigenciadesde DESC"] and query["$limit"] == ["1"]

    def test_vigencia_de_fin_de_semana(self, server):
        row = dict(TRM_ROW, valor="3174.67", vigenciadesde="2026-10-17T00:00:00.000", vigenciahasta="2026-10-19T00:00:00.000")
        server.routes[self.PATH] = (200, [row])
        rate = self.provider(server).rate("USD", "COP", date(2026, 10, 18))
        assert (rate.valid_from, rate.valid_until) == (date(2026, 10, 17), date(2026, 10, 19))

    @pytest.mark.parametrize("status, body", [
        (500, {"error": "x"}),
        (200, []),
        (200, [dict(TRM_ROW, unidad="USD")]),
        (200, [dict(TRM_ROW, valor="abc")]),
        (200, [dict(TRM_ROW, valor="0")]),
        (200, [{"otro": 1}]),
        (200, {"no": "lista"}),
    ])
    def test_respuesta_inutilizable(self, server, status, body):
        server.routes[self.PATH] = (status, body)
        with pytest.raises(ExchangeRateUnavailable):
            self.provider(server).rate("USD", "COP", TODAY)

    def test_api_inalcanzable(self):
        with pytest.raises(ExchangeRateUnavailable):
            TrmExchangeRateProvider(UNREACHABLE, timeout=1).rate("USD", "COP", TODAY)

    def test_fijo_dice_que_es_respaldo(self):
        rate = FixedExchangeRateProvider("3200").rate("USD", "COP", TODAY)
        assert (rate.rate, rate.source, rate.valid_from) == (Decimal("3200"), ExchangeRateSource.FALLBACK, None)


# --- Cache de Redis ------------------------------------------------------------


class FakeRedis:
    def __init__(self):
        self.data, self.ttl = {}, {}

    def get(self, key):
        return self.data.get(key)

    def pipeline(self):
        return self

    def set(self, key, value, ex=None):
        self.data[key] = value
        self.ttl[key] = ex

    def execute(self):
        pass


class TestRedisExchangeRateCache:
    def test_guarda_el_dia_con_ttl_y_la_ultima_sin_ttl(self):
        client = FakeRedis()
        live = FakeRateProvider().rate("USD", "COP", TODAY)
        RedisExchangeRateCache(client).store(live, TODAY, 3600)
        assert client.ttl == {day_key("USD", "COP", TODAY): 3600, last_key("USD", "COP"): None}

    def test_lo_que_sale_del_cache_es_cached(self):
        client = FakeRedis()
        cache = RedisExchangeRateCache(client)
        cache.store(FakeRateProvider().rate("USD", "COP", TODAY), TODAY, 3600)
        for rate in (cache.today("USD", "COP", TODAY), cache.last_known("USD", "COP")):
            assert (rate.rate, rate.source, rate.fetched_on) == (TRM, ExchangeRateSource.CACHED, TODAY)

    def test_otro_dia_no_es_hoy(self):
        cache = RedisExchangeRateCache(FakeRedis())
        cache.store(FakeRateProvider().rate("USD", "COP", TODAY), TODAY, 3600)
        assert cache.today("USD", "COP", date(2026, 10, 22)) is None

    def test_redis_caido_es_un_cache_vacio(self):
        cache = RedisExchangeRateCache.from_url("redis://127.0.0.1:9/0")
        assert cache.today("USD", "COP", TODAY) is None and cache.last_known("USD", "COP") is None
        cache.store(FakeRateProvider().rate("USD", "COP", TODAY), TODAY, 10)  # no lanza


# --- Cliente de analytics -----------------------------------------------------


INSIGHTS = {"period": "2026-10", "insights": [
    {"type": "CATEGORY_SPIKE", "code": "category_spike", "severity": "warning", "period": "2026-10",
     "params": {"category_name": "Compras", "currency": "COP", "increase_pct": "100.0"},
     "evidence": {"current": "200000.00", "previous_average": "100000.00", "previous_months": [], "threshold_pct": "30.0", "min_amount": "50000"}},
    {"type": "NEGATIVE_SAVINGS", "code": "negative_savings", "severity": "warning", "period": "2026-10",
     "params": {"currency": "COP", "deficit": "50000.00"},
     "evidence": {"income": "100000.00", "expense": "150000.00"}},
    {"type": "TOP_CATEGORY", "code": "top_category", "severity": "info", "period": "2026-10",
     "params": {"category_name": "Compras", "currency": "COP", "share_pct": "100.0"},
     "evidence": {"category_total": "1.00", "expense_total": "1.00"}},
]}
PATTERNS = {"reference_period": "2026-10", "window_months": 6, "patterns": [
    {"description": "netflix", "category_name": "Entretenimiento", "currency": "COP", "average_amount": "39900.00",
     "months_present": 3, "window_months": 6, "occurrences": 3, "monthly_frequency": "1.00", "last_seen": "2026-10-03"},
]}
DASHBOARD = {"period": "2026-10", "currencies": [{"currency": "COP", "income": "0.00", "expense": "0.00", "net": "0.00",
    "categories": [], "accounts": [],
    "trend": [{"period": "2026-09", "income": "500000.00", "expense": "200000.00", "net": "300000.00"}]}]}


class TestHttpAnalyticsReader:
    def serve(self, server):
        server.routes.update({
            "/api/v1/analytics/insights/": (200, INSIGHTS),
            "/api/v1/analytics/spending-patterns/": (200, PATTERNS),
            "/api/v1/analytics/dashboard/": (200, DASHBOARD),
        })

    def test_traduce_y_reenvia_la_identidad(self, server):
        self.serve(server)
        user = uuid4()
        snapshot = HttpAnalyticsReader(server.url).snapshot(user, Period(2026, 10))

        assert [s.category_name for s in snapshot.spikes] == ["Compras"]
        assert snapshot.negative_savings[0].deficit == Money("50000", "COP")
        assert snapshot.recurring[0].average_amount == Money("39900", "COP")
        assert [(str(n.period), n.net) for n in snapshot.monthly_nets] == [("2026-09", Money("300000", "COP"))]
        for _, query, headers in server.requests:
            assert headers["X-User-Id"] == str(user) and query["period"] == ["2026-10"]
            # Llamada interna: las de optimizacion son gratuitas aunque lean insights (INV-06).
            assert headers["X-Finty-Caller"] == "recommendation-service"

    @pytest.mark.parametrize("broken", ["/api/v1/analytics/insights/", "/api/v1/analytics/dashboard/"])
    def test_un_500_es_unavailable(self, server, broken):
        self.serve(server)
        server.routes[broken] = (500, {"detail": "Error interno del servidor."})
        with pytest.raises(AnalyticsUnavailable):
            HttpAnalyticsReader(server.url).snapshot(uuid4(), Period(2026, 10))

    def test_fuera_de_contrato_es_unavailable(self, server):
        self.serve(server)
        server.routes["/api/v1/analytics/insights/"] = (200, {"otra": "cosa"})
        with pytest.raises(AnalyticsUnavailable):
            HttpAnalyticsReader(server.url).snapshot(uuid4(), Period(2026, 10))

    def test_inalcanzable_es_unavailable(self):
        with pytest.raises(AnalyticsUnavailable):
            HttpAnalyticsReader(UNREACHABLE, timeout=0.5).snapshot(uuid4(), Period(2026, 10))
