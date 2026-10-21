"""La transaccion tal como la conoce analytics (anillo de Dominio).

`TransactionFact` es la entrada de todos los calculos: lo que `analytics` sabe
de una transaccion por los eventos de `finance-service`, sin consultarlo nunca
(ADR-10). Solo entran las vigentes: una transaccion borrada no llega aqui.
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from domain.period import Period
from domain.shared.value_objects import Money
from domain.value_objects import TransactionType

_NON_ALPHANUMERIC = re.compile(r"[^0-9a-z]+")


def normalize_description(text):
    """Minusculas, sin tildes y solo letras y numeros separados por un espacio.

    `"  Netflix   PREMIUM!"` y `"netflix premium"` son la misma descripcion.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALPHANUMERIC.sub(" ", without_accents.lower()).strip()


@dataclass(frozen=True)
class TransactionFact:
    """Una transaccion vigente de un usuario."""

    transaction_id: UUID
    account_id: UUID
    amount: Money
    transaction_type: TransactionType
    category_name: str | None
    description: str
    occurred_on: date

    def __post_init__(self):
        object.__setattr__(
            self, "transaction_type", TransactionType.from_value(self.transaction_type)
        )

    @property
    def period(self):
        return Period.of(self.occurred_on)

    @property
    def currency(self):
        return self.amount.currency

    @property
    def is_expense(self):
        return self.transaction_type is TransactionType.EXPENSE
