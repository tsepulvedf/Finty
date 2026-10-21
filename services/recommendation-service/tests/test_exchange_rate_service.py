"""Cadena de degradacion de tasas (`ExchangeRateService`, ADR-12, A-22).

live → cached → fallback, con la procedencia veraz de A-14: `live` solo cuando la
API respondio en esa consulta; todo lo que sale de Redis es `cached`.
"""
from datetime import date, datetime
from decimal import Decimal

from domain.value_objects import ExchangeRateSource
from infra.exchange_rates import FixedExchangeRateProvider
from infra.rate_cache import RedisExchangeRateCache
from services import ExchangeRateService
from tests.doubles import NOW, TODAY, TRM, FakeRateProvider, MemoryRateCache, fixed_clock


class TestCadenaDeDegradacion:
    """A-22 para tasas: live → cached → fallback, con procedencia veraz."""

    def service(self, provider, cache, now=NOW):
        return ExchangeRateService(provider, cache, FixedExchangeRateProvider("3200"), fixed_clock(now))

    def test_api_disponible_live_y_se_guarda(self):
        provider, cache = FakeRateProvider(), MemoryRateCache()
        rate = self.service(provider, cache).rate("USD", "COP")
        assert (rate.rate, rate.source) == (TRM, ExchangeRateSource.LIVE)
        assert cache.days[TODAY] == rate and cache.ttls == [14 * 3600]  # 10:00 → medianoche

    def test_el_mismo_dia_sale_del_cache(self):
        provider, cache = FakeRateProvider(), MemoryRateCache()
        self.service(provider, cache).rate("USD", "COP")
        rate = self.service(provider, cache).rate("USD", "COP")
        assert rate.source is ExchangeRateSource.CACHED and provider.calls == 1

    def test_api_caida_usa_la_ultima_conocida(self):
        provider, cache = FakeRateProvider(), MemoryRateCache()
        self.service(provider, cache, datetime(2026, 10, 20, 9, 0)).rate("USD", "COP")
        provider.down = True
        rate = self.service(provider, cache).rate("USD", "COP")
        assert (rate.rate, rate.source, rate.fetched_on) == (TRM, ExchangeRateSource.CACHED, date(2026, 10, 20))

    def test_sin_cache_tasa_fija(self):
        provider = FakeRateProvider()
        provider.down = True
        rate = self.service(provider, MemoryRateCache()).rate("USD", "COP")
        assert (rate.rate, rate.source) == (Decimal("3200"), ExchangeRateSource.FALLBACK)

    def test_cop_usd_es_la_inversa_con_su_procedencia(self):
        provider = FakeRateProvider()
        provider.down = True
        rate = self.service(provider, MemoryRateCache()).rate("COP", "USD")
        assert (rate.base, rate.target, rate.rate, rate.source) == ("COP", "USD", Decimal("0.0003125000"), ExchangeRateSource.FALLBACK)

    def test_una_sola_consulta_por_peticion(self):
        provider = FakeRateProvider()
        service = self.service(provider, MemoryRateCache())
        service.rate("USD", "COP")
        service.rate("COP", "USD")
        assert provider.calls == 1

    def test_redis_caido_no_rompe_la_cadena(self):
        cache = RedisExchangeRateCache.from_url("redis://127.0.0.1:9/0")
        rate = self.service(FakeRateProvider(), cache).rate("USD", "COP")
        assert rate.source is ExchangeRateSource.LIVE
