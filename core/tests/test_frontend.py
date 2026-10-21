"""Tests del cliente de demostracion.

**Lo que se verifica aqui no es la interfaz, es la frontera.** El cliente existe
para evidenciar que el backend es headless: si Django renderizara datos de
negocio en la plantilla, esa demostracion seria falsa. `TestPlantillaSinDatos`
comprueba mecanicamente que no lo hace.

Hasta E2-M3a este modulo probaba tambien que el admin de las cuentas y
transacciones fuera de solo lectura. Esos modelos ya no viven en el monolito
(ADR-08), asi que esas pruebas se fueron con ellos.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent
PLANTILLA = RAIZ / "frontend" / "app.html"

# Etiquetas de plantilla de Django que **interpolan** algo. `{% ... %}` de
# control quedaria fuera de este patron, pero tampoco hay ninguna: el test de
# ausencia total esta mas abajo.
INTERPOLACION_DJANGO = re.compile(r"\{\{.*?\}\}", re.DOTALL)
BLOQUE_DJANGO = re.compile(r"\{%.*?%\}", re.DOTALL)


@pytest.fixture
def html():
    """Contenido de la plantilla, leido del disco."""
    return PLANTILLA.read_text(encoding="utf-8")


class TestSeSirveElCliente:
    """`GET /` entrega el cliente."""

    def test_devuelve_200(self, client):
        assert client.get("/").status_code == 200

    def test_sirve_html(self, client):
        assert client.get("/")["Content-Type"].startswith("text/html")

    def test_no_exige_autenticacion(self, client):
        """Sin token ni sesion: la pagina es publica, los datos no."""
        respuesta = client.get("/")

        assert respuesta.status_code == 200
        assert "Authorization" not in respuesta.request.get("headers", {})

    def test_contiene_los_paneles_esperados(self, client):
        cuerpo = client.get("/").content.decode("utf-8")

        for identificador in (
            'id="panel-auth"',
            'id="panel-cuentas"',
            'id="panel-movimientos"',
            'id="registro"',
            'id="avisos"',
        ):
            assert identificador in cuerpo, f"falta {identificador}"

    def test_contiene_las_cuatro_etiquetas_de_procedencia(self, client):
        """Las cuatro procedencias tienen estilo propio (C-19 y A-14)."""
        cuerpo = client.get("/").content.decode("utf-8")

        for clase in ("origen-rule", "origen-ai", "origen-mock", "origen-manual"):
            assert clase in cuerpo, f"falta el estilo {clase}"

    def test_muestra_las_dos_columnas_de_saldo(self, client):
        """La distincion que motivo la correccion C-17, visible en pantalla."""
        cuerpo = client.get("/").content.decode("utf-8")

        assert "Apertura" in cuerpo
        assert "Saldo actual" in cuerpo


class TestPlantillaSinDatos:
    """El cliente es headless: Django sirve el archivo, no lo rellena."""

    def test_no_interpola_variables_de_django(self, html):
        """Garantia mecanica: cero `{{ ... }}` en la plantilla."""
        encontradas = INTERPOLACION_DJANGO.findall(html)

        assert not encontradas, (
            f"La plantilla interpola datos con etiquetas de Django: {encontradas}. "
            f"El cliente debe pedir todo a /api/v1/; si Django rellena la pagina, "
            f"la demostracion de que el backend es headless deja de ser cierta."
        )

    def test_no_usa_bloques_de_plantilla(self, html):
        encontrados = BLOQUE_DJANGO.findall(html)

        assert not encontrados, (
            f"La plantilla usa bloques de Django: {encontrados}"
        )

    def test_la_vista_no_aporta_contexto(self):
        """`TemplateView` pelado: sin `get_context_data` sobreescrito."""
        from django.urls import resolve

        vista = resolve("/").func.view_class

        assert vista.__name__ == "TemplateView"
        assert "get_context_data" not in vista.__dict__

    def test_pide_los_datos_a_la_api(self, html):
        assert 'var BASE = "/api/v1"' in html

    def test_no_carga_recursos_externos(self, html):
        """Sin CDN: la sala de sustentacion puede no tener red."""
        externos = re.findall(r'(?:src|href)\s*=\s*["\'](https?:)?//', html)

        assert not externos, f"La pagina carga recursos externos: {externos}"

    def test_es_un_solo_archivo(self):
        archivos = sorted(p.name for p in (RAIZ / "frontend").iterdir() if p.is_file())

        assert archivos == ["app.html"]
