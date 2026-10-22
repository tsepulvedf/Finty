"""Verifica los enlaces internos de la Wiki (`docs/wiki/`), sin red (E2-M9b).

Comprueba tres tipos de enlace y sale con codigo 1 si alguno esta roto:

- A otra pagina (`[texto](Pagina)` o `[texto](Pagina#seccion)`): la pagina debe
  existir en `docs/wiki/` y la seccion debe ser un titulo de esa pagina.
- A una seccion de la misma pagina (`[texto](#seccion)`).
- Al codigo en GitHub (`https://github.com/tsepulvedf/Finty/blob/main/<ruta>#L<n>`
  o `/tree/main/<ruta>`): la ruta debe existir en el repositorio y la linea, en el
  archivo. Si el texto del enlace es un identificador entre comillas invertidas
  (por ejemplo `` `CategorizerFactory` ``), ademas debe aparecer en esa linea: asi
  una cita deja de pasar en cuanto el codigo se mueve.

Los enlaces externos (otros dominios) no se visitan.

    python tools/check_wiki_links.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "docs" / "wiki"
REPO_URL = re.compile(r"^https://github\.com/tsepulvedf/Finty/(?:blob|tree)/main/([^#]+?)(?:#L(\d+))?$")
LINK = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
IDENTIFIER = re.compile(r"^`([A-Za-z_][A-Za-z0-9_]*)`$")


def slug(heading):
    """Ancla de un titulo, como la genera GitHub."""
    text = re.sub(r"[`*]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text):
    return {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+?)\s*$", FENCE.sub("", text), re.M)}


def links(text):
    """Enlaces fuera de los bloques de codigo, con su numero de linea."""
    without_fences = FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for number, line in enumerate(without_fences.splitlines(), start=1):
        for match in LINK.finditer(line):
            yield number, match.group(1), match.group(2)


def check_repo_link(label, path, line):
    target = ROOT / path
    if not target.exists():
        return f"no existe {path}"
    if line is None:
        return None
    if target.is_dir():
        return f"{path} es una carpeta y no tiene linea {line}"
    lines = target.read_text(encoding="utf-8").splitlines()
    if not 1 <= int(line) <= len(lines):
        return f"{path} tiene {len(lines)} lineas, no {line}"
    name = IDENTIFIER.match(label.strip())
    if name and name.group(1) not in lines[int(line) - 1]:
        return f"{path}:{line} ya no contiene {name.group(1)}"
    return None


def check_page(page, pages):
    text = page.read_text(encoding="utf-8")
    own = anchors(text)
    errors = []
    for number, label, href in links(text):
        problem = None
        repo = REPO_URL.match(href)
        if repo:
            problem = check_repo_link(label, repo.group(1), repo.group(2))
        elif href.startswith(("http://", "https://", "mailto:")):
            continue
        elif href.startswith("#"):
            if href[1:] not in own:
                problem = f"la seccion {href} no existe en la pagina"
        else:
            name, _, anchor = href.partition("#")
            if name not in pages:
                problem = f"la pagina {name} no existe en docs/wiki/"
            elif anchor and anchor not in anchors(pages[name]):
                problem = f"la seccion #{anchor} no existe en {name}"
        if problem:
            errors.append(f"{page.relative_to(ROOT).as_posix()}:{number}: [{label}]({href}): {problem}")
    return errors


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pages = {p.stem: p.read_text(encoding="utf-8") for p in WIKI.glob("*.md")}
    errors = []
    checked = 0
    for page in sorted(WIKI.glob("*.md")):
        checked += 1
        errors.extend(check_page(page, pages))
    for error in errors:
        print("ROTO", error)
    print(f"{checked} paginas revisadas, {len(errors)} enlaces rotos")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
