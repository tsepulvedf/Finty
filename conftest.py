"""Configuracion compartida de pytest."""
import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _reset_throttle_cache():
    """Limpia el cache entre tests para que el throttling de DRF no acumule.

    `DEFAULT_THROTTLE_RATES` cuenta peticiones por cliente en el cache, que en
    tests es un LocMemCache compartido por todo el proceso. Sin esta limpieza
    una bateria de tests de API agotaria la cuota `anon: 60/hour` y empezaria a
    devolver 429 por acumulacion entre tests, no por el caso bajo prueba.
    """
    cache.clear()
    yield
    cache.clear()
