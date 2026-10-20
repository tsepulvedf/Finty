"""Catalogo unico de los mensajes que ve el usuario (anillo externo).

Todo texto que `finance-service` devuelve en una respuesta y que no nace en el
dominio esta aqui: validacion de entrada, errores HTTP, paginacion y los mensajes
que `services.py` compone al lanzar errores de dominio. En E2-M8 cada constante
se envuelve en `lazy_gettext` de Flask-Babel sin tocar a quien la usa.

**Por que los textos son estos y no otros.** Reproducen literalmente los del
monolito: los de validacion y HTTP son los de DRF 3.17 en `es-co`, extraidos de
la instalacion que corre en el contenedor `django`; los de servicio son los de
`finance/services.py`. Es parte de mantener el mismo contrato (ADR-08).

**Lo que no esta aqui:** los mensajes por defecto de las excepciones de
`domain/`. El dominio es Python puro y no puede depender de Flask-Babel (A-16);
esos se traduciran en el handler a partir de su `code`, que es estable.

Las plantillas usan `str.format` con argumentos nombrados.
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
# Mensaje de `get_object_or_404` de Django, que DRF 3.17 conserva cuando el id
# tiene forma valida pero no existe. Django no lo traduce: queda en ingles.
MODEL_NOT_FOUND = "No {model} matches the given query."
METHOD_NOT_ALLOWED = 'Método "{method}" no permitido.'
JSON_PARSE_ERROR = "JSON parse error - {error}"
UNSUPPORTED_MEDIA_TYPE = 'Tipo de medio "{media_type}" incompatible en la solicitud.'
INVALID_PAGE = "Página inválida."
SERVER_ERROR = "Error interno del servidor."

# --- Mensajes que compone la capa de servicios ------------------------------

DUPLICATE_ACCOUNT_NAME = "Ya tienes una cuenta llamada '{name}'."
ACCOUNT_HAS_TRANSACTIONS = (
    "La cuenta '{name}' tiene transacciones asociadas. "
    "Archivala en lugar de eliminarla."
)
CATEGORY_NOT_FOUND = "No existe la categoria '{name}'."
CATEGORY_TYPE_MISMATCH = (
    "La categoria '{category}' aplica a movimientos de tipo '{applies_to}', "
    "no a '{transaction_type}'."
)
