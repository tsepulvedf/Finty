"""Reglas de capas de finance-service, verificadas sobre el AST.

Replica en el servicio los criterios del monolito (`core/tests/test_architecture.py`):

- **A-16**: `domain/` es Python puro: no importa Flask, SQLAlchemy, pydantic,
  Alembic ni nada del anillo externo del servicio.
- Equivalente de A-02: los blueprints no contienen `try` ni aritmetica.
- Equivalente de A-03: los modelos solo declaran columnas y `__repr__`.
- Equivalente de A-10: `services.py` no conoce implementaciones concretas.

Sin base de datos.
"""
import ast
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Paquetes del anillo externo del propio servicio que el dominio no puede ver.
OUTER_RING = {"api", "infra", "models", "services", "messages", "app", "migrations"}
FRAMEWORKS = {"flask", "werkzeug", "sqlalchemy", "alembic", "pydantic", "pydantic_core", "psycopg2"}


def python_files(package):
    return sorted(
        path
        for path in (SERVICE_ROOT / package).rglob("*.py")
        if "__pycache__" not in path.parts
    )


def tree_of(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_roots(tree):
    """Primer componente de cada modulo importado."""
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def relative(path):
    return path.relative_to(SERVICE_ROOT).as_posix()


DOMAIN_FILES = python_files("domain")


class TestPurezaDelDominio:
    """A-16."""

    def test_hay_modulos_de_dominio(self):
        assert len(DOMAIN_FILES) >= 7

    @pytest.mark.parametrize("path", DOMAIN_FILES, ids=relative)
    def test_no_importa_frameworks(self, path):
        assert not imported_roots(tree_of(path)) & FRAMEWORKS

    @pytest.mark.parametrize("path", DOMAIN_FILES, ids=relative)
    def test_no_importa_el_anillo_externo(self, path):
        assert not imported_roots(tree_of(path)) & OUTER_RING

    @pytest.mark.parametrize("path", DOMAIN_FILES, ids=relative)
    def test_solo_conoce_la_stdlib_y_el_dominio(self, path):
        foreign = {
            root
            for root in imported_roots(tree_of(path))
            if root != "domain" and root not in sys.stdlib_module_names
        }
        assert not foreign, f"{relative(path)} importa {sorted(foreign)}"


class TestBlueprintsSinLogica:
    """Equivalente de A-02 para `api/routes.py`."""

    ROUTES = SERVICE_ROOT / "api" / "routes.py"

    def test_cero_bloques_try(self):
        assert not [n for n in ast.walk(tree_of(self.ROUTES)) if isinstance(n, ast.Try)]

    def test_cero_aritmetica(self):
        arithmetic = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
        nodes = [
            n
            for n in ast.walk(tree_of(self.ROUTES))
            if isinstance(n, ast.BinOp) and isinstance(n.op, arithmetic)
        ]
        assert not nodes

    def test_no_toca_el_dominio_ni_los_modelos(self):
        roots = imported_roots(tree_of(self.ROUTES))
        assert not roots & {"domain", "models", "sqlalchemy"}


class TestModelosAnemicos:
    """Equivalente de A-03 para `models.py`."""

    ALLOWED_METHODS = {"__repr__"}

    def model_classes(self):
        tree = tree_of(SERVICE_ROOT / "models.py")
        return [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name != "Base"
        ]

    def test_hay_tres_modelos(self):
        assert {c.name for c in self.model_classes()} == {"Category", "Account", "Transaction"}

    def test_solo_declaran_repr(self):
        for model in self.model_classes():
            methods = {n.name for n in model.body if isinstance(n, ast.FunctionDef)}
            assert methods <= self.ALLOWED_METHODS, f"{model.name}: {methods}"

    def test_no_hay_decoradores_ni_listeners(self):
        tree = tree_of(SERVICE_ROOT / "models.py")
        decorated = [
            n.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.decorator_list
        ]
        assert not decorated
        assert "event" not in {
            alias.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
            for alias in n.names
        }


class TestServiciosSinImplementacionesConcretas:
    """Equivalente de A-10."""

    def test_no_importa_categorizadores_ni_la_fabrica(self):
        tree = tree_of(SERVICE_ROOT / "services.py")
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "infra.categorizers" not in modules
        assert "infra.factories" not in modules


class TestComandosSinLogica:
    """`commands.py` es un mecanismo de entrega, igual que un blueprint.

    Traslado de `TestComandosSinLogica` del monolito (E2-M3a): orquesta llamadas
    al servicio y formatea la salida, pero no calcula, no reimplementa reglas y
    no consulta la base.
    """

    COMMANDS = SERVICE_ROOT / "commands.py"

    def test_no_importa_el_dominio_ni_los_modelos(self):
        roots = imported_roots(tree_of(self.COMMANDS))
        assert not roots & {"domain", "models", "sqlalchemy", "infra"}

    def test_el_cuerpo_del_comando_no_hace_aritmetica(self):
        """Los anchos de columna se calculan fuera; el comando en si no suma."""
        tree = tree_of(self.COMMANDS)
        command = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "verify_invariants"
        )
        arithmetic = (ast.Add, ast.Sub, ast.Mult, ast.Div)
        assert not [
            n.lineno for n in ast.walk(command)
            if isinstance(n, ast.BinOp) and isinstance(n.op, arithmetic)
        ]

    def test_solo_usa_el_servicio_de_cuentas(self):
        tree = tree_of(self.COMMANDS)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "services"
            for alias in node.names
        }
        assert imported == {"AccountService"}
