"""Esquemas de entrada del contrato `/api/v1/` (anillo externo), con pydantic v2.

Uno por cada serializer de entrada de `finance/api/serializers.py`, con los
mismos campos, longitudes y obligatoriedad. La semantica de cada campo la
aportan los validadores de `api/fields.py`.

`validate_input()` produce los errores con la forma de DRF:
`{"campo": ["mensaje", ...]}`, o `{"non_field_errors": [...]}` si el cuerpo no es
un objeto. Los blueprints solo la llaman; no interpretan errores.
"""
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PlainValidator, ValidationError

import messages
from api import fields
from api.errors import InvalidInput
from domain.value_objects import AccountType, TransactionType

MAX_ACCOUNT_NAME_LENGTH = 120
MAX_CATEGORY_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 255
CURRENCY_CODE_LENGTH = 3

MONEY_MAX_DIGITS = 14
MONEY_DECIMAL_PLACES = 2

# Los valores validos salen de los enums del dominio: una sola fuente de verdad.
ACCOUNT_TYPE_VALUES = [member.value for member in AccountType]
TRANSACTION_TYPE_VALUES = [member.value for member in TransactionType]

NON_FIELD_ERRORS = "non_field_errors"
MISSING = "missing"

# El validador envuelve el tipo completo, opcional incluido: con `Tipo | None`
# fuera del `Annotated`, pydantic aceptaria un `null` explicito sin llamarlo, y
# DRF lo rechaza con "Este campo no puede ser nulo.". Que el campo falte o no lo
# decide el valor por defecto del esquema, no el tipo.
_char_name = fields.char(MAX_ACCOUNT_NAME_LENGTH)
_char_category = fields.char(MAX_CATEGORY_NAME_LENGTH)
_money = fields.money(MONEY_MAX_DIGITS, MONEY_DECIMAL_PLACES)

AccountName = Annotated[str, PlainValidator(_char_name)]
CategoryName = Annotated[str, PlainValidator(_char_category)]
OptionalCategoryName = Annotated[str | None, PlainValidator(_char_category)]
Amount = Annotated[Decimal, PlainValidator(_money)]
OptionalAmount = Annotated[Decimal | None, PlainValidator(_money)]
OptionalIdentifier = Annotated[UUID | None, PlainValidator(fields.uuid_value())]
Identifier = Annotated[UUID, PlainValidator(fields.uuid_value())]
Day = Annotated[date, PlainValidator(fields.date_value())]
OptionalDay = Annotated[date | None, PlainValidator(fields.date_value())]


class _Input(BaseModel):
    """Base de los esquemas: los campos desconocidos se ignoran, como en DRF."""

    model_config = ConfigDict(extra="ignore")


class AccountInput(_Input):
    """Crear una cuenta (`AccountInputSerializer`)."""

    name: AccountName
    type: Annotated[str, PlainValidator(fields.choice(ACCOUNT_TYPE_VALUES))]
    initial_balance: OptionalAmount = None
    currency: Annotated[
        str | None,
        PlainValidator(
            fields.char(
                max_length=CURRENCY_CODE_LENGTH, min_length=CURRENCY_CODE_LENGTH
            )
        ),
    ] = None


class AccountRename(_Input):
    """Renombrar una cuenta (`AccountRenameSerializer`): solo el nombre."""

    name: AccountName


class TransactionInput(_Input):
    """Registrar una transaccion (`TransactionInputSerializer`).

    No valida que el monto sea distinto de cero ni que la fecha no sea futura:
    eso es semantica y vive en el dominio.
    """

    account_id: Identifier
    amount: Amount
    type: Annotated[str, PlainValidator(fields.choice(TRANSACTION_TYPE_VALUES))]
    occurred_on: Day
    description: Annotated[
        str, PlainValidator(fields.char(MAX_DESCRIPTION_LENGTH, allow_blank=True))
    ] = ""
    category_name: OptionalCategoryName = None


class RecategorizeInput(_Input):
    """Reclasificar manualmente una transaccion (`RecategorizeInputSerializer`)."""

    category_name: CategoryName


class TransactionFilter(_Input):
    """Filtros de `GET /transactions/` (`TransactionFilterSerializer`)."""

    account_id: OptionalIdentifier = None
    category_id: OptionalIdentifier = None
    date_from: OptionalDay = None
    date_to: OptionalDay = None


def validate_input(schema, data):
    """Valida `data` contra `schema` o lanza `InvalidInput` con la forma de DRF."""
    if data is None:
        raise InvalidInput({NON_FIELD_ERRORS: [messages.NO_DATA]})
    if not isinstance(data, dict):
        raise InvalidInput(
            {
                NON_FIELD_ERRORS: [
                    messages.INVALID_DATATYPE.format(datatype=type(data).__name__)
                ]
            }
        )

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        errors = {}
        for error in exc.errors():
            field = error["loc"][0]
            if error["type"] == MISSING:
                errors.setdefault(field, [messages.REQUIRED])
            else:
                errors.setdefault(field, error["ctx"]["messages"])
        raise InvalidInput(errors) from exc
