"""Validadores de campo con la semantica de DRF, para usar con pydantic v2.

Copia de `finance-service/api/fields.py` mas `integer()`. Los esquemas de
`api/schemas.py` son modelos de pydantic, pero el contrato que
deben cumplir es el del monolito: mismas coerciones, mismo orden de
verificaciones y mismos mensajes que los campos de DRF 3.17 (`CharField`,
`ChoiceField`, `DecimalField`, `UUIDField`, `DateField`). Cada funcion de este
modulo devuelve un validador para `PlainValidator`, que recibe la entrada cruda y
hace toda la validacion del campo, como `run_validation()` en DRF.

Validacion **sintactica** solamente (RULES.md, regla 4): tipos, formato y
longitudes. Que el monto no sea cero o que la fecha no sea futura es del dominio.

Un error se lanza como `PydanticCustomError` con la lista de mensajes en el
contexto; `api/schemas.py` la convierte en `{"campo": ["mensaje", ...]}`.
"""
import datetime
import decimal
import re
import uuid

from pydantic_core import PydanticCustomError

import messages

FIELD_ERROR = "field_error"

# Igual que `DecimalField.MAX_STRING_LENGTH` de DRF.
DECIMAL_MAX_STRING_LENGTH = 1000

# `django.utils.dateparse.date_re`: respaldo cuando `fromisoformat` no reconoce
# la cadena (por ejemplo, "2026-1-5").
DATE_RE = re.compile(r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})$")

SURROGATE_RANGE = range(0xD800, 0xE000)
SURROGATE_MESSAGE = "Surrogate characters are not allowed: U+{code_point:X}."


def _fail(*field_messages):
    """Rechaza el campo con uno o mas mensajes ya formateados."""
    raise PydanticCustomError(
        FIELD_ERROR,
        "{message}",
        {"message": field_messages[0], "messages": list(field_messages)},
    )


def char(max_length=None, min_length=None, allow_blank=False):
    """Equivalente de `serializers.CharField` (con `trim_whitespace=True`)."""

    def validate(data):
        if data is None:
            _fail(messages.NULL)
        # DRF comprueba el blanco antes que el tipo, sobre la cadena recortada.
        if data == "" or str(data).strip() == "":
            if not allow_blank:
                _fail(messages.BLANK)
            return ""
        # Numeros si, booleanos y compuestos no: igual que DRF.
        if isinstance(data, bool) or not isinstance(data, (str, int, float)):
            _fail(messages.INVALID_STRING)

        value = str(data).strip()

        # DRF corre todos los validadores y reporta todos los que fallen.
        errors = []
        if max_length is not None and len(value) > max_length:
            errors.append(messages.MAX_LENGTH.format(max_length=max_length))
        if min_length is not None and len(value) < min_length:
            errors.append(messages.MIN_LENGTH.format(min_length=min_length))
        if "\x00" in value:
            errors.append(messages.NULL_CHARACTERS)
        surrogate = next((c for c in value if ord(c) in SURROGATE_RANGE), None)
        if surrogate is not None:
            errors.append(SURROGATE_MESSAGE.format(code_point=ord(surrogate)))
        if errors:
            _fail(*errors)
        return value

    return validate


def choice(values):
    """Equivalente de `serializers.ChoiceField`: compara por `str(entrada)`."""
    allowed = {str(value): value for value in values}

    def validate(data):
        if data is None:
            _fail(messages.NULL)
        try:
            return allowed[str(data)]
        except KeyError:
            _fail(messages.INVALID_CHOICE.format(input=data))

    return validate


