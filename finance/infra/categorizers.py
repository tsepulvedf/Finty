"""Adaptadores de clasificacion de transacciones (anillo externo).

Tres implementaciones concretas de la ABC `Categorizer` definida en
`finance/domain/interfaces.py`. Cada una resuelve la misma operacion contra una
fuente distinta y son intercambiables sin tocar los services: eso es LSP, y
`finance/tests/test_categorizer_lsp.py` lo verifica de forma ejecutable.

Los nombres de categoria se declaran aqui como constantes de modulo. **No se
importan del modulo que siembra el catalogo**: el codigo de runtime no debe
depender de un artefacto del historial de esquema, porque esos archivos se
aplastan y se reescriben y el import quedaria roto sin aviso. La coherencia entre
estas constantes y lo que hay en base se garantiza con un test de contrato
(`test_categorizer_catalog_contract.py`), no con un import compartido.
"""
import logging
import re
import unicodedata
from typing import Protocol

from finance.domain.interfaces import Categorizer
from finance.domain.value_objects import (
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    CategorizationSource,
    CategorySuggestion,
    TransactionType,
)

logger = logging.getLogger(__name__)

# --- Catalogo de categorias -------------------------------------------------

CATEGORY_FOOD = "Alimentación"
CATEGORY_TRANSPORT = "Transporte"
CATEGORY_HOUSING = "Vivienda"
CATEGORY_UTILITIES = "Servicios públicos"
CATEGORY_HEALTH = "Salud"
CATEGORY_EDUCATION = "Educación"
CATEGORY_ENTERTAINMENT = "Entretenimiento"
CATEGORY_SHOPPING = "Compras"
CATEGORY_DEBT = "Deudas y créditos"

CATEGORY_SALARY = "Salario"
CATEGORY_FREELANCE = "Freelance"
CATEGORY_INVESTMENTS = "Inversiones"
CATEGORY_REFUNDS = "Reembolsos"

# Categorias de respaldo: se usan cuando ninguna regla hace match. Deben existir
# siempre en el catalogo.
FALLBACK_EXPENSE_CATEGORY = "Otros gastos"
FALLBACK_INCOME_CATEGORY = "Otros ingresos"

FALLBACK_BY_TYPE = {
    TransactionType.EXPENSE: FALLBACK_EXPENSE_CATEGORY,
    TransactionType.INCOME: FALLBACK_INCOME_CATEGORY,
}


# --- Reglas deterministas ---------------------------------------------------

# Un mapa por tipo de transaccion. La separacion no es cosmetica: garantiza que
# una regla de gasto jamas pueda devolver una categoria de ingreso, algo que un
# unico mapa compartido no podria impedir.
EXPENSE_KEYWORDS = {
    CATEGORY_FOOD: (
        "mercado",
        "supermercado",
        "restaurante",
        "almuerzo",
        "comida",
        "domicilio",
    ),
    CATEGORY_TRANSPORT: (
        "taxi",
        "uber",
        "gasolina",
        "bus",
        "metro",
        "parqueadero",
        "peaje",
    ),
    CATEGORY_HOUSING: ("arriendo", "hipoteca", "administracion", "mudanza"),
    CATEGORY_UTILITIES: (
        "agua",
        "luz",
        "energia",
        "gas",
        "internet",
        "telefono",
        "celular",
    ),
    CATEGORY_HEALTH: (
        "eps",
        "medicina",
        "farmacia",
        "drogueria",
        "medico",
        "odontologia",
    ),
    CATEGORY_EDUCATION: ("matricula", "universidad", "curso", "colegio", "libro"),
    CATEGORY_ENTERTAINMENT: (
        "cine",
        "netflix",
        "spotify",
        "concierto",
        "streaming",
        "videojuego",
    ),
    CATEGORY_SHOPPING: (
        "ropa",
        "zapatos",
        "tecnologia",
        "electrodomestico",
        "amazon",
    ),
    CATEGORY_DEBT: ("cuota", "prestamo", "tarjeta", "credito", "interes"),
}

INCOME_KEYWORDS = {
    CATEGORY_SALARY: ("salario", "nomina", "sueldo", "quincena", "pago empleador"),
    CATEGORY_FREELANCE: (
        "freelance",
        "honorarios",
        "factura",
        "proyecto",
        "consultoria",
    ),
    CATEGORY_INVESTMENTS: (
        "dividendo",
        "rendimiento",
        "interes ganado",
        "cdt",
        "accion",
    ),
    CATEGORY_REFUNDS: ("reembolso", "devolucion", "reintegro"),
}

