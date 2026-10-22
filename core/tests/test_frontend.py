"""Tests del frontend (ADR-11, E2-M8a).

Tres cosas, todas mecanicas:

1. **Las paginas se sirven** en espanol y en ingles, y el selector ES/EN cambia
   el idioma con la cookie de Django.
2. **La frontera se mantiene:** las vistas son `TemplateView` sin contexto y las
   plantillas solo interpolan el idioma y la ruta actual. Todo dato de negocio lo
   pide el JavaScript a /api/v1/. Y nada se carga de otro origen.
3. **A-23, primer tramo:** ninguna plantilla de `frontend/templates/finty/` tiene
   texto visible fuera de `{% translate %}` o `{% blocktranslate %}`, y los
   catalogos `es` y `en` estan completos. E2-M8b extiende la cobertura.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.urls import resolve

RAIZ = Path(__file__).resolve().parent.parent.parent
FRONTEND = RAIZ / "frontend"
PLANTILLAS = sorted((FRONTEND / "templates" / "finty").glob("*.html"))
JAVASCRIPT = sorted((FRONTEND / "static" / "finty" / "js").rglob("*.js"))
LOCALE = RAIZ / "locale"

PAGINAS = ["/", "/registro/", "/dashboard/", "/movimientos/"]
IDIOMAS = ["es", "en"]
COOKIE_IDIOMA = "django_language"


def html_de(client, url, idioma):
    client.cookies[COOKIE_IDIOMA] = idioma
    respuesta = client.get(url)
    return respuesta, respuesta.content.decode("utf-8")


class TestPaginas:
    @pytest.mark.parametrize("idioma", IDIOMAS)
    @pytest.mark.parametrize("url", PAGINAS)
    def test_cada_pagina_responde_200_en_ambos_idiomas(self, client, url, idioma):
        respuesta, html = html_de(client, url, idioma)

        assert respuesta.status_code == 200
        assert respuesta["Content-Type"].startswith("text/html")
        assert f'<html lang="{idioma}">' in html

    @pytest.mark.parametrize("url", PAGINAS)
    def test_no_exigen_autenticacion(self, client, url):
        """La pagina es publica; los datos no. Sin token, el JavaScript lleva al ingreso."""
        assert client.get(url).status_code == 200

    def test_sin_cookie_el_idioma_es_espanol(self, client):
        html = client.get("/").content.decode("utf-8")
        assert '<html lang="es">' in html

    def test_cada_pagina_carga_su_modulo(self, client):
        for url, modulo in zip(PAGINAS, ["login", "register", "dashboard", "transactions"]):
            html = client.get(url).content.decode("utf-8")
            assert f"finty/js/pages/{modulo}.js" in html
            assert "/jsi18n/" in html

    def test_las_urls_de_pagina_no_chocan_con_las_de_la_api(self, client):
        """`login` y `register` ya son nombres de la API de identity: las paginas
        usan `page-*`. Si chocaran, cerrar sesion llevaria a /api/v1/auth/login/."""
        html = client.get("/dashboard/").content.decode("utf-8")
        for atributo, ruta in [
            ("data-url-login", "/"), ("data-url-register", "/registro/"),
            ("data-url-dashboard", "/dashboard/"), ("data-url-transactions", "/movimientos/"),
        ]:
            assert f'{atributo}="{ruta}"' in html

    @pytest.mark.parametrize("url, enlace", [("/dashboard/", "/dashboard/"), ("/movimientos/", "/movimientos/")])
    def test_la_navegacion_marca_la_pagina_actual(self, client, url, enlace):
        html = client.get(url).content.decode("utf-8")
        assert f'<a href="{enlace}" aria-current="page">' in html

    def test_el_catalogo_de_javascript_se_sirve(self, client):
        respuesta = client.get("/jsi18n/")
        assert respuesta.status_code == 200
        assert "gettext" in respuesta.content.decode("utf-8")


class TestSelectorDeIdioma:
    def test_cambia_el_idioma_y_lo_guarda_en_la_cookie(self, client):
        respuesta = client.post("/i18n/setlang/", {"language": "en", "next": "/dashboard/"})

        assert respuesta.status_code == 302
        assert respuesta["Location"] == "/dashboard/"
        assert respuesta.cookies[COOKIE_IDIOMA].value == "en"
        assert '<html lang="en">' in client.get("/dashboard/").content.decode("utf-8")

    def test_vuelve_a_espanol(self, client):
        client.post("/i18n/setlang/", {"language": "en", "next": "/"})
        client.post("/i18n/setlang/", {"language": "es", "next": "/"})
        assert '<html lang="es">' in client.get("/").content.decode("utf-8")

    @pytest.mark.parametrize("idioma", IDIOMAS)
    def test_el_boton_del_idioma_activo_esta_presionado(self, client, idioma):
        _, html = html_de(client, "/", idioma)
        assert re.search(rf'value="{idioma}"[^>]*aria-pressed="true"', html)

    def test_el_selector_vuelve_a_la_pagina_actual(self, client):
        html = client.get("/movimientos/").content.decode("utf-8")
        assert 'name="next" value="/movimientos/"' in html


class TestFrontera:
    """Django sirve plantillas, no datos: el backend sigue siendo headless."""

    VARIABLES_PERMITIDAS = {"LANG", "request.get_full_path"}

    @pytest.mark.parametrize("url", PAGINAS)
    def test_las_vistas_no_aportan_contexto(self, url):
        vista = resolve(url).func.view_class
        assert vista.__name__ == "TemplateView"
        assert "get_context_data" not in vista.__dict__

    @pytest.mark.parametrize("plantilla", PLANTILLAS, ids=lambda p: p.name)
    def test_solo_interpolan_el_idioma_y_la_ruta(self, plantilla):
        variables = set(re.findall(r"\{\{\s*([\w.]+)", plantilla.read_text(encoding="utf-8")))
        assert variables <= self.VARIABLES_PERMITIDAS, variables - self.VARIABLES_PERMITIDAS

    def test_el_javascript_pide_los_datos_a_la_api(self):
        api = (FRONTEND / "static" / "finty" / "js" / "api.js").read_text(encoding="utf-8")
        assert 'const BASE = "/api/v1";' in api

    def test_no_carga_recursos_externos(self):
        """Sin CDN ni Google Fonts: la sala de sustentacion puede no tener red."""
        archivos = PLANTILLAS + JAVASCRIPT + sorted((FRONTEND / "static").rglob("*.css"))
        externos = [
            (archivo.name, url)
            for archivo in archivos
            for url in re.findall(r"""(?:src|href|url)\s*[=(]\s*["']?(https?:)?//""", archivo.read_text(encoding="utf-8"))
        ]
        assert not externos

    def test_la_tipografia_se_sirve_desde_el_proyecto(self):
        fuentes = FRONTEND / "static" / "finty" / "fonts"
        assert (fuentes / "manrope-latin-wght-normal.woff2").stat().st_size > 10_000
        assert "SIL Open Font License" in (fuentes / "OFL.txt").read_text(encoding="utf-8")

    def test_app_html_ya_no_existe(self):
        assert not (FRONTEND / "app.html").exists()


