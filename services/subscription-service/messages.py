"""Catalogo unico de los mensajes que ve el usuario (anillo externo).

Los de validacion y HTTP son los de DRF 3.17 en `es-co`, iguales a los de
finance-service, para que todo `/api/v1/` responda con la misma forma. En E2-M8
cada constante se envuelve en `lazy_gettext` de Flask-Babel sin tocar a quien la
usa. Los mensajes de las excepciones del dominio se traducen por su `code`.
"""

# --- Validacion de entrada (equivalentes de los campos de DRF) ---------------

REQUIRED = "Este campo es requerido."
NULL = "Este campo no puede ser nulo."
BLANK = "Este campo no puede estar en blanco."
INVALID_STRING = "No es una cadena válida."
MAX_LENGTH = "Asegúrese de que este campo no tenga más de {max_length} caracteres."
MIN_LENGTH = "Asegúrese de que este campo tenga al menos {min_length} caracteres."
NULL_CHARACTERS = "Los caracteres nulos no están permitidos."
INVALID_CHOICE = '"{input}" no es una elección válida.'
INVALID_NUMBER = "Se requiere un número válido."
INVALID_INTEGER = "Introduzca un número entero válido."
MAX_DIGITS = "Asegúrese de que no haya más de {max_digits} dígitos en total."
MAX_DECIMAL_PLACES = "Asegúrese de que no haya más de {max_decimal_places} decimales."
MAX_WHOLE_DIGITS = (
    "Asegúrese de que no haya más de {max_whole_digits} dígitos en la parte entera."
)
MAX_STRING_LENGTH = "Cadena demasiado larga."
INVALID_UUID = "Debe ser un UUID válido."
INVALID_DATE = (
    "Fecha con formato erróneo. Use uno de los siguientes formatos en su lugar: "
    "{format}."
)
DATE_FORMAT_HINT = "YYYY-MM-DD"
DATETIME_NOT_DATE = "Se esperaba una fecha en vez de una fecha/hora."
INVALID_DATATYPE = "Datos inválidos. Se esperaba un diccionario pero es un {datatype}."
NO_DATA = "No data provided"

# --- Errores HTTP -----------------------------------------------------------

NOT_AUTHENTICATED = "Las credenciales de autenticación no se proveyeron."
NOT_FOUND = "No encontrado."
METHOD_NOT_ALLOWED = 'Método "{method}" no permitido.'
JSON_PARSE_ERROR = "JSON parse error - {error}"
UNSUPPORTED_MEDIA_TYPE = 'Tipo de medio "{media_type}" incompatible en la solicitud.'
SERVER_ERROR = "Error interno del servidor."
