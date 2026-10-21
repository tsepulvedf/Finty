"""Caso de uso de `categorization-service` (anillo de Servicios).

Un solo caso de uso: sugerir la categoria de una transaccion a partir de su
descripcion y su tipo. El servicio no tiene base de datos ni estado (§3.1): la
clasificacion no depende del usuario ni de nada persistido.

**Inversion de dependencias.** `CategorizationService` recibe un `Categorizer`
por constructor y depende solo de la ABC. Quien elige la implementacion es el
blueprint, que se la pide a `CategorizerFactory` (el Factory Method del proyecto,
ARCHITECTURE.md 6.1).
"""
from domain.value_objects import TransactionType


class CategorizationService:
    """Sugiere categorias con el `Categorizer` inyectado."""

    def __init__(self, categorizer):
        self._categorizer = categorizer

    def suggest(self, description, transaction_type):
        """Devuelve un `CategorySuggestion` para la transaccion descrita.

        El monto no viaja en el contrato HTTP (ver `api/routes.py`): ninguna
        implementacion lo usa para decidir, asi que se pasa `None`.
        """
        return self._categorizer.categorize(
            description, None, TransactionType.from_value(transaction_type)
        )
