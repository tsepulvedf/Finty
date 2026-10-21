"""Esquemas de entrada (anillo externo), con pydantic v2 y los campos de DRF.

Validacion sintactica solamente (RULES.md, regla 4). Que una respuesta valga de 1
a 3, que el aporte sea positivo o que el instrumento corresponda al perfil es del
dominio.

`validate_input()` produce los errores con la forma de DRF:
`{"campo": ["mensaje", ...]}`, igual que finance-service.
"""
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainValidator, ValidationError

import messages
from api import fields
from api.errors import InvalidInput
from domain.value_objects import InstrumentType

CURRENCY_CODE_LENGTH = 3
MONEY_MAX_DIGITS = 14
MONEY_DECIMAL_PLACES = 2

INSTRUMENT_TYPE_VALUES = [member.value for member in InstrumentType]

NON_FIELD_ERRORS = "non_field_errors"
MISSING = "missing"

Answer = Annotated[int, PlainValidator(fields.integer())]
Currency = Annotated[
    str, PlainValidator(fields.char(max_length=CURRENCY_CODE_LENGTH, min_length=CURRENCY_CODE_LENGTH))
]
OptionalCurrency = Annotated[
    str | None,
    PlainValidator(fields.char(max_length=CURRENCY_CODE_LENGTH, min_length=CURRENCY_CODE_LENGTH)),
]


class _Input(BaseModel):
    """Los campos desconocidos se ignoran, como en DRF."""

    model_config = ConfigDict(extra="ignore")


class RiskProfileInput(_Input):
    """Las cinco respuestas del cuestionario (§6.6)."""

    investment_horizon: Answer
    loss_reaction: Answer
    experience: Answer
    income_stability: Answer
    goal: Answer


class InvestmentPlanInput(_Input):
    instrument_type: Annotated[str, PlainValidator(fields.choice(INSTRUMENT_TYPE_VALUES))]
    monthly_contribution: Annotated[Decimal, PlainValidator(fields.money(MONEY_MAX_DIGITS, MONEY_DECIMAL_PLACES))]
    horizon_months: Annotated[int, PlainValidator(fields.integer())]
    currency: OptionalCurrency = None


class ExchangeRateQuery(_Input):
    base: Currency
    target: Currency


class RecommendationQuery(_Input):
    display_currency: OptionalCurrency = None


def validate_input(schema, data):
    """Valida `data` contra `schema` o lanza `InvalidInput` con la forma de DRF."""
    if data is None:
        raise InvalidInput({NON_FIELD_ERRORS: [messages.NO_DATA]})
    if not isinstance(data, dict):
        raise InvalidInput(
            {NON_FIELD_ERRORS: [messages.INVALID_DATATYPE.format(datatype=type(data).__name__)]}
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
