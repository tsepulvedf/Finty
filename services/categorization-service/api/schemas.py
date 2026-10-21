"""Esquema de entrada del contrato interno, con pydantic v2.

Validacion sintactica (RULES.md, regla 4): tipos, valores permitidos y longitud.
No reproduce los mensajes de DRF: este contrato no lo ve un cliente externo,
solo `finance-service`.
"""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import messages
from api.errors import InvalidRequest

MAX_DESCRIPTION_LENGTH = 255


class SuggestionRequest(BaseModel):
    """`POST /v1/suggestions/`: lo que se clasifica."""

    model_config = ConfigDict(extra="ignore", strict=True)

    description: str = Field(default="", max_length=MAX_DESCRIPTION_LENGTH)
    transaction_type: Literal["income", "expense"]


def parse_suggestion_request(body):
    """Valida el cuerpo crudo o lanza `InvalidRequest` con los errores por campo."""
    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except ValueError as exc:
        raise InvalidRequest(message=messages.INVALID_JSON) from exc
    if not isinstance(data, dict):
        raise InvalidRequest()
    try:
        return SuggestionRequest.model_validate(data)
    except ValidationError as exc:
        fields = {}
        for error in exc.errors():
            fields.setdefault(str(error["loc"][0]), []).append(error["msg"])
        raise InvalidRequest(fields=fields) from exc
