"""Reglas de capas de categorization-service, sobre el AST (A-16 y equivalentes).

- A-16: `domain/` es Python puro: solo stdlib y el propio dominio.
- A-02: el blueprint no contiene `try` ni aritmetica, ni toca el dominio.
- A-10: `services.py` no conoce implementaciones concretas ni la fabrica; quien
  elige es el blueprint (DIP).
"""
import ast
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parent.parent
FRAMEWORKS = {"flask", "werkzeug", "pydantic", "pydantic_core", "gunicorn"}


def tree_of(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_roots(tree):
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def imported_names(tree):
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }


DOMAIN_FILES = sorted(
    p for p in (SERVICE_ROOT / "domain").rglob("*.py") if "__pycache__" not in p.parts
)


class TestPurezaDelDominio:
    def test_hay_modulos_de_dominio(self):
        assert len(DOMAIN_FILES) >= 6

    @pytest.mark.parametrize("path", DOMAIN_FILES, ids=lambda p: p.relative_to(SERVICE_ROOT).as_posix())
    def test_solo_conoce_la_stdlib_y_el_dominio(self, path):
        foreign = {
            root
            for root in imported_roots(tree_of(path))
            if root != "domain" and root not in sys.stdlib_module_names
        }
        assert not foreign, f"importa {sorted(foreign)}"


class TestBlueprintSinLogica:
    ROUTES = SERVICE_ROOT / "api" / "routes.py"

    def test_cero_bloques_try(self):
        assert not [n for n in ast.walk(tree_of(self.ROUTES)) if isinstance(n, ast.Try)]

    def test_cero_aritmetica(self):
        arithmetic = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
        assert not [
            n for n in ast.walk(tree_of(self.ROUTES))
            if isinstance(n, ast.BinOp) and isinstance(n.op, arithmetic)
        ]

    def test_no_toca_el_dominio(self):
        assert "domain" not in imported_roots(tree_of(self.ROUTES))


class TestServiciosSinImplementacionesConcretas:
    def test_no_importa_categorizadores_ni_la_fabrica(self):
        names = imported_names(tree_of(SERVICE_ROOT / "services.py"))
        assert not names & {
            "AICategorizer", "RuleBasedCategorizer", "MockCategorizer", "CategorizerFactory",
        }

    def test_sin_frameworks(self):
        assert not imported_roots(tree_of(SERVICE_ROOT / "services.py")) & FRAMEWORKS
