"""Verificacion de las reglas de capas mediante analisis del AST (A-15).

**Por que AST y no `grep`.** Un regex sobre texto no distingue una sentencia de
una subcadena. El caso que lo demostro: `grep -rnE "try:|except"` sobre las views
daba positivo por `serializer.is_valid(raise_exception=True)`, porque
`raise_ex-cept-ion` contiene `except`. Anclar el patron a inicio de sentencia lo
arreglaba, pero seguia siendo una heuristica sobre caracteres. `ast` examina la
estructura real del programa: un `ast.Try` es un `try`, y nada mas lo es.

**Consecuencia para quien escriba docstrings.** En M2 hubo que reformular varios
docstrings de `finance/domain/` porque mencionaban `django`, `finance.models` o
`identity` como prosa —explicando justamente que no se importaban— y los `grep`
de pureza daban falso positivo. Esa restriccion de vocabulario **ya no existe**:
estos tests miran nodos `ast.Import` e `ast.ImportFrom`, no texto. Los docstrings
de `finance/domain/` pueden volver a nombrar lo que necesiten nombrar.

Estos tests no tocan la base de datos ni importan los modulos que analizan: leen
el archivo y lo parsean. Corren sin PostgreSQL levantado.
"""
import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent

# Modulos prohibidos en el anillo de dominio. La regla de dependencia apunta
# hacia adentro: el dominio no conoce framework, ni ORM, ni infraestructura, ni
# los demas contextos.
PROHIBIDOS_EN_DOMINIO = (
    "django",
    "rest_framework",
    "finance.models",
    "finance.infra",
    "identity",
    "config",
)

PAQUETES_DE_DOMINIO = ("core/domain", "finance/domain")

MODULOS_DE_VISTAS = ("finance/api/views.py", "identity/api/views.py")
MODULOS_DE_MODELOS = ("finance/models.py", "identity/models.py")
MODULOS_DE_SERVICIOS = ("finance/services.py", "identity/services.py")
MODULOS_DE_SERIALIZERS = (
    "finance/api/serializers.py",
    "identity/api/serializers.py",
)

PAQUETES_DE_COMANDOS = ("finance/management/commands",)

# Piezas del dominio que una vista jamas debe manipular directamente: si las
# necesita, es que esta haciendo el trabajo del servicio.
PIEZAS_DE_DOMINIO_VETADAS_EN_VISTAS = (
    "Money",
    "BalanceCalculator",
    "TransactionBuilder",
    "AccountBuilder",
    "TransactionRules",
)

CATEGORIZADORES_CONCRETOS = (
    "AICategorizer",
    "RuleBasedCategorizer",
    "MockCategorizer",
)

METODOS_DE_MODELO_PROHIBIDOS = (
    "save",
    "clean",
    "delete",
    "full_clean",
    "get_absolute_url",
)

DECORADORES_DE_MODELO_PROHIBIDOS = ("property", "cached_property")

# Clases base que convierten a una clase en un modelo persistido. `Model` cubre
# `models.Model`; las otras dos son las bases de usuario de Django. Sin
# `AbstractUser` en esta lista, `identity.User` se escaparia de las
# comprobaciones de ADR-03, que es justo lo que este test descubrio.
BASES_DE_MODELO = ("Model", "AbstractUser", "AbstractBaseUser")

# Unico acceso directo al ORM tolerado fuera de un servicio. Se permite por
# nombre completo y no por comodin: `CategoryViewSet` es un catalogo global de
# solo lectura sin ninguna regla que orquestar (ADR-05), asi que interponer un
# servicio que solo reenviara el queryset seria ceremonia vacia.
ACCESO_A_ORM_PERMITIDO_EN_VISTAS = {("CategoryViewSet", "queryset")}


def arbol_de(ruta_relativa):
    """Parsea un modulo del proyecto y devuelve su AST."""
    ruta = RAIZ / ruta_relativa
    assert ruta.exists(), f"No existe {ruta_relativa}"
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def modulos_de(*paquetes):
    """Devuelve las rutas relativas de todos los `.py` de esos paquetes."""
    encontrados = []
    for paquete in paquetes:
        for ruta in sorted((RAIZ / paquete).rglob("*.py")):
            if "__pycache__" in ruta.parts:
                continue
            encontrados.append(ruta.relative_to(RAIZ).as_posix())
    return encontrados


