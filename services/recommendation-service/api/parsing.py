"""Lectura del cuerpo y de la consulta de la peticion, como lo hacia DRF.

- Cuerpo vacio: `{}`, sin importar el `Content-Type`.
- Cuerpo JSON: se interpreta con `json` de la stdlib, rechazando `NaN` e
  `Infinity` como el `JSONParser` estricto de DRF.
- Cualquier otro tipo de contenido: 415. El monolito aceptaba tambien
  formularios; el contrato de Finty es JSON y el frontend solo envia JSON.
- Parametros de consulta repetidos: gana el **ultimo**, como `QueryDict.get()`.
"""
import json

from flask import request

import messages
from api.errors import ParseError, UnsupportedMediaType

JSON_MEDIA_TYPE = "application/json"
TRUTHY_QUERY_VALUES = {"1", "true", "yes", "on"}


def _reject_constant(constant):
    """Rechaza `NaN`, `Infinity` y `-Infinity` (`json.strict_constant` de DRF)."""
    raise ValueError(
        "Out of range float values are not JSON compliant: " + repr(constant)
    )


def request_data():
    """Cuerpo de la peticion ya interpretado."""
    body = request.get_data(cache=True)
    if not body:
        return {}

    if request.mimetype != JSON_MEDIA_TYPE:
        raise UnsupportedMediaType(
            messages.UNSUPPORTED_MEDIA_TYPE.format(
                media_type=request.headers.get("Content-Type", "")
            )
        )

    try:
        return json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
    except ValueError as exc:
        raise ParseError(messages.JSON_PARSE_ERROR.format(error=exc)) from exc


def query_values():
    """Parametros de consulta, uno por nombre: el ultimo valor recibido."""
    return {name: request.args.getlist(name)[-1] for name in request.args}


def query_value(name):
    """Ultimo valor de un parametro de consulta, o `None`."""
    return query_values().get(name)


def query_flag(name):
    """Interpreta un parametro de consulta como booleano. Formato, no negocio."""
    return (query_value(name) or "").strip().lower() in TRUTHY_QUERY_VALUES
