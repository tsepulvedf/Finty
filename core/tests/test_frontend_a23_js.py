"""A-23 en JavaScript (E2-M8b): ningun texto visible se arma con literales.

Todo texto que el JavaScript pone en pantalla sale de `gettext()` / `ngettext()`
o del modulo de codigos (`js/codes.js`, que traduce los `code` de la API con
gettext). El test lee cada modulo con un analizador lexico pequeño: separa
comentarios, cadenas y plantillas, descarta los argumentos de gettext y marca
las cadenas que se leen como texto para una persona.

Una cadena tecnica (clases CSS, ids, rutas, codigos de la API, nombres de
cabeceras HTTP) no es texto visible: va en minusculas con guiones, en
mayusculas o en la lista de permitidas.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent
JS = RAIZ / "frontend" / "static" / "finty" / "js"
MODULOS = sorted(p for p in JS.rglob("*.js") if p.name != "codes.js")

# Cabeceras HTTP y nombres de teclas: tecnicos aunque empiecen con mayuscula.
PERMITIDAS = {"Authorization", "Content-Type", "Accept", "Token", "Escape", "HTTP"}
PALABRAS_DE_TEXTO = {
    "de", "del", "la", "el", "los", "las", "en", "y", "o", "con", "sin", "por", "para", "tu", "tus", "un", "una",
    "the", "of", "and", "or", "in", "to", "with", "for", "your", "a", "an", "is",
}
# El atributo `d` de un trazo SVG: comandos de una letra y numeros.
TRAZO_SVG = re.compile(r"[MmLlHhVvCcSsQqTtAaZz][MmLlHhVvCcSsQqTtAaZz0-9.,\s-]*")
GETTEXT = re.compile(r"(?<![\w.$])n?gettext\(\s*$")


def es_inicio_de_regex(fuente, i):
    """Un `/` abre una expresion regular si lo precede un operador, un
    delimitador o `return` (y no un valor, como en una division)."""
    antes = fuente[:i].rstrip()
    return not antes or antes[-1] in "(,=:[!&|?{};+-*%<>~^" or re.search(r"\breturn$", antes) is not None


def fin_de_regex(fuente, i):
    """Posicion despues del `/` que cierra la regex que empieza en `i` (y sus
    banderas). Las comillas dentro de la regex no abren cadenas."""
    j, en_clase = i + 1, False
    while j < len(fuente) and fuente[j] != "\n":
        d = fuente[j]
        if d == "\\":
            j += 2
            continue
        if d == "[":
            en_clase = True
        elif d == "]":
            en_clase = False
        elif d == "/" and not en_clase:
            j += 1
            while j < len(fuente) and fuente[j].isalpha():
                j += 1
            return j
        j += 1
    return j


def literales(fuente):
    """`[(texto, linea)]` de cada cadena y plantilla de `fuente` que no es
    argumento de gettext/ngettext. En las plantillas, `${...}` se descarta."""
    encontrados = []
    i, n, linea = 0, len(fuente), 1
    dentro_de_gettext = 0  # cadenas pendientes como argumento de gettext/ngettext
    while i < n:
        c = fuente[i]
        if c == "\n":
            linea += 1
        if fuente.startswith("//", i):
            fin = fuente.find("\n", i)
            i = n if fin < 0 else fin
            continue
        if fuente.startswith("/*", i):
            fin = fuente.find("*/", i + 2)
            linea += fuente.count("\n", i, fin)
            i = n if fin < 0 else fin + 2
            continue
        if c == "/" and es_inicio_de_regex(fuente, i):
            i = fin_de_regex(fuente, i)
            continue
        if c in "\"'`":
            inicio, texto, j, profundidad = linea, [], i + 1, 0
            while j < n:
                d = fuente[j]
                if d == "\\":
                    texto.append(fuente[j:j + 2])
                    j += 2
                    continue
                if d == "\n":
                    linea += 1
                if c == "`" and fuente.startswith("${", j):
                    profundidad, j = 1, j + 2
                    while j < n and profundidad:
                        profundidad += {"{": 1, "}": -1}.get(fuente[j], 0)
                        j += 1
                    texto.append(" ")
                    continue
                if d == c:
                    break
                texto.append(d)
                j += 1
            antes = fuente[max(0, i - 40):i]
            if GETTEXT.search(antes):
                # Primer argumento de gettext/ngettext; ngettext trae un segundo.
                dentro_de_gettext = 1 if "ngettext(" in antes[-12:] else 0
            elif dentro_de_gettext and re.search(r",\s*$", antes):
                dentro_de_gettext = 0
            else:
                encontrados.append(("".join(texto), inicio))
            i = j + 1
            continue
        i += 1
    return encontrados


def parece_texto(cadena):
    """True si la cadena se lee como texto para una persona."""
    limpia = cadena.strip()
    if not re.search(r"[^\W\d_]", limpia) or limpia in PERMITIDAS:
        return False
    if TRAZO_SVG.fullmatch(limpia):
        return False
    if re.search(r"[áéíóúñÁÉÍÓÚÑ¿¡]", limpia):
        return True
    if re.search(r"(?<![\w-])[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?![\w-])", limpia) and limpia not in PERMITIDAS:
        return True
    palabras = re.findall(r"[a-záéíóúñ]+", limpia.lower())
    return len(palabras) > 1 and " " in limpia and any(p in PALABRAS_DE_TEXTO for p in palabras) and not re.search(r"--|__", limpia)


def textos_quemados(fuente):
    return [(texto, linea) for texto, linea in literales(fuente) if parece_texto(texto)]


class TestA23JavaScript:
    def test_hay_modulos_que_revisar(self):
        nombres = {p.name for p in MODULOS}
        assert {"api.js", "dom.js", "format.js", "shell.js", "checkout.js", "investments.js", "settings.js"} <= nombres

    @pytest.mark.parametrize("modulo", MODULOS, ids=lambda p: p.relative_to(JS).as_posix())
    def test_ningun_texto_visible_con_literales(self, modulo):
        hallazgos = textos_quemados(modulo.read_text(encoding="utf-8"))
        assert not hallazgos, f"{modulo.name}: texto sin gettext(): {hallazgos}"

    def test_codes_traduce_cada_valor_con_gettext(self):
        """codes.js: las claves son codigos o nombres de la API; los valores de
        texto pasan por gettext()."""
        fuente = (JS / "codes.js").read_text(encoding="utf-8")
        valores = re.findall(r"^\s+[\w\"'áéíóúñÁÉÍÓÚÑ ]+:\s*(\"[^\"]*\"|'[^']*'),?\s*$", fuente, re.MULTILINE)
        assert not valores, f"valores de codes.js sin gettext(): {valores}"

    @pytest.mark.parametrize("fuente, esperado", [
        ('el.textContent = "Hola mundo";', ["Hola mundo"]),
        ('h("p", null, "Sin movimientos")', ["Sin movimientos"]),
        ("h('span', {}, 'Guardado')", ["Guardado"]),
        ('const t = `Total de ${n} cuentas`;', ["Total de   cuentas"]),
        ('x = "monto en la cuenta";', ["monto en la cuenta"]),
        ('el.textContent = gettext("Hola mundo");', []),
        ('format(ngettext("%(n)s cuenta", "%(n)s cuentas", n), {})', []),
        ('h("div", { class: "btn btn--primary", id: "tx-list" })', []),
        ('api("/subscriptions/checkout/", { method: "POST" })', []),
        ('headers["Content-Type"] = "application/json"; `Token ${token()}`', []),
        ('// Comentario con "Texto en una cadena"\nconst a = 1;', []),
        ('/* Bloque "Con texto" */ const b = "PREMIUM";', []),
        ('svg.setAttribute("viewBox", "0 0 24 24")', []),
        ('path.setAttribute("d", "M3 6h18v12H3zM12 9.5a2.5 2.5 0 110 5")', []),
        ('const m = /filename="([^"]+)"/.exec(x); el.textContent = "Hola mundo";', ["Hola mundo"]),
        ("const r = a / b; const s = c / d; t.textContent = 'Sin datos';", ["Sin datos"]),
        ('return /^[\\w"]+$/.test(v) ? "ok" : "Texto con error";', ["Texto con error"]),
    ])
    def test_el_detector_distingue_lo_traducido(self, fuente, esperado):
        assert [texto for texto, _ in textos_quemados(fuente)] == esperado