KEYWORDS_BY_TYPE = {
    TransactionType.EXPENSE: EXPENSE_KEYWORDS,
    TransactionType.INCOME: INCOME_KEYWORDS,
}

# Conjunto completo de nombres que el sistema puede emitir o aceptar. Es lo que
# `AICategorizer` usa por defecto para descartar categorias alucinadas.
ALL_CATEGORY_NAMES = frozenset(
    list(EXPENSE_KEYWORDS)
    + list(INCOME_KEYWORDS)
    + [FALLBACK_EXPENSE_CATEGORY, FALLBACK_INCOME_CATEGORY]
)

MATCH_CONFIDENCE = 0.75
FALLBACK_CONFIDENCE = 0.20

_NON_ALPHANUMERIC = re.compile(r"[^0-9a-z]+")
_MULTIPLE_SPACES = re.compile(r"\s+")


def normalize_description(description):
    """Reduce una descripcion a texto comparable.

    Minusculas, sin tildes y sin puntuacion, con los espacios colapsados. Asi
    `"Almuerzo en El Corral!!"` y `"almuerzo en el corral"` activan la misma
    regla. Cualquier entrada que no sea texto se trata como cadena vacia: este
    modulo nunca lanza.
    """
    if not isinstance(description, str):
        return ""

    # NFKD separa cada letra de su tilde; descartar los diacriticos combinantes
    # deja el texto en ASCII sin perder las letras base.
    decomposed = unicodedata.normalize("NFKD", description.lower())
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    cleaned = _NON_ALPHANUMERIC.sub(" ", without_accents)
    return _MULTIPLE_SPACES.sub(" ", cleaned).strip()


def _compile_rules(keywords_by_category):
    """Compila un patron por categoria con limites de palabra.

    Los limites evitan el falso positivo clasico de la subcadena: `mercado` no
    se activa dentro de `supermercadito`, pero si en `mercado de la esquina`.
    """
    return {
        category: re.compile(
            r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b"
        )
        for category, words in keywords_by_category.items()
    }


COMPILED_RULES_BY_TYPE = {
    transaction_type: _compile_rules(keywords)
    for transaction_type, keywords in KEYWORDS_BY_TYPE.items()
}


def _coerce_transaction_type(transaction_type):
    """Normaliza el tipo, cayendo en gasto si es irreconocible.

    Un categorizador no puede lanzar, ni siquiera ante un tipo invalido: quien
    valida INV-09 es el builder, antes de llegar aqui.
    """
    try:
        return TransactionType.from_value(transaction_type)
    except Exception:
        return TransactionType.EXPENSE


class RuleBasedCategorizer(Categorizer):
    """Clasifica por coincidencia de palabras clave. Determinista y sin red.

    Es el respaldo obligatorio de todo lo demas: no consulta base de datos, no
    abre conexiones, no guarda estado mutable y siempre responde. La misma entrada
    produce siempre la misma salida.
    """

    def categorize(self, description, amount, transaction_type):
        """Devuelve la primera categoria cuyas palabras clave coincidan."""
        resolved_type = _coerce_transaction_type(transaction_type)
        normalized = normalize_description(description)

        if normalized:
            for category, pattern in COMPILED_RULES_BY_TYPE[resolved_type].items():
                if pattern.search(normalized):
                    return CategorySuggestion(
                        category, MATCH_CONFIDENCE, CategorizationSource.RULE
                    )

        return CategorySuggestion(
            FALLBACK_BY_TYPE[resolved_type],
            FALLBACK_CONFIDENCE,
            CategorizationSource.RULE,
        )


class SuggestionClient(Protocol):
    """Forma esperada de un cliente de proveedor externo de clasificacion.

    Se declara como `Protocol` y no como clase base para documentar el contrato
    sin obligar a heredar: cualquier objeto con este metodo sirve, incluido un
    doble de prueba.
    """

    def suggest_category(self, description, amount, transaction_type):
        """Devuelve `(nombre_de_categoria, confianza)`."""
        ...


