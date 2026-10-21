"""Mensajes de error del contrato interno de `categorization-service`.

Los consume otro servicio, no una persona: no pasan por gettext. Estan en un
solo modulo por la misma razon que en `finance-service`, para que no queden
textos sueltos en los blueprints.
"""

INVALID_REQUEST = "La solicitud no cumple el contrato de sugerencias."
NOT_FOUND = "La ruta no existe."
METHOD_NOT_ALLOWED = "Metodo no permitido."
INVALID_JSON = "El cuerpo no es JSON valido."
CONFIGURATION_ERROR = "El servicio esta mal configurado."
SERVER_ERROR = "Error interno del servidor."