# --- A-23: cero textos quemados ------------------------------------------------------

# Codigos que se leen igual en todos los idiomas: idioma y moneda.
INVARIANTES = {"ES", "EN", "COP", "USD"}
ATRIBUTOS_VISIBLES = {"aria-label", "placeholder", "title", "alt", "label"}
# Una letra de cualquier alfabeto; deja fuera simbolos como ×, ‹ o ·.
LETRA = re.compile(r"[^\W\d_]")

COMENTARIO = re.compile(r"\{#.*?#\}|\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL)
TRADUCCION = re.compile(
    r"\{%\s*translate\b.*?%\}|\{%\s*blocktranslate\b.*?%\}.*?\{%\s*endblocktranslate\s*%\}",
    re.DOTALL,
)
ETIQUETA_DJANGO = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.DOTALL)


class _TextoVisible(HTMLParser):
    """Recoge texto y atributos visibles que quedan tras quitar lo traducido."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hallazgos = []
        self._oculto = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._oculto += 1
        for nombre, valor in attrs:
            if nombre in ATRIBUTOS_VISIBLES and valor and self._sin_traducir(valor):
                self.hallazgos.append(f'{tag}[{nombre}="{valor}"]')

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._oculto:
            self._oculto -= 1

    def handle_data(self, data):
        if not self._oculto and self._sin_traducir(data):
            self.hallazgos.append(data.strip())

    @staticmethod
    def _sin_traducir(texto):
        limpio = texto.strip()
        return bool(LETRA.search(limpio)) and limpio not in INVARIANTES


def textos_sin_traducir(fuente):
    """Texto visible de una plantilla que no pasa por gettext."""
    sin_comentarios = COMENTARIO.sub("", fuente)
    sin_traducciones = TRADUCCION.sub("", sin_comentarios)
    sin_etiquetas = ETIQUETA_DJANGO.sub("", sin_traducciones)
    analizador = _TextoVisible()
    analizador.feed(sin_etiquetas)
    return analizador.hallazgos


class TestA23SinTextosQuemados:
    def test_hay_plantillas_que_revisar(self):
        assert {p.name for p in PLANTILLAS} >= {
            "base.html", "app_base.html", "login.html", "register.html", "dashboard.html", "transactions.html",
        }

    @pytest.mark.parametrize("plantilla", PLANTILLAS, ids=lambda p: p.name)
    def test_ningun_texto_visible_sin_traducir(self, plantilla):
        hallazgos = textos_sin_traducir(plantilla.read_text(encoding="utf-8"))
        assert not hallazgos, f"{plantilla.name}: texto sin {{% translate %}}: {hallazgos}"

    @pytest.mark.parametrize("fragmento, esperado", [
        ("<p>Hola</p>", ["Hola"]),
        ('<input placeholder="Buscar">', ['input[placeholder="Buscar"]']),
        ('<button aria-label="Cerrar">×</button>', ['button[aria-label="Cerrar"]']),
        ("<p>{% translate 'Hola' %}</p>", []),
        ("<p>{% blocktranslate %}Hola {{ x }}{% endblocktranslate %}</p>", []),
        ('<input placeholder="{% translate \'Buscar\' %}">', []),
        ("<option>COP</option><script>const x = 'Hola';</script>", []),
        ("<span>{# comentario #}</span>", []),
    ])
    def test_el_detector_distingue_lo_traducido(self, fragmento, esperado):
        assert textos_sin_traducir(fragmento) == esperado


def entradas_po(ruta):
    """`{msgid: [msgstr...]}` de un .po (une las lineas de continuacion)."""
    entradas, actual, campo = {}, None, None
    for linea in ruta.read_text(encoding="utf-8").splitlines() + [""]:
        if not linea.strip():
            if actual and actual["msgid"]:
                entradas[actual["msgid"]] = actual
            actual, campo = None, None
            continue
        if linea.startswith("#"):
            actual = actual or {"msgid": "", "msgstr": [], "fuzzy": False}
            actual["fuzzy"] = actual["fuzzy"] or (linea.startswith("#,") and "fuzzy" in linea)
            continue
        actual = actual or {"msgid": "", "msgstr": [], "fuzzy": False}
        clave, _, valor = linea.partition(" ")
        if linea.startswith('"'):
            texto = linea[1:-1]
            if campo == "msgid":
                actual["msgid"] += texto
            elif campo == "msgstr":
                actual["msgstr"][-1] += texto
        elif clave == "msgid":
            campo, actual["msgid"] = "msgid", valor[1:-1]
        elif clave == "msgid_plural":
            campo = "plural"
        elif clave.startswith("msgstr"):
            campo = "msgstr"
            actual["msgstr"].append(valor[1:-1])
    return entradas


def literales(patron, archivos):
    return {
        texto.replace('\\"', '"')
        for archivo in archivos
        for texto in re.findall(patron, archivo.read_text(encoding="utf-8"))
    }


class TestCatalogos:
    @pytest.mark.parametrize("idioma", IDIOMAS)
    @pytest.mark.parametrize("dominio", ["django", "djangojs"])
    def test_completo_y_sin_borradores(self, idioma, dominio):
        entradas = entradas_po(LOCALE / idioma / "LC_MESSAGES" / f"{dominio}.po")
        assert entradas
        vacias = [msgid for msgid, e in entradas.items() if not all(e["msgstr"]) or e["fuzzy"]]
        assert not vacias, f"{idioma}/{dominio}: sin traducir o fuzzy: {vacias}"

    def test_cada_texto_de_las_plantillas_esta_en_el_catalogo(self):
        textos = {
            doble or simple
            for plantilla in PLANTILLAS
            for doble, simple in re.findall(r"""\{%\s*translate\s+(?:"([^"]*)"|'([^']*)')""", plantilla.read_text(encoding="utf-8"))
        }
        catalogo = entradas_po(LOCALE / "en" / "LC_MESSAGES" / "django.po")
        faltan = sorted(textos - set(catalogo))
        assert not faltan, f"falta correr makemessages: {faltan}"

    def test_cada_gettext_del_javascript_esta_en_el_catalogo(self):
        textos = literales(r'(?<![\w.])n?gettext\(\s*"((?:[^"\\]|\\.)*)"', JAVASCRIPT)
        catalogo = entradas_po(LOCALE / "en" / "LC_MESSAGES" / "djangojs.po")
        faltan = sorted(textos - set(catalogo))
        assert textos and not faltan, f"falta correr makemessages -d djangojs: {faltan}"

    def test_el_ingles_traduce_de_verdad(self):
        catalogo = entradas_po(LOCALE / "en" / "LC_MESSAGES" / "django.po")
        assert catalogo["Ingresa a tu cuenta"]["msgstr"] == ["Log in to your account"]