def _check_precision(value, max_digits, decimal_places):
    """`DecimalField.validate_precision` de DRF, paso por paso."""
    _, digits, exponent = value.as_tuple()

    if exponent >= 0:
        total_digits = len(digits) + exponent
        whole_digits = total_digits
        places = 0
    elif len(digits) > abs(exponent):
        total_digits = len(digits)
        whole_digits = total_digits - abs(exponent)
        places = abs(exponent)
    else:
        total_digits = abs(exponent)
        whole_digits = 0
        places = total_digits

    if total_digits > max_digits:
        _fail(messages.MAX_DIGITS.format(max_digits=max_digits))
    if places > decimal_places:
        _fail(messages.MAX_DECIMAL_PLACES.format(max_decimal_places=decimal_places))
    max_whole_digits = max_digits - decimal_places
    if whole_digits > max_whole_digits:
        _fail(messages.MAX_WHOLE_DIGITS.format(max_whole_digits=max_whole_digits))


def money(max_digits, decimal_places):
    """Equivalente de `serializers.DecimalField`: entrega un `Decimal`, nunca un float.

    La entrada se convierte a texto antes de interpretarla, como hace DRF con
    `smart_str`: un `10.5` del JSON llega como la cadena `"10.5"` y nunca como un
    flotante binario.
    """
    quantum = decimal.Decimal(".1") ** decimal_places

    def validate(data):
        if data is None:
            _fail(messages.NULL)
        text = str(data).strip()
        if len(text) > DECIMAL_MAX_STRING_LENGTH:
            _fail(messages.MAX_STRING_LENGTH)
        try:
            value = decimal.Decimal(text)
        except decimal.DecimalException:
            _fail(messages.INVALID_NUMBER)
        if value.is_nan() or value in (decimal.Decimal("Inf"), decimal.Decimal("-Inf")):
            _fail(messages.INVALID_NUMBER)

        _check_precision(value, max_digits, decimal_places)

        context = decimal.getcontext().copy()
        context.prec = max_digits
        return value.quantize(quantum, context=context)

    return validate


def uuid_value():
    """Equivalente de `serializers.UUIDField`.

    Como en DRF, un entero se interpreta como el valor numerico del UUID.
    """

    def validate(data):
        if data is None:
            _fail(messages.NULL)
        if isinstance(data, uuid.UUID):
            return data
        try:
            if isinstance(data, int):
                return uuid.UUID(int=data)
            if isinstance(data, str):
                return uuid.UUID(hex=data)
        except ValueError:
            pass
        _fail(messages.INVALID_UUID)

    return validate


def _parse_date(value):
    """`django.utils.dateparse.parse_date`: ISO 8601 y, de respaldo, `AAAA-M-D`."""
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        if match := DATE_RE.match(value):
            parts = {key: int(number) for key, number in match.groupdict().items()}
            return datetime.date(**parts)
    return None


def date_value():
    """Equivalente de `serializers.DateField` con el formato ISO 8601."""

    def validate(data):
        if data is None:
            _fail(messages.NULL)
        if isinstance(data, datetime.datetime):
            _fail(messages.DATETIME_NOT_DATE)
        if isinstance(data, datetime.date):
            return data
        try:
            parsed = _parse_date(data)
        except (ValueError, TypeError):
            parsed = None
        if parsed is None:
            _fail(messages.INVALID_DATE.format(format=messages.DATE_FORMAT_HINT))
        return parsed

    return validate


INTEGER_RE = re.compile(r"^-?\d+(\.0*)?$")


def integer():
    """Equivalente de `serializers.IntegerField`: `3`, `"3"` y `3.0` valen; `2.5` no.

    El rango (por ejemplo, 1 a 3 en el cuestionario) es semantica y lo valida el
    dominio, no este campo.
    """

    def validate(data):
        if data is None:
            _fail(messages.NULL)
        if isinstance(data, bool):
            _fail(messages.INVALID_INTEGER)
        if isinstance(data, int):
            return data
        text = str(data).strip()
        if len(text) > DECIMAL_MAX_STRING_LENGTH:
            _fail(messages.MAX_STRING_LENGTH)
        if not INTEGER_RE.match(text):
            _fail(messages.INVALID_INTEGER)
        return int(text.split(".")[0])

    return validate
