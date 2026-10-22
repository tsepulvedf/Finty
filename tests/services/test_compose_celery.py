"""Convencion de Celery en Compose (E2-M7, ADR-15).

Lee la configuracion ya resuelta (`docker compose config --format json`, con los
anclajes aplicados). Si Docker no esta instalado, se omite.

- Cada contenedor de Celery usa la imagen de su servicio, no publica puertos y
  tiene `restart: unless-stopped`.
- Un solo beat por servicio.
- El broker esta en una base logica de Redis distinta de la del stream y las
  caches (`REDIS_URL`).
- Cada worker consume solo la cola de su servicio.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DOCKER = shutil.which("docker")

CELERY = {
    "analytics": {"worker": "analytics-celery", "beat": "analytics-celery-beat", "web": "analytics-service"},
    "subscription": {"worker": "subscription-worker", "beat": "subscription-beat", "web": "subscription-service"},
}

pytestmark = pytest.mark.skipif(DOCKER is None, reason="Docker no esta instalado")


@pytest.fixture(scope="module")
def services():
    result = subprocess.run(
        [DOCKER, "compose", "config", "--format", "json"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(f"docker compose config fallo: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout)["services"]


def command(service):
    return service.get("command") or []


def database(url):
    return url.rsplit("/", 1)[-1]


@pytest.mark.parametrize("queue, names", CELERY.items())
class TestContenedores:
    def test_misma_imagen_que_el_servicio(self, services, queue, names):
        image = services[names["web"]]["image"]
        assert services[names["worker"]]["image"] == image
        assert services[names["beat"]]["image"] == image

    def test_sin_puertos_y_con_reinicio(self, services, queue, names):
        for name in (names["worker"], names["beat"]):
            assert not services[name].get("ports"), name
            assert services[name]["restart"] == "unless-stopped", name

    def test_el_worker_consume_solo_su_cola(self, services, queue, names):
        args = command(services[names["worker"]])
        assert args[:4] == ["celery", "-A", "celery_app:celery", "worker"]
        assert args[args.index("-Q") + 1] == queue

    def test_broker_en_otra_base_que_el_stream_y_las_caches(self, services, queue, names):
        environment = services[names["worker"]]["environment"]
        broker = environment["CELERY_BROKER_URL"]
        assert broker.startswith("redis://redis:6379/")
        assert database(broker) != database(environment.get("REDIS_URL", "redis://redis:6379/0"))
        assert services[names["web"]]["environment"]["CELERY_BROKER_URL"] == broker


def test_un_solo_beat_por_servicio(services):
    beats = {}
    for name, service in services.items():
        args = command(service)
        if args[:4] == ["celery", "-A", "celery_app:celery", "beat"]:
            beats.setdefault(service["image"], []).append(name)
    assert beats == {
        services["analytics-service"]["image"]: ["analytics-celery-beat"],
        services["subscription-service"]["image"]: ["subscription-beat"],
    }


def test_el_worker_de_eventos_de_analytics_sigue(services):
    assert command(services["analytics-worker"]) == ["flask", "consume-events"]
