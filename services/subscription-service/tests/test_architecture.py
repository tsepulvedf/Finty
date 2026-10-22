"""Reglas de capas de subscription-service, verificadas sobre el AST.

Replica en el servicio los criterios del monolito (`core/tests/test_architecture.py`):

- **A-16**: `domain/` es Python puro: no importa Flask, SQLAlchemy, pydantic,
  Alembic ni nada del anillo externo del servicio.
- Equivalente de A-02: los blueprints no contienen `try` ni aritmetica.
- Equivalente de A-03: los modelos solo declaran columnas y `__repr__`.
- Equivalente de A-10: `services.py` no conoce `infra/`, Redis ni urllib.
- E2-M7: las tareas de Celery (`tasks.py`) son un mecanismo de entrega: cada
  una solo arma el caso de uso y llama a un metodo publico de `services.py`.
- Glosario (§12): ningun identificador usa los sinonimos prohibidos de DDD
  Stage 1 (Membership, Billing, Charge; `Plan` a secas como clase).

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
        assert len(DOMAIN_FILES) >= 8

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
            "SubscriptionRecord", "PaymentRecord", "SentNotificationRecord",
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
    """Equivalente de A-10: el servicio recibe la pasarela por la ABC
    `PaymentGateway`; la elige `PaymentGatewayFactory`."""

    def test_no_importa_infra_ni_redis(self):
        roots = imported_roots(tree_of(SERVICE_ROOT / "services.py"))
        assert not roots & {"infra", "redis", "api", "flask", "urllib"}


class TestSinonimosProhibidos:
    """§12: `Subscription`, `SubscriptionPlan` y `Payment`, nunca sus sinonimos."""

    FORBIDDEN = ("membership", "billing", "charge")
    PACKAGES = ("domain", "infra", "api")
    MODULES = ("services.py", "models.py", "app.py", "messages.py")

    def files(self):
        found = [p for package in self.PACKAGES for p in python_files(package)]
        return found + [SERVICE_ROOT / m for m in self.MODULES]

    def identifiers(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                yield node.name
            elif isinstance(node, ast.Name):
                yield node.id
            elif isinstance(node, ast.Attribute):
                yield node.attr
            elif isinstance(node, ast.arg):
                yield node.arg
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isidentifier():
                yield node.value  # codes y claves JSON

    def test_ningun_identificador_usa_un_sinonimo(self):
        offenders = sorted({
            (relative(path), name)
            for path in self.files()
            for name in self.identifiers(tree_of(path))
            if any(word in name.lower() for word in self.FORBIDDEN)
        })
        assert not offenders

    def test_ninguna_clase_se_llama_plan_a_secas(self):
        classes = {
            n.name
            for path in self.files()
            for n in ast.walk(tree_of(path))
            if isinstance(n, ast.ClassDef)
        }
        assert "Plan" not in classes and "SubscriptionPlan" in classes


class TestTareasSinLogica:
    """E2-M7 (regla 3): una tarea de Celery recibe el mensaje y llama a un caso
    de uso de `services.py`; no consulta la base ni toca el dominio."""

    TASKS = SERVICE_ROOT / "tasks.py"
    FACTORIES = {"notification_service": "NotificationService", "subscription_service": "SubscriptionService"}

    def tasks(self):
        return [
            node for node in tree_of(self.TASKS).body
            if isinstance(node, ast.FunctionDef)
            and any(isinstance(d, ast.Call) and getattr(d.func, "id", None) == "shared_task" for d in node.decorator_list)
        ]

    def public_methods(self, class_name):
        tree = tree_of(SERVICE_ROOT / "services.py")
        service = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
        return {n.name for n in service.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}

    def test_hay_tareas(self):
        assert {t.name for t in self.tasks()} == {
            "send_premium_welcome", "send_missing_welcomes", "notify_expiring_subscriptions",
            "expire_subscriptions",
        }

    def test_no_importa_dominio_modelos_base_ni_infra(self):
        roots = imported_roots(tree_of(self.TASKS))
        assert not roots & {"domain", "models", "sqlalchemy", "redis", "infra", "psycopg2", "urllib"}

    def test_de_services_solo_toma_la_politica_de_reintentos(self):
        imported = {
            alias.name
            for node in ast.walk(tree_of(self.TASKS))
            if isinstance(node, ast.ImportFrom) and node.module == "services"
            for alias in node.names
        }
        assert imported == {"TRANSIENT_ERRORS"}

    def test_cada_tarea_es_una_llamada_a_un_caso_de_uso(self):
        """Cuerpo: `return <servicio>().<metodo publico>(...)`, y nada mas."""
        for task in self.tasks():
            body = [n for n in task.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
            assert len(body) == 1 and isinstance(body[0], ast.Return), task.name
            call = body[0].value
            assert isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute), task.name
            factory = call.func.value
            assert isinstance(factory, ast.Call), task.name
            service = self.FACTORIES.get(getattr(factory.func, "id", None))
            assert service, f"{task.name} no arma un caso de uso"
            assert call.func.attr in self.public_methods(service), f"{task.name} llama a {call.func.attr}"

    def test_sin_aritmetica_ni_control_de_flujo(self):
        nodes = [
            n for n in ast.walk(tree_of(self.TASKS))
            if isinstance(n, (ast.Try, ast.BinOp, ast.For, ast.While, ast.If))
        ]
        assert not nodes