def modulos_importados(arbol):
    """Devuelve los nombres de modulo que importa un AST.

    Cubre las dos formas: `import x.y` y `from x.y import z`. Los imports
    relativos se ignoran porque no pueden salir del paquete actual.
    """
    nombres = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            nombres.append(nodo.module)
    return nombres


def simbolos_importados(arbol):
    """Devuelve los nombres concretos que un modulo trae al espacio de nombres."""
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            nombres.update(alias.name for alias in nodo.names)
    return nombres


def coincide(modulo, prohibido):
    """Indica si un modulo importado cae bajo un paquete prohibido."""
    return modulo == prohibido or modulo.startswith(prohibido + ".")


def accesos_a_orm(arbol):
    """Devuelve los nodos que acceden al ORM a traves de `.objects`."""
    return [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Attribute) and nodo.attr == "objects"
    ]


def nombre_del_decorador(decorador):
    """Devuelve el nombre simple de un decorador, sea `x`, `x.y` o `x(...)`."""
    if isinstance(decorador, ast.Call):
        decorador = decorador.func
    if isinstance(decorador, ast.Attribute):
        return decorador.attr
    if isinstance(decorador, ast.Name):
        return decorador.id
    return ""


def nombre_de_base(base):
    """Devuelve el nombre simple de una clase base, sea `X` o `modulo.X`."""
    if isinstance(base, ast.Attribute):
        return base.attr
    if isinstance(base, ast.Name):
        return base.id
    return ""


def clases_de_modelo(arbol):
    """Devuelve los `ClassDef` que definen un modelo persistido.

    Un manager como `UserManager` queda fuera a proposito: `create_user` es
    logica de persistencia que Django exige en el manager, no una regla de
    negocio en el modelo.
    """
    return [
        nodo
        for nodo in arbol.body
        if isinstance(nodo, ast.ClassDef)
        and any(nombre_de_base(base) in BASES_DE_MODELO for base in nodo.bases)
    ]


class TestPurezaDelDominio:
    """A-01 y A-09: el anillo de dominio no conoce nada de afuera."""

    @pytest.mark.parametrize("ruta", modulos_de(*PAQUETES_DE_DOMINIO))
    def test_ningun_modulo_de_dominio_importa_hacia_afuera(self, ruta):
        importados = modulos_importados(arbol_de(ruta))

        infracciones = [
            (modulo, prohibido)
            for modulo in importados
            for prohibido in PROHIBIDOS_EN_DOMINIO
            if coincide(modulo, prohibido)
        ]

        assert not infracciones, (
            f"{ruta} importa desde fuera del dominio: "
            + ", ".join(f"'{m}' (prohibido: {p})" for m, p in infracciones)
        )

    def test_se_analizo_algo(self):
        """Red de seguridad: si el recorrido no encuentra archivos, no prueba nada."""
        assert len(modulos_de(*PAQUETES_DE_DOMINIO)) >= 8

    def test_los_builders_solo_conocen_la_stdlib_y_el_dominio(self):
        """El Builder vive en `domain/` y no puede arrastrar el ORM (C-11, C-12)."""
        importados = modulos_importados(arbol_de("finance/domain/builders.py"))

        permitidos = ("core.domain", "finance.domain")
        externos = [
            modulo
            for modulo in importados
            if "." in modulo and not any(coincide(modulo, p) for p in permitidos)
        ]

        assert not externos, f"builders.py importa modulos externos: {externos}"


