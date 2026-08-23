"""Value Objects transversales del dominio (anillo de Dominio, Python puro).

Aqui vive `Money`, el Value Object que representa una cantidad monetaria como la
union indivisible de un `Decimal` y una moneda. Se ubica en `core` porque lo
comparten los contextos `identity` y `finance`, y duplicarlo romperia el lenguaje
ubicuo del glosario (ARCHITECTURE.md 12).

Este modulo no importa Django ni ninguna dependencia de infraestructura.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import total_ordering

from core.domain.exceptions import CurrencyMismatchError, ValidationError

# Toda cantidad monetaria se guarda con dos decimales exactos, igual que el
# DecimalField(max_digits=14, decimal_places=2) de la capa de persistencia.
CENTS = Decimal("0.01")

CURRENCY_CODE_LENGTH = 3


def validate_currency_code(code):
    """Normaliza y valida un codigo de moneda de tres letras.

    Devuelve el codigo en mayusculas. Lanza `ValidationError` si no son
    exactamente tres letras ASCII. Es una funcion de modulo y no un metodo de
    `Money` porque `ProfileService` valida `preferred_currency` con esta misma
    regla, sin construir un `Money` solo para eso.
    """
    if not isinstance(code, str):
        raise ValidationError(
            "El codigo de moneda debe ser una cadena de tres letras."
        )

    normalized = code.strip().upper()
    if len(normalized) != CURRENCY_CODE_LENGTH or not (
        normalized.isascii() and normalized.isalpha()
    ):
        raise ValidationError(
            f"'{code}' no es un codigo de moneda valido: se esperan exactamente "
            f"tres letras, por ejemplo 'COP'."
        )
    return normalized


def _coerce_amount(amount):
    """Convierte el monto recibido a `Decimal` cuantizado a dos decimales.

    Acepta `Decimal`, `int` y cadena numerica. Rechaza `float` de forma
    explicita porque su representacion binaria no puede expresar exactamente
    valores como 0.10 y arrastraria errores de redondeo al dinero.
    """
    if isinstance(amount, bool):
        # bool es subclase de int; un booleano nunca es una cantidad de dinero.
        raise ValidationError("El monto no puede ser un booleano.")

    if isinstance(amount, float):
        raise ValidationError(
            "Money no acepta float por perdida de precision binaria. "
            "Usa Decimal('10.50') o la cadena '10.50'."
        )

    if isinstance(amount, Decimal):
        value = amount
    elif isinstance(amount, int):
        value = Decimal(amount)
    elif isinstance(amount, str):
        try:
            value = Decimal(amount.strip())
        except InvalidOperation as exc:
            raise ValidationError(
                f"'{amount}' no es una cantidad numerica valida."
            ) from exc
    else:
        raise ValidationError(
            f"Tipo de monto no soportado: {type(amount).__name__}. "
            f"Usa Decimal, int o una cadena numerica."
        )

    if not value.is_finite():
        raise ValidationError("El monto debe ser un numero finito.")

    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


@total_ordering
@dataclass(frozen=True)
class Money:
    """Cantidad monetaria inmutable: monto y moneda son un solo valor.

    Dos instancias son iguales si coinciden monto y moneda. Cualquier operacion
    entre monedas distintas lanza `CurrencyMismatchError` (INV-11): sumar pesos
    con dolares no es un error de redondeo, es un error de modelo.
    """

    amount: Decimal
    currency: str

    def __post_init__(self):
        """Normaliza y valida los atributos de una instancia congelada.

        El dataclass es `frozen`, asi que la normalizacion se escribe con
        `object.__setattr__`; es el unico punto del ciclo de vida donde el valor
        puede cambiar.
        """
        object.__setattr__(self, "amount", _coerce_amount(self.amount))
        object.__setattr__(self, "currency", validate_currency_code(self.currency))

    @classmethod
    def zero(cls, currency):
        """Construye la cantidad nula en la moneda indicada."""
        return cls(Decimal("0"), currency)

    def _require_same_currency(self, other):
        """Exige que `other` sea un `Money` de la misma moneda (INV-11)."""
        if not isinstance(other, Money):
            raise ValidationError(
                f"Solo se puede operar Money con Money, no con "
                f"{type(other).__name__}."
            )
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"No se pueden operar cantidades en {self.currency} y "
                f"{other.currency}."
            )

    def add(self, other):
        """Suma dos cantidades de la misma moneda."""
        self._require_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def subtract(self, other):
        """Resta dos cantidades de la misma moneda."""
        self._require_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def negate(self):
        """Devuelve la cantidad con el signo invertido."""
        return Money(-self.amount, self.currency)

    def is_zero(self):
        """Indica si la cantidad es exactamente cero."""
        return self.amount == Decimal("0")

    def is_negative(self):
        """Indica si la cantidad es menor que cero."""
        return self.amount < Decimal("0")

    def __add__(self, other):
        return self.add(other)

    def __sub__(self, other):
        return self.subtract(other)

    def __neg__(self):
        return self.negate()

    def __lt__(self, other):
        """Orden parcial dentro de una misma moneda.

        `functools.total_ordering` deriva `__le__`, `__gt__` y `__ge__` de este
        metodo y del `__eq__` que genera el dataclass.
        """
        self._require_same_currency(other)
        return self.amount < other.amount

    def __str__(self):
        return f"{self.amount} {self.currency}"
