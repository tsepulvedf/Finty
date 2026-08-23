"""Value Objects del dominio `finance` (anillo de Dominio, Python puro).

Este modulo no importa Django. Solo la stdlib y `core.domain`.

**Por que `AccountType`, `TransactionType` y `CategorizationSource` son
enumeraciones y no `@dataclass(frozen=True)` como `Money`:**

`Money` es un dataclass porque combina dos datos (monto y moneda) cuyo conjunto
de valores validos es infinito y hay que validar en construccion. Estos tres, en
cambio, son conjuntos cerrados y finitos, y una `StrEnum` les da gratis las
cuatro propiedades que se buscan en un value object:

1. Inmutabilidad: los miembros de un enum no se reasignan.
2. Igualdad por valor: `AccountType.CASH is AccountType("cash")`.
3. Conjunto restringido por construccion: no existe un cuarto tipo de cuenta.
4. `.value` mapea directo a las `TextChoices` de Django en M3, sin traduccion.

Un dataclass congelado para representar `{cash, bank, credit}` obligaria a
escribir a mano la validacion del conjunto y la igualdad que el enum ya trae.

`TransactionDraft` y `AccountDraft` si son dataclasses: son agregados de datos
validados, no conjuntos cerrados.
"""
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from core.domain.exceptions import ValidationError
from core.domain.value_objects import Money
from finance.domain.exceptions import InvalidTransactionTypeError

CONFIDENCE_FLOOR = 0.0
CONFIDENCE_CEILING = 1.0
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


class AccountType(StrEnum):
    """Tipo de cuenta financiera. Conjunto cerrado (ARCHITECTURE.md 5.3)."""

    CASH = "cash"
    BANK = "bank"
    CREDIT = "credit"

    @classmethod
    def from_value(cls, raw):
        """Normaliza un valor externo a un miembro del enum.

        Acepta el propio miembro o una cadena en cualquier capitalizacion.
        Lanza `ValidationError` si el valor no pertenece al conjunto.
        """
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, str):
            raise ValidationError(
                f"El tipo de cuenta debe ser una cadena, no "
                f"{type(raw).__name__}."
            )
        try:
            return cls(raw.strip().lower())
        except ValueError as exc:
            valid = ", ".join(member.value for member in cls)
            raise ValidationError(
                f"'{raw}' no es un tipo de cuenta valido. Opciones: {valid}."
            ) from exc

    def allows_negative_balance(self):
        """Indica si el tipo de cuenta admite saldo negativo (INV-14).

        Solo el credito: una tarjeta puede quedar en rojo por definicion. El
        efectivo y una cuenta bancaria de deposito, no. `TransactionRules`
        consume esta regla; el tipo de cuenta es su unica fuente de verdad.
        """
        return self is AccountType.CREDIT


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
    """

    AI = "ai"
    RULE = "rule"
    MANUAL = "manual"


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


@dataclass(frozen=True)
class TransactionDraft:
    """Transaccion validada, todavia sin persistir.

    Es lo que devuelve `TransactionBuilder.build()` (M4). ARCHITECTURE.md 6.2
    decia que `build()` devolvia un `Transaction`; se corrige aqui: un builder
    alojado en `domain/` que importara los modelos de persistencia acoplaria el
    dominio al ORM de forma transitiva y romperia el ADR-01. Con el draft, el
    dominio valida las invariantes sin saber que Django existe, y es el Service
    (M5) quien traduce el draft a filas.

    **Este dataclass no valida nada en `__post_init__`, y es deliberado.** La
    validacion de invariantes (INV-04, INV-08, INV-09, INV-11, INV-12) ocurre
    una sola vez, en `.build()`. Cuando un `TransactionDraft` existe, ya es
    valido por construccion: no hay forma de obtener uno a medio validar. Repetir
    las comprobaciones aqui duplicaria las reglas en dos sitios y las dejaria
    libres de divergir.

    `account_id` se tipa como `str` o `UUID` de la stdlib, nunca como una
    instancia de modelo.
    """

    account_id: str | UUID
    amount: Money
    transaction_type: TransactionType
    occurred_on: date
    description: str
    category_name: str | None = None
    categorization_source: CategorizationSource | None = None
    confidence: float | None = None

    def signed_amount(self):
        """Devuelve el monto con el signo que corresponde al tipo.

        Un gasto de 50 COP es `-50.00 COP` para efectos de balance. Delega el
        signo en `TransactionType.sign()` en lugar de decidirlo aqui.
        """
        if self.transaction_type.sign() > 0:
            return self.amount
        return self.amount.negate()


@dataclass(frozen=True)
class AccountDraft:
    """Cuenta validada, todavia sin persistir.

    Es lo que devuelve `AccountBuilder.build()` (M4). Misma division que en
    `TransactionDraft`: el draft no valida, el builder si.
    """

    user_id: str | UUID
    name: str
    account_type: AccountType
    initial_balance: Money