class TestVistasSinLogica:
    """A-02: las views traducen HTTP y nada mas."""

    @pytest.mark.parametrize("ruta", MODULOS_DE_VISTAS)
    def test_cero_bloques_try(self, ruta):
        """El handler global traduce las excepciones de dominio; nadie las captura."""
        capturas = [n for n in ast.walk(arbol_de(ruta)) if isinstance(n, ast.Try)]

        assert not capturas, (
            f"{ruta} contiene {len(capturas)} bloque(s) try en la(s) linea(s) "
            f"{[n.lineno for n in capturas]}"
        )

    @pytest.mark.parametrize("ruta", MODULOS_DE_VISTAS)
    def test_cero_aritmetica(self, ruta):
        """Calcular es del dominio. Una vista que suma esta decidiendo algo."""
        aritmeticos = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
        operaciones = [
            nodo
            for nodo in ast.walk(arbol_de(ruta))
            if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, aritmeticos)
        ]

        assert not operaciones, (
            f"{ruta} hace aritmetica en la(s) linea(s) "
            f"{[n.lineno for n in operaciones]}"
        )

    @pytest.mark.parametrize("ruta", MODULOS_DE_VISTAS)
    def test_no_importa_piezas_del_dominio(self, ruta):
        importados = simbolos_importados(arbol_de(ruta))
        vetados = importados & set(PIEZAS_DE_DOMINIO_VETADAS_EN_VISTAS)

        assert not vetados, f"{ruta} importa piezas del dominio: {sorted(vetados)}"

    @pytest.mark.parametrize("ruta", MODULOS_DE_VISTAS)
    def test_no_importa_categorizadores_concretos(self, ruta):
        """La vista pide uno a la fabrica; no conoce implementaciones."""
        importados = simbolos_importados(arbol_de(ruta))
        vetados = importados & set(CATEGORIZADORES_CONCRETOS)

        assert not vetados, (
            f"{ruta} importa categorizadores concretos: {sorted(vetados)}"
        )

    @pytest.mark.parametrize("ruta", MODULOS_DE_VISTAS)
    def test_todo_acceso_a_datos_pasa_por_un_servicio(self, ruta):
        arbol = arbol_de(ruta)
        permitidos = self._asignaciones_permitidas(arbol)

        infracciones = [
            nodo.lineno
            for nodo in accesos_a_orm(arbol)
            if nodo.lineno not in permitidos
        ]

        assert not infracciones, (
            f"{ruta} accede al ORM directamente en la(s) linea(s) {infracciones}; "
            f"todo acceso a datos debe pasar por un servicio"
        )

    @staticmethod
    def _asignaciones_permitidas(arbol):
        """Lineas de los atributos de clase tolerados explicitamente."""
        lineas = set()
        for clase in [n for n in arbol.body if isinstance(n, ast.ClassDef)]:
            for cuerpo in clase.body:
                if not isinstance(cuerpo, ast.Assign):
                    continue
                for objetivo in cuerpo.targets:
                    if (
                        isinstance(objetivo, ast.Name)
                        and (clase.name, objetivo.id)
                        in ACCESO_A_ORM_PERMITIDO_EN_VISTAS
                    ):
                        lineas.update(
                            n.lineno
                            for n in ast.walk(cuerpo)
                            if hasattr(n, "lineno")
                        )
        return lineas


