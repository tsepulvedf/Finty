"""Esquemas de entrada (anillo externo), con pydantic v2 y los campos de DRF.

Sintaxis solamente (RULES.md, regla 4): que el plan sea FREE o PREMIUM. Que FREE
no se compre es una regla del dominio (422).

**El checkout no recibe datos de tarjeta** (ADR-14, C-33). `CheckoutInput` acepta
solo `plan` y rechaza con 400 cualquier otro campo (`extra="forbid"`): un
`card_number` o un `cvc` nunca llegan al servicio, al log ni a la base. El
formulario de tarjeta del frontend es una simulacion y no los envia (E2-M8).
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
EXTRA_FORBIDDEN = "extra_forbidden"


class _Input(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CheckoutInput(_Input):
    """Solo `{plan}`. Cualquier otro campo es 400: la API no acepta datos de tarjeta."""

    model_config = ConfigDict(extra="forbid")

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
            elif error["type"] == EXTRA_FORBIDDEN:
                # Solo el nombre del campo: el valor recibido nunca se repite.
                errors.setdefault(field, [messages.FIELD_NOT_ALLOWED])
            else:
                errors.setdefault(field, error["ctx"]["messages"])
        # `from None`: la excepcion de pydantic guarda los valores recibidos
        # (`input_value`). Sin encadenarla, un numero de tarjeta enviado por error
        # no puede terminar en una traza del log.
        raise InvalidInput(errors) from None
