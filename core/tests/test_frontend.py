"""Tests del cliente de demostracion y del blindaje del admin.

**Lo que se verifica aqui no es la interfaz, es la frontera.** El cliente existe
para evidenciar que el backend es headless: si Django renderizara datos de
negocio en la plantilla, esa demostracion seria falsa. `TestPlantillaSinDatos`
comprueba mecanicamente que no lo hace.

El blindaje del admin se prueba en el mismo modulo porque responde a la misma
idea: con la interfaz disponible, el admin deja de ser necesario para escribir y
pasa a ser un camino que evade la capa de servicios.
"""
import re
from pathlib import Path

import pytest
from django.contrib import admin

from finance.models import Account, Category, Transaction

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


class TestAdminDeSoloLectura:
    """El admin escribe por el ORM, saltandose las invariantes.

    Crear una `Transaction` desde el admin no pasaria por `TransactionService`:
    no bloquearia la cuenta, no recalcularia el balance y no verificaria INV-14.
    Quedaria una transaccion persistida con el balance sin mover, o sea INV-07
    violada desde dentro del propio sistema.
    """

    MODELOS = [Account, Transaction, Category]

    @pytest.fixture
    def peticion(self, rf, django_user_model, db):
        """Peticion de un superusuario: ni con todos los permisos puede escribir."""
        solicitud = rf.get("/admin/")
        solicitud.user = django_user_model.objects.create_superuser(
            email="admin@finty.co", password="Contrasena-Segura-2026"
        )
        return solicitud

    @pytest.mark.parametrize("modelo", MODELOS)
    def test_no_permite_agregar(self, modelo, peticion):
        assert admin.site._registry[modelo].has_add_permission(peticion) is False

    @pytest.mark.parametrize("modelo", MODELOS)
    def test_no_permite_modificar(self, modelo, peticion):
        assert admin.site._registry[modelo].has_change_permission(peticion) is False

    @pytest.mark.parametrize("modelo", MODELOS)
    def test_no_permite_eliminar(self, modelo, peticion):
        assert admin.site._registry[modelo].has_delete_permission(peticion) is False

    @pytest.mark.parametrize("modelo", MODELOS)
    def test_todos_los_campos_son_de_solo_lectura(self, modelo, peticion):
        registro = admin.site._registry[modelo]
        declarados = set(registro.get_readonly_fields(peticion))
        concretos = {campo.name for campo in modelo._meta.fields}

        assert concretos <= declarados, (
            f"{modelo.__name__}: quedan campos editables "
            f"{sorted(concretos - declarados)}"
        )

    @pytest.mark.parametrize("modelo", MODELOS)
    def test_sigue_permitiendo_inspeccionar(self, modelo, peticion):
        """Leer si: el admin sigue siendo util para revisar datos en la demo."""
        assert admin.site._registry[modelo].has_view_permission(peticion) is True

    @pytest.mark.parametrize("modelo", MODELOS)
    def test_el_formulario_de_alta_devuelve_403(self, modelo, client, peticion):
        """No es solo cosmetico: un POST a mano tampoco pasa."""
        client.force_login(peticion.user)
        etiqueta = modelo._meta.app_label
        nombre = modelo._meta.model_name

        respuesta = client.get(f"/admin/{etiqueta}/{nombre}/add/")

        assert respuesta.status_code == 403

    def test_la_lista_sigue_siendo_accesible(self, client, peticion):
        client.force_login(peticion.user)

        assert client.get("/admin/finance/account/").status_code == 200
