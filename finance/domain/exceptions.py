"""Excepciones del dominio `finance` (anillo de Dominio, Python puro).

Desviacion respecto al arbol de ADR-04, que no lista este archivo: `finance` es
el contexto **Core** del mapa de bounded contexts (ARCHITECTURE.md 3), asi que
tiene un anillo de dominio completo y sus excepciones viven dentro de `domain/`,
junto a las reglas que las lanzan. El contexto de identidad, que es **Generic**,
no tiene carpeta `domain/` y sus excepciones estan en un modulo plano.

Todas heredan de `core.domain.exceptions`, de modo que el handler global las
traduce a HTTP por su superclase sin conocer ninguna de ellas: las que derivan de
`ValidationError` salen como 422, las de `BusinessRuleError` como 409, las de
`NotFoundError` como 404 y las de `PermissionDeniedError` como 403.

Este modulo no importa Django.
"""
from core.domain.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


class ZeroAmountError(ValidationError):
    """El monto de una transaccion no puede ser cero (INV-04)."""

    default_code = "zero_amount"
    default_message = "El monto de la transaccion no puede ser cero."


class InvalidTransactionTypeError(ValidationError):
    """El tipo de transaccion no pertenece al conjunto valido (INV-09)."""

    default_code = "invalid_transaction_type"
    default_message = "El tipo de transaccion no es valido."


class FutureTransactionDateError(ValidationError):
    """La fecha de la transaccion no puede estar en el futuro (INV-12)."""

    default_code = "future_transaction_date"
    default_message = "La fecha de la transaccion no puede estar en el futuro."


class UncategorizedTransactionError(ValidationError):
    """Se invoco la categorizacion pero no quedo categoria asignada (INV-08)."""

    default_code = "uncategorized_transaction"
    default_message = "La transaccion debe quedar categorizada."


class ArchivedAccountError(BusinessRuleError):
    """No se puede operar sobre una cuenta archivada."""

    default_code = "archived_account"
    default_message = "No se puede operar sobre una cuenta archivada."


class NegativeBalanceNotAllowedError(BusinessRuleError):
    """El tipo de cuenta no admite saldo negativo (INV-14).

    INV-14 se formaliza en este modulo. Venia del catalogo DDD original, que
    anotaba `balance >= 0 (dependiendo tipo)` sin darle identificador propio.
    """

    default_code = "negative_balance_not_allowed"
    default_message = "El saldo de esta cuenta no puede quedar en negativo."


class AccountHasTransactionsError(BusinessRuleError):
    """No se puede eliminar una cuenta que tiene transacciones (INV-13)."""

    default_code = "account_has_transactions"
    default_message = "No se puede eliminar una cuenta con transacciones."


class AccountNotOwnedError(PermissionDeniedError):
    """La cuenta pertenece a otro usuario (INV-03)."""

    default_code = "account_not_owned"
    default_message = "Esta cuenta no te pertenece."


class AccountNotFoundError(NotFoundError):
    """La cuenta solicitada no existe."""

    default_code = "account_not_found"
    default_message = "La cuenta solicitada no existe."


class TransactionNotFoundError(NotFoundError):
    """La transaccion solicitada no existe."""

    default_code = "transaction_not_found"
    default_message = "La transaccion solicitada no existe."


class CategoryNotFoundError(NotFoundError):
    """La categoria solicitada no existe."""

    default_code = "category_not_found"
    default_message = "La categoria solicitada no existe."


class NegativeAmountError(ValidationError):
    """El monto de una transaccion llego en negativo.

    Los montos se almacenan siempre positivos y el signo lo aporta
    `TransactionType.sign()`. Un `Money(-500)` con tipo `EXPENSE` produciria un
    doble negativo, asi que se rechaza en vez de normalizarse con `abs()` en
    silencio: es un error de quien llama, no algo que el dominio deba adivinar.
    """

    default_code = "negative_amount"
    default_message = "El monto de la transaccion no puede ser negativo."
