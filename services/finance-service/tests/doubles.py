"""Dobles de prueba de finance-service.

Desde E2-M3b el `MockCategorizer` de produccion vive en `categorization-service`.
Los tests de este servicio necesitan un categorizador determinista que no pase
por la red, y este doble lo es: misma interfaz y misma procedencia (`mock`, A-14).
"""
from domain.interfaces import Categorizer
from domain.value_objects import CategorizationSource, CategorySuggestion, TransactionType
from infra.categorizers import FALLBACK_BY_TYPE


class MockCategorizer(Categorizer):
    """Devuelve una sugerencia fija; por defecto, la categoria de respaldo del tipo."""

    def __init__(self, category_name=None, confidence=1.0, source=CategorizationSource.MOCK):
        self._category_name = category_name
        self._confidence = confidence
        self._source = CategorizationSource(source)

    def categorize(self, description, amount, transaction_type):
        resolved = TransactionType.from_value(transaction_type)
        name = self._category_name or FALLBACK_BY_TYPE[resolved]
        return CategorySuggestion(name, self._confidence, self._source)
