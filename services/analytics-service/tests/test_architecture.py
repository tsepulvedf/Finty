"""Reglas de capas de analytics-service, verificadas sobre el AST.

Replica en el servicio los criterios del monolito (`core/tests/test_architecture.py`):

- **A-16**: `domain/` es Python puro: no importa Flask, SQLAlchemy, pydantic,
  Alembic ni nada del anillo externo del servicio.
- Equivalente de A-02: los blueprints no contienen `try` ni aritmetica.
- Equivalente de A-03: los modelos solo declaran columnas y `__repr__`.
- Equivalente de A-10: `services.py` no conoce `infra/` ni Redis.
- E2-M7: las tareas de Celery (`tasks.py`) son un mecanismo de entrega: cada
  una solo arma el caso de uso y llama a un metodo publico de `services.py`.

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
        assert len(DOMAIN_FILES) >= 10

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

    def test_se_analizan_todos_los_modelos(self):
        assert {c.name for c in self.model_classes()} == {
            "TransactionFactRecord", "ProcessedEvent", "MonthlyReportRecord",
        }

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
    """Equivalente de A-10: los servicios reciben el origen de eventos por la ABC."""

    def test_no_importa_infra_ni_redis(self):
        roots = imported_roots(tree_of(SERVICE_ROOT / "services.py"))
        assert not roots & {"infra", "redis", "api", "flask"}


class TestComandosSinLogica:
    """`commands.py` es un mecanismo de entrega, igual que un blueprint:
    conecta el origen de eventos con el servicio, pero no proyecta nada."""

    COMMANDS = SERVICE_ROOT / "commands.py"

    def test_no_importa_el_dominio_ni_los_modelos(self):
        """Como un blueprint, conecta adaptadores de `infra/`, pero no toca el
        dominio, los modelos ni la base directamente."""
        roots = imported_roots(tree_of(self.COMMANDS))
        assert not roots & {"domain", "models", "sqlalchemy", "redis"}

    @pytest.mark.parametrize("name", ["consume_events"])
    def test_el_cuerpo_del_comando_no_hace_aritmetica(self, name):
        """Las esperas se calculan en `Backoff`; el comando en si no suma."""
        tree = tree_of(self.COMMANDS)
        command = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == name
        )
        arithmetic = (ast.Add, ast.Sub, ast.Mult, ast.Div)
        assert not [
            n.lineno for n in ast.walk(command)
            if isinstance(n, ast.BinOp) and isinstance(n.op, arithmetic)
        ]

    def test_solo_usa_servicios_de_mantenimiento(self):
        tree = tree_of(self.COMMANDS)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "services"
            for alias in node.names
        }
        assert imported == {"EventConsumer", "EventProjector"}


class TestTareasSinLogica:
    """E2-M7 (regla 3): una tarea de Celery recibe el mensaje y llama a un caso
    de uso de `services.py`; no consulta la base ni toca el dominio."""

    TASKS = SERVICE_ROOT / "tasks.py"

    def tasks(self):
        tree = tree_of(self.TASKS)
        return [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and any(isinstance(d, ast.Call) and getattr(d.func, "id", None) == "shared_task" for d in node.decorator_list)
        ]

    def test_hay_tareas(self):
        assert {t.name for t in self.tasks()} == {
            "generate_monthly_report", "requeue_pending_reports", "purge_expired_reports",
        }

    def test_no_importa_dominio_modelos_base_ni_infra(self):
        roots = imported_roots(tree_of(self.TASKS))
        assert not roots & {"domain", "models", "sqlalchemy", "redis", "infra", "psycopg2"}

    def test_de_services_solo_toma_la_politica_de_reintentos(self):
        imported = {
            alias.name
            for node in ast.walk(tree_of(self.TASKS))
            if isinstance(node, ast.ImportFrom) and node.module == "services"
            for alias in node.names
        }
        assert imported == {"TRANSIENT_ERRORS"}

    def test_cada_tarea_es_una_llamada_a_un_caso_de_uso(self):
        """Cuerpo: `return report_service().<metodo publico>(...)`, y nada mas."""
        tree = tree_of(SERVICE_ROOT / "services.py")
        service = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ReportService")
        public = {n.name for n in service.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}
        for task in self.tasks():
            body = [n for n in task.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
            assert len(body) == 1 and isinstance(body[0], ast.Return), task.name
            call = body[0].value
            assert isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute), task.name
            assert call.func.attr in public, f"{task.name} llama a {call.func.attr}"
            factory = call.func.value
            assert isinstance(factory, ast.Call) and getattr(factory.func, "id", None) == "report_service", task.name

    def test_sin_aritmetica_ni_try(self):
        nodes = [
            n for n in ast.walk(tree_of(self.TASKS))
            if isinstance(n, (ast.Try, ast.BinOp, ast.For, ast.While, ast.If))
        ]
        assert not nodes
