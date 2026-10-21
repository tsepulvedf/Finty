"""Esquemas de entrada (anillo externo), con pydantic v2 y los campos de DRF.

Sintaxis solamente (RULES.md, regla 4): que el plan sea FREE o PREMIUM. Que FREE
no se compre es una regla del dominio (422).
"""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainValidator, ValidationError

import messages
from api import fields
from api.errors import InvalidInput
from domain.value_objects import PlanCode

PLAN_VALUES = [member.value for member in PlanCode]
NON_FIELD_ERRORS = "non_field_errors"
MISSING = "missing"


class _Input(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CheckoutInput(_Input):
    plan: Annotated[str, PlainValidator(fields.choice(PLAN_VALUES))]


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