class TestComandosSinLogica:
    """Un comando de gestion es un mecanismo de entrega, igual que una vista.

    Le aplica el mismo criterio: orquesta llamadas al servicio y formatea la
    salida, pero no calcula, no reimplementa reglas y no consulta el ORM. Un
    comando que recalculara el balance por su cuenta duplicaria `BalanceCalculator`
    y podria estar de acuerdo con un error del servicio.
    """

    @pytest.mark.parametrize("ruta", modulos_de(*PAQUETES_DE_COMANDOS))
    def test_no_importan_piezas_del_dominio(self, ruta):
        importados = simbolos_importados(arbol_de(ruta))
        vetados = importados & set(PIEZAS_DE_DOMINIO_VETADAS_EN_VISTAS)

        assert not vetados, (
            f"{ruta} importa piezas del dominio: {sorted(vetados)}. Un comando "
            f"pide los datos ya calculados al servicio."
        )

    @pytest.mark.parametrize("ruta", modulos_de(*PAQUETES_DE_COMANDOS))
    def test_no_importan_modelos(self, ruta):
        importados = modulos_importados(arbol_de(ruta))
        vetados = [
            modulo
            for modulo in importados
            if modulo.endswith(".models") or modulo.endswith("models")
        ]

        assert not vetados, (
            f"{ruta} importa modelos directamente: {vetados}. El acceso a datos "
            f"pasa por un servicio."
        )

    @pytest.mark.parametrize("ruta", modulos_de(*PAQUETES_DE_COMANDOS))
    def test_no_importan_el_dominio_ni_la_infraestructura(self, ruta):
        importados = modulos_importados(arbol_de(ruta))
        vetados = [
            modulo
            for modulo in importados
            for prohibido in ("finance.domain", "finance.infra", "core.domain")
            if coincide(modulo, prohibido)
        ]

        assert not vetados, f"{ruta} importa {vetados}; solo puede usar servicios."

    @pytest.mark.parametrize("ruta", modulos_de(*PAQUETES_DE_COMANDOS))
    def test_cero_aritmetica(self, ruta):
        """Si un comando suma, esta calculando algo que le toca al dominio.

        El formateo de anchos de columna usa multiplicacion de cadenas y sumas de
        enteros, asi que se excluyen los modulos de soporte y se revisa solo el
        cuerpo de `handle`, que es donde viviria una regla infiltrada.
        """
        arbol = arbol_de(ruta)
        handles = [
            nodo
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.FunctionDef) and nodo.name == "handle"
        ]

        operaciones = [
            nodo.lineno
            for handle in handles
            for nodo in ast.walk(handle)
            if isinstance(nodo, ast.BinOp)
            and isinstance(nodo.op, (ast.Add, ast.Sub, ast.Mult, ast.Div))
        ]

        assert not operaciones, (
            f"{ruta}: handle() hace aritmetica en la(s) linea(s) {operaciones}"
        )

    def test_se_encontraron_comandos(self):
        """Test centinela: sin el, mover el paquete dejaria la suite en verde."""
        comandos = [
            ruta
            for ruta in modulos_de(*PAQUETES_DE_COMANDOS)
            if not ruta.endswith("__init__.py")
        ]

        assert comandos, "No se encontro ningun comando de gestion que analizar"
        assert any(r.endswith("verify_invariants.py") for r in comandos)


