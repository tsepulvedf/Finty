"""Estaticos con nombres con hash (ADR-11, E2-M8b).

Corre `collectstatic` de verdad con el almacen de produccion, en un directorio
temporal, y comprueba que un despliegue nuevo no pueda servir JavaScript viejo:
cada archivo tiene su nombre con hash y los `import` de los modulos apuntan a
los nombres con hash de sus dependencias.
"""
import json
import re
from pathlib import Path

import pytest
from django.core.management import call_command

from config import settings as configuracion

RAIZ = Path(__file__).resolve().parent.parent.parent
HASH = r"\.[0-9a-f]{12}\."


@pytest.fixture
def recolectado(settings, tmp_path):
    settings.STATIC_ROOT = tmp_path
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "config.storage.FintyStaticFilesStorage"},
    }
    call_command("collectstatic", interactive=False, verbosity=0)
    manifiesto = json.loads((tmp_path / "staticfiles.json").read_text(encoding="utf-8"))["paths"]
    return tmp_path, manifiesto


def test_produccion_usa_el_almacen_con_hash():
    """Lo que dice `config/settings.py` (los demas tests usan el almacen simple)."""
    assert configuracion.STORAGES["staticfiles"]["BACKEND"] == "config.storage.FintyStaticFilesStorage"


def test_cada_js_y_css_tiene_nombre_con_hash(recolectado):
    _, manifiesto = recolectado
    propios = [n for n in manifiesto if n.startswith("finty/") and n.endswith((".js", ".css"))]
    assert "finty/js/api.js" in propios and "finty/css/finty.css" in propios
    for nombre in propios:
        assert re.search(HASH + r"(js|css)$", manifiesto[nombre]), nombre


def test_los_import_de_los_modulos_apuntan_a_nombres_con_hash(recolectado):
    raiz, manifiesto = recolectado
    pagina = (raiz / manifiesto["finty/js/pages/investments.js"]).read_text(encoding="utf-8")
    importados = re.findall(r'from\s+"([^"]+)"', pagina)
    assert importados
    for ruta in importados:
        assert re.search(HASH + "js$", ruta), f"import sin hash: {ruta}"


def test_la_tipografia_del_css_tambien_lleva_hash(recolectado):
    raiz, manifiesto = recolectado
    css = (raiz / manifiesto["finty/css/finty.css"]).read_text(encoding="utf-8")
    fuentes = re.findall(r"url\(['\"]?([^'\")]+\.woff2)", css)
    assert fuentes and all(re.search(HASH + "woff2$", f) for f in fuentes)


def test_la_pagina_enlaza_los_nombres_con_hash(client, recolectado):
    _, manifiesto = recolectado
    html = client.get("/dashboard/").content.decode("utf-8")
    assert "/static/" + manifiesto["finty/js/pages/dashboard.js"] in html
    assert "/static/" + manifiesto["finty/css/finty.css"] in html