class AICategorizer(Categorizer):
    """Envuelve un proveedor externo y garantiza el contrato pase lo que pase.

    **En esta entrega no se implementa ningun cliente concreto de proveedor.**
    `client` es una costura deliberada: no hay dependencias de red, ni claves de
    API, ni llamadas salientes en todo el proyecto. Sin cliente configurado, esta
    clase opera en modo degradado y delega en el respaldo determinista.

    Eso no es una limitacion del diseno: es exactamente el requisito de Phase 0 de
    que toda funcionalidad AI-powered tenga respaldo determinista, demostrado en
    codigo y no prometido en un documento. El dia que exista un cliente real, se
    inyecta por constructor y ni el Service ni las views cambian una linea.

    Las cuatro degradaciones posibles terminan todas en el respaldo: sin cliente,
    cliente que falla, categoria alucinada fuera del catalogo, o respuesta con
    forma inesperada. La confianza fuera de rango se recorta en vez de descartarse,
    porque el nombre de la categoria sigue siendo utilizable.
    """

    def __init__(self, client=None, fallback=None, allowed_categories=None):
        self._client = client
        self._fallback = fallback if fallback is not None else RuleBasedCategorizer()
        self._allowed_categories = (
            frozenset(allowed_categories)
            if allowed_categories is not None
            else ALL_CATEGORY_NAMES
        )

    @property
    def allowed_categories(self):
        """Conjunto de nombres que este categorizador acepta del proveedor."""
        return self._allowed_categories

    def categorize(self, description, amount, transaction_type):
        """Consulta al proveedor y degrada al respaldo ante cualquier problema."""
        if self._client is None:
            return self._fallback.categorize(description, amount, transaction_type)

        try:
            category_name, confidence = self._client.suggest_category(
                description, amount, transaction_type
            )
        except BaseException as exc:
            # Se captura `BaseException` y no `Exception` a proposito: algunas
            # bibliotecas de cliente senalan expiracion de tiempo con excepciones
            # que no derivan de `Exception`. El contrato de `Categorizer` dice
            # "nunca propaga", y nunca no admite excepciones.
            logger.warning(
                "El proveedor de clasificacion fallo con %s: %s. "
                "Se usa el respaldo determinista.",
                type(exc).__name__,
                exc,
            )
            return self._fallback.categorize(description, amount, transaction_type)

        return self._suggestion_or_fallback(
            category_name, confidence, description, amount, transaction_type
        )

    def _suggestion_or_fallback(
        self, category_name, confidence, description, amount, transaction_type
    ):
        """Valida la respuesta del proveedor o degrada al respaldo."""
        if not isinstance(category_name, str) or category_name.strip() not in (
            self._allowed_categories
        ):
            logger.warning(
                "El proveedor de clasificacion devolvio la categoria %r, que no "
                "esta en el catalogo. Se usa el respaldo determinista.",
                category_name,
            )
            return self._fallback.categorize(description, amount, transaction_type)

        try:
            numeric_confidence = float(confidence)
        except (TypeError, ValueError):
            logger.warning(
                "El proveedor de clasificacion devolvio la confianza %r, que no "
                "es numerica. Se usa el respaldo determinista.",
                confidence,
            )
            return self._fallback.categorize(description, amount, transaction_type)

        clamped = min(max(numeric_confidence, CONFIDENCE_FLOOR), CONFIDENCE_CEILING)
        return CategorySuggestion(
            category_name.strip(), clamped, CategorizationSource.AI
        )


class MockCategorizer(Categorizer):
    """Devuelve una sugerencia fija y configurable, para desarrollo y pruebas.

    Sin red, sin base de datos y sin estado mutable. Existe para que desarrollar y
    probar no consuma cuota de inferencia (restriccion HC-06 de Phase 0) ni
    dependa de que un proveedor externo este disponible.
    """

    def __init__(
        self,
        category_name=None,
        confidence=CONFIDENCE_CEILING,
        source=CategorizationSource.RULE,
    ):
        self._category_name = category_name
        self._confidence = confidence
        self._source = CategorizationSource(source)

    def categorize(self, description, amount, transaction_type):
        """Devuelve siempre la misma sugerencia configurada."""
        resolved_type = _coerce_transaction_type(transaction_type)
        name = (
            self._category_name
            if self._category_name is not None
            else FALLBACK_BY_TYPE[resolved_type]
        )
        return CategorySuggestion(name, self._confidence, self._source)