class TestModelosAnemicos:
    """A-03 y ADR-03: `models.py` solo persiste.

    Es la seccion que la rubrica penaliza con la mitad de la nota, asi que cada
    mensaje de fallo nombra la clase y el metodo infractor.
    """

    @pytest.mark.parametrize("ruta", MODULOS_DE_MODELOS)
    def test_solo_se_permiten_str_y_meta(self, ruta):
        infracciones = []
        for clase in clases_de_modelo(arbol_de(ruta)):
            for miembro in clase.body:
                if isinstance(miembro, ast.ClassDef):
                    if miembro.name != "Meta":
                        infracciones.append(f"{clase.name}.{miembro.name} (clase anidada)")
                elif isinstance(miembro, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if miembro.name != "__str__":
                        infracciones.append(f"{clase.name}.{miembro.name}()")

        assert not infracciones, (
            f"{ruta}: ADR-03 solo permite campos, Meta y __str__ en un modelo. "
            f"Sobran: {infracciones}. Un metodo de negocio en un modelo cuesta el "
            f"50% de la nota de esa seccion."
        )

    @pytest.mark.parametrize("ruta", MODULOS_DE_MODELOS)
    def test_no_sobreescriben_metodos_del_orm(self, ruta):
        infracciones = [
            f"{clase.name}.{miembro.name}()"
            for clase in clases_de_modelo(arbol_de(ruta))
            for miembro in clase.body
            if isinstance(miembro, (ast.FunctionDef, ast.AsyncFunctionDef))
            and miembro.name in METODOS_DE_MODELO_PROHIBIDOS
        ]

        assert not infracciones, (
            f"{ruta}: {infracciones} sobreescribe(n) el ciclo de vida del ORM. "
            f"Las reglas van en domain/ y la orquestacion en services.py."
        )

    @pytest.mark.parametrize("ruta", MODULOS_DE_MODELOS)
    def test_no_declaran_propiedades_calculadas(self, ruta):
        infracciones = [
            f"{clase.name}.{miembro.name} (@{nombre_del_decorador(decorador)})"
            for clase in clases_de_modelo(arbol_de(ruta))
            for miembro in clase.body
            if isinstance(miembro, (ast.FunctionDef, ast.AsyncFunctionDef))
            for decorador in miembro.decorator_list
            if nombre_del_decorador(decorador) in DECORADORES_DE_MODELO_PROHIBIDOS
        ]

        assert not infracciones, (
            f"{ruta}: {infracciones} calcula(n) algo del negocio en el modelo."
        )

    @pytest.mark.parametrize("ruta", MODULOS_DE_MODELOS)
    def test_no_hay_receptores_de_senales(self, ruta):
        arbol = arbol_de(ruta)

        decorados = [
            f"{n.name}() en la linea {n.lineno}"
            for n in ast.walk(arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            for d in n.decorator_list
            if nombre_del_decorador(d) == "receiver"
        ]
        conectados = [
            f"linea {n.lineno}"
            for n in ast.walk(arbol)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "connect"
        ]

        assert not decorados + conectados, (
            f"{ruta}: hay senales conectadas ({decorados + conectados}). ADR-03 las "
            f"prohibe: una regla que se ejecuta sola al guardar es logica de "
            f"negocio escondida en la persistencia."
        )

    def test_se_analizaron_los_modelos_esperados(self):
        """Sin esta comprobacion, un recorrido vacio dejaria pasar cualquier cosa."""
        nombres = {
            clase.name
            for ruta in MODULOS_DE_MODELOS
            for clase in clases_de_modelo(arbol_de(ruta))
        }

        assert {"Account", "Transaction", "Category", "User", "UserProfile"} <= nombres


class TestServiciosSinImplementacionesConcretas:
    """A-10: el servicio depende de la abstraccion, nunca de una concrecion."""

    @pytest.mark.parametrize("ruta", MODULOS_DE_SERVICIOS)
    def test_no_importan_categorizadores_ni_la_fabrica(self, ruta):
        importados = simbolos_importados(arbol_de(ruta))
        vetados = importados & set(CATEGORIZADORES_CONCRETOS + ("CategorizerFactory",))

        assert not vetados, (
            f"{ruta} importa {sorted(vetados)}. Quien elige la implementacion es la "
            f"vista, que pide una al Factory Method y la inyecta por constructor."
        )

    def test_finance_services_no_importa_nada_de_infra(self):
        importados = modulos_importados(arbol_de("finance/services.py"))

        assert not [m for m in importados if coincide(m, "finance.infra")]


class TestSerializersSinAccesoADatos:
    """Regla 4: los serializers validan sintaxis, no semantica."""

    @pytest.mark.parametrize("ruta", MODULOS_DE_SERIALIZERS)
    def test_no_consultan_la_base(self, ruta):
        infracciones = [nodo.lineno for nodo in accesos_a_orm(arbol_de(ruta))]

        assert not infracciones, (
            f"{ruta} consulta la base en la(s) linea(s) {infracciones}. Que algo "
            f"exista o sea del usuario lo decide el servicio."
        )

    @pytest.mark.parametrize("ruta", MODULOS_DE_SERIALIZERS)
    def test_no_importan_servicios(self, ruta):
        importados = modulos_importados(arbol_de(ruta))
        infracciones = [m for m in importados if m.endswith(".services")]

        assert not infracciones, f"{ruta} importa servicios: {infracciones}"


class TestMigracionesSinCodigoVivo:
    """Las migraciones son artefactos historicos.

    Deben seguir aplicandose dentro de un ano aunque el dominio cambie de forma,
    de nombre o de ubicacion. Formaliza lo que se decidio a mano en M3 y M5.1.
    """

    PROHIBIDOS = (
        "finance.domain",
        "finance.infra",
        "finance.services",
        "core.domain",
        "identity.services",
    )

    @pytest.mark.parametrize(
        "ruta", modulos_de("finance/migrations", "identity/migrations")
    )
    def test_ninguna_migracion_importa_codigo_vivo(self, ruta):
        importados = modulos_importados(arbol_de(ruta))

        infracciones = [
            modulo
            for modulo in importados
            for prohibido in self.PROHIBIDOS
            if coincide(modulo, prohibido)
        ]

        assert not infracciones, (
            f"{ruta} importa codigo vivo: {infracciones}. Una migracion que depende "
            f"del dominio deja de aplicar en cuanto ese codigo cambia."
        )

    def test_se_analizaron_las_migraciones(self):
        rutas = modulos_de("finance/migrations", "identity/migrations")

        assert len([r for r in rutas if not r.endswith("__init__.py")]) >= 6
