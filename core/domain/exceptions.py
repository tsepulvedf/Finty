"""Jerarquia de excepciones del dominio (anillo de Dominio, Python puro).

El dominio y los servicios lanzan unicamente subclases de `DomainError`. Nunca
excepciones de Django ni de DRF: eso ataria el nucleo al framework y rompería la
regla de dependencia de ADR-02.

La traduccion a codigos HTTP es responsabilidad exclusiva de
`core/api/exception_handler.py`, en el anillo externo.
"""


class DomainError(Exception):
    """Error de dominio. Base de toda la jerarquia.

    Atributos:
        code: identificador estable del error, consumible por el cliente.
        message: descripcion legible del error.
    """

    default_code = "domain_error"
    default_message = "Se violo una regla del dominio."

    def __init__(self, message=None, code=None):
        self.message = message or self.default_message
        self.code = code or self.default_code
        super().__init__(self.message)

    def __str__(self):
        return self.message


class ValidationError(DomainError):
    """Se violo una invariante de una entidad o value object."""

    default_code = "validation_error"
    default_message = "Los datos violan una invariante del dominio."


class BusinessRuleError(DomainError):
    """Se violo una regla de negocio en un caso de uso."""

    default_code = "business_rule_error"
    default_message = "La operacion viola una regla de negocio."


class NotFoundError(DomainError):
    """El recurso solicitado no existe."""

    default_code = "not_found"
    default_message = "El recurso solicitado no existe."


class PermissionDeniedError(DomainError):
    """El usuario intento acceder a un recurso que no le pertenece."""

    default_code = "permission_denied"
    default_message = "No tienes acceso a este recurso."


class CurrencyMismatchError(ValidationError):
    """Se intento operar dos cantidades en monedas distintas (INV-11)."""

    default_code = "currency_mismatch"
    default_message = "No se pueden operar cantidades en monedas distintas."


class AuthenticationError(DomainError):
    """Las credenciales presentadas no identifican a ningun usuario activo."""

    default_code = "authentication_error"
    default_message = "Credenciales invalidas."
