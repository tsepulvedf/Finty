"""A-12 entre servicios: toda categoria que `categorization-service` puede emitir
existe en el catalogo que siembra `finance-service`, con el mismo tipo.

Hasta E2-M3a las reglas y el catalogo vivian en el mismo servicio y un test lo
comprobaba contra la base. Desde E2-M3b viven en servicios distintos, y la
garantia se sostiene con dos piezas:

1. **En ejecucion:** `RemoteCategorizer` (finance-service) rechaza una sugerencia
   que no este en su catalogo o no aplique al tipo, y clasifica con su respaldo
   local, que si esta verificado contra el catalogo. Una regla nueva del remoto
   que no se sembro aqui no rompe un registro: se degrada, y queda en el log.
2. **Antes de desplegar:** este test. Lee por AST las reglas de
   `services/categorization-service/infra/categorizers.py` y la siembra de
   `services/finance-service/migrations/versions/0002_seed_categories.py`, sin
   importar ninguno de los dos, y falla si una categoria emitible no esta
   sembrada. Asi la degradacion de (1) es la excepcion, no la norma.

    cd tests/services && python -m pytest -v
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "services/categorization-service/infra/categorizers.py"
SEED = ROOT / "services/finance-service/migrations/versions/0002_seed_categories.py"

TYPE_BY_MEMBER = {"EXPENSE": "expense", "INCOME": "income"}


class _ModuleConstants:
    """Constantes de modulo de un archivo de Python, resueltas sin ejecutarlo."""

    def __init__(self, path):
        self.tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        self.nodes = {
            target.id: node.value
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }

    def value(self, node):
        """Valor literal de un nodo, resolviendo nombres de otras constantes."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self.value(self.nodes[node.id])
        if isinstance(node, ast.Attribute) and node.attr in TYPE_BY_MEMBER:
            return TYPE_BY_MEMBER[node.attr]
        if isinstance(node, (ast.Tuple, ast.List)):
            return [self.value(element) for element in node.elts]
        raise AssertionError(f"Nodo no soportado: {ast.dump(node)}")

    def dict_keys(self, name):
        return [self.value(key) for key in self.nodes[name].keys]

    def dict_items(self, name):
        node = self.nodes[name]
        return {self.value(k): self.value(v) for k, v in zip(node.keys, node.values)}


def emitible_by_rules():
    """`{nombre: tipo}` de todo lo que las reglas y el mock del remoto pueden emitir.

    Las reglas: las claves de cada mapa de palabras, con el tipo de su mapa. El
    respaldo de cada tipo, que es tambien lo que devuelve `MockCategorizer` sin
    configurar (el que construye `CategorizerFactory` con `MOCK`).
    """
    rules = _ModuleConstants(RULES)
    emitible = {name: "expense" for name in rules.dict_keys("EXPENSE_KEYWORDS")}
    emitible.update({name: "income" for name in rules.dict_keys("INCOME_KEYWORDS")})
    for kind, name in rules.dict_items("FALLBACK_BY_TYPE").items():
        emitible[name] = kind
    return emitible


def seeded():
    """`{nombre: applies_to}` que siembra la migracion 0002 de finty_finance."""
    seed = _ModuleConstants(SEED)
    return {name: kind for name, kind in seed.value(seed.nodes["SEEDED_CATEGORIES"])}


def test_se_leyeron_las_dos_fuentes():
    """Centinela: un recorrido vacio dejaria pasar cualquier cosa."""
    assert len(emitible_by_rules()) == 15
    assert len(seeded()) == 15


def test_toda_categoria_emitible_esta_sembrada():
    missing = sorted(set(emitible_by_rules()) - set(seeded()))
    assert not missing, (
        f"categorization-service puede emitir {missing}, que finty_finance no siembra. "
        f"finance-service las rechazaria y clasificaria con su respaldo."
    )


def test_cada_categoria_emitible_aplica_al_mismo_tipo():
    catalog = seeded()
    mismatched = {
        name: (kind, catalog[name])
        for name, kind in emitible_by_rules().items()
        if name in catalog and catalog[name] != kind
    }
    assert not mismatched, f"tipo distinto en el catalogo: {mismatched}"


def test_el_proveedor_externo_no_puede_salir_del_catalogo():
    """`AICategorizer` filtra sus sugerencias con `ALL_CATEGORY_NAMES`.

    Ese conjunto se arma con los mapas y los respaldos, asi que basta con que
    los mapas esten sembrados. Si alguien lo reescribe como una lista propia,
    este test obliga a revisarlo.
    """
    node = _ModuleConstants(RULES).nodes["ALL_CATEGORY_NAMES"]
    referenced = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    assert referenced >= {"EXPENSE_KEYWORDS", "INCOME_KEYWORDS"}
