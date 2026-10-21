"""Catalogo unico de los mensajes que ve el usuario (para Flask-Babel en E2-M8).

Los de autenticacion, 404 y 405 son los mismos textos que `finance-service` y el
Gateway, para que el cliente vea un solo contrato de errores.
"""

INVALID_PERIOD = "Periodo invalido. Use el formato AAAA-MM, por ejemplo 2026-10."

NOT_AUTHENTICATED = "Las credenciales de autenticación no se proveyeron."
NOT_FOUND = "No encontrado."
METHOD_NOT_ALLOWED = 'Método "{method}" no permitido.'
SERVER_ERROR = "Error interno del servidor."
