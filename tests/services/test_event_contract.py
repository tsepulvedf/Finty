"""Contrato de eventos entre servicios (ARCHITECTURE.md §10.5): lo que
`finance-service` publica en `finty.finance.events` es lo que `analytics-service`
sabe leer.

En ejecucion, un mensaje fuera de contrato no rompe al worker: lo descarta con un
aviso en el log (ADR-15). Eso protege la disponibilidad, pero perderia el
evento. Este test lo evita antes de desplegar: lee por AST el serializador de
finance y el deserializador de analytics, sin importar ninguno de los dos, y
falla si analytics lee un campo que finance no escribe o si no coinciden los
tipos de evento.

    cd tests/services && python -m pytest -v
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERIALIZER = ROOT / "services/finance-service/infra/event_serialization.py"
DESERIALIZER = ROOT / "services/analytics-service/infra/event_deserialization.py"
FINANCE_EVENTS = ROOT / "services/finance-service/domain/events.py"
ANALYTICS_EVENTS = ROOT / "services/analytics-service/domain/events.py"


def tree(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def function(path, name):
    return next(n for n in ast.walk(tree(path)) if isinstance(n, ast.FunctionDef) and n.name == name)


def returned_dict_keys(path, name):
    """Claves literales del `dict` que devuelve una funcion."""
    [ret] = [n for n in ast.walk(function(path, name)) if isinstance(n, ast.Return)]
    return {key.value for key in ret.value.keys}


def keys_read_from(path, variable):
    """Claves que se leen de `variable` con `variable["x"]` o `variable.get("x")`."""
    keys = set()
    for node in ast.walk(tree(path)):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == variable and isinstance(node.slice, ast.Constant)):
            keys.add(node.slice.value)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and isinstance(node.func.value, ast.Name)
                and node.func.value.id == variable):
            keys.add(node.args[0].value)
    return keys


def required_keys_read_from(path, variable):
    """Solo las que se leen con `variable["x"]`: sin ellas el mensaje es invalido."""
    return {
        node.slice.value
        for node in ast.walk(tree(path))
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
        and node.value.id == variable and isinstance(node.slice, ast.Constant)
    }


def event_types(path):
    cls = next(n for n in ast.walk(tree(path)) if isinstance(n, ast.ClassDef) and n.name == "EventType")
    return {node.value.value for node in cls.body if isinstance(node, ast.Assign)}


def test_se_leyeron_las_fuentes():
    """Centinela: un recorrido vacio dejaria pasar cualquier cosa."""
    assert len(returned_dict_keys(SERIALIZER, "payload_to_dict")) == 10
    assert len(returned_dict_keys(SERIALIZER, "to_stream_message")) == 5
    assert len(keys_read_from(DESERIALIZER, "payload")) == 10


def test_analytics_solo_lee_campos_que_finance_escribe():
    missing = keys_read_from(DESERIALIZER, "payload") - returned_dict_keys(SERIALIZER, "payload_to_dict")
    assert not missing, f"analytics lee {sorted(missing)} del payload y finance no los publica"


def test_los_campos_obligatorios_del_mensaje_existen():
    missing = required_keys_read_from(DESERIALIZER, "fields") - returned_dict_keys(SERIALIZER, "to_stream_message")
    assert not missing, f"analytics exige {sorted(missing)} y finance no los publica"


def test_mismos_tipos_de_evento():
    assert event_types(FINANCE_EVENTS) == event_types(ANALYTICS_EVENTS)
