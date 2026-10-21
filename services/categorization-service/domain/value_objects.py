"""Value Objects del dominio de categorizacion (anillo de Dominio, Python puro).

Subconjunto de `finance-service/domain/value_objects.py`, copiado sin cambios:
el tipo de transaccion que se clasifica, la procedencia de una clasificacion y la
sugerencia que devuelve todo `Categorizer`. Este modulo no importa Flask.
"""
from dataclasses import dataclass
from enum import StrEnum

from domain.shared.exceptions import ValidationError
from domain.exceptions import InvalidTransactionTypeError

CONFIDENCE_FLOOR = 0.0
CONFIDENCE_CEILING = 1.0
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


class TransactionType(StrEnum):
    """Sentido de un movimiento financiero. Conjunto cerrado (INV-09)."""

    INCOME = "income"
    EXPENSE = "expense"

    @classmethod
    def from_value(cls, raw):
        """Normaliza un valor externo a un miembro del enum (INV-09)."""
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, str):
            raise InvalidTransactionTypeError(
                f"El tipo de transaccion debe ser una cadena, no "
                f"{type(raw).__name__}."
            )
        try:
            return cls(raw.strip().lower())
        except ValueError as exc:
            valid = ", ".join(member.value for member in cls)
            raise InvalidTransactionTypeError(
                f"'{raw}' no es un tipo de transaccion valido. "
                f"Opciones: {valid}."
            ) from exc

    def sign(self):
        """Devuelve el signo con que el movimiento afecta un balance.

        `+1` para ingreso, `-1` para gasto. Es la unica fuente de verdad sobre
        como un movimiento altera el balance: `BalanceCalculator` la consume y
        nadie mas replica el signo. Si un dia apareciera un tercer tipo, este
        es el unico punto a tocar.
        """
        return 1 if self is TransactionType.INCOME else -1


class CategorizationSource(StrEnum):
    """Origen de la categoria asignada a una transaccion.

    Mapea al campo `categorization_source` de ARCHITECTURE.md 5.2.

    Cada valor identifica **el mecanismo que realmente clasifico**, no el que se
    pidio (A-14). Por eso `MOCK` existe como valor propio: un doble de pruebas
    reportandose como `RULE` dejaria una traza de auditoria falsa. Por la misma
    razon, cuando el clasificador de proveedor externo degrada a su respaldo, la
    procedencia registrada es la del respaldo y no la suya.
    """

    AI = "ai"
    RULE = "rule"
    MANUAL = "manual"
    MOCK = "mock"


@dataclass(frozen=True)
class CategorySuggestion:
    """Resultado de categorizar una transaccion.

    Es el contrato de retorno de `Categorizer` (ARCHITECTURE.md 5.3) y lo que
    hace posible el LSP: toda implementacion devuelve este mismo value object,
    incluida la que fallo internamente y responde con confianza reducida.

    `confidence` si es un `float`, a diferencia del monto de `Money`: es una
    medida estadistica aproximada, no dinero. Aqui la imprecision binaria no
    tiene consecuencias contables.
    """

    category_name: str
    confidence: float
    source: CategorizationSource

    def __post_init__(self):
        """Valida y normaliza la sugerencia."""
        if not isinstance(self.category_name, str):
            raise ValidationError(
                "El nombre de la categoria debe ser una cadena de texto."
            )

        cleaned_name = self.category_name.strip()
        if not cleaned_name:
            raise ValidationError("El nombre de la categoria no puede estar vacio.")
        object.__setattr__(self, "category_name", cleaned_name)

        try:
            confidence = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "La confianza debe ser un numero entre 0.0 y 1.0."
            ) from exc

        if not CONFIDENCE_FLOOR <= confidence <= CONFIDENCE_CEILING:
            raise ValidationError(
                f"La confianza debe estar entre {CONFIDENCE_FLOOR} y "
                f"{CONFIDENCE_CEILING}; se recibio {confidence}."
            )
        object.__setattr__(self, "confidence", confidence)

        object.__setattr__(
            self, "source", CategorizationSource(self.source)
        )

    def is_confident(self, threshold=DEFAULT_CONFIDENCE_THRESHOLD):
        """Indica si la confianza alcanza el umbral indicado (inclusive)."""
        return self.confidence >= threshold
