"""Valida el contrato y ejecuta las reglas extraidas, sin ORM."""
import re

from core.domain.exceptions import ValidationError
from core.domain.value_objects import Money
from finance.domain.value_objects import TransactionType
from finance.infra.categorizers import RuleBasedCategorizer


class CategorizationService:
    def __init__(self, categorizer=None):
        self._categorizer = categorizer or RuleBasedCategorizer()

    def suggest(self, payload):
        if not isinstance(payload, dict):
            raise ValidationError("El cuerpo debe ser un objeto JSON.")
        expected = {"description", "amount", "currency", "type"}
        if set(payload) != expected:
            raise ValidationError("Envia exactamente description, amount, currency y type.")
        description = payload["description"]
        if not isinstance(description, str) or len(description) > 255:
            raise ValidationError("description debe ser texto de hasta 255 caracteres.")
        amount = payload["amount"]
        if not isinstance(amount, str) or not re.fullmatch(r"[0-9]{1,12}(\.[0-9]{1,2})?", amount):
            raise ValidationError("amount debe ser una cadena positiva con hasta 12 enteros y 2 decimales.")
        money = Money(amount, payload["currency"])
        if money.is_zero():
            raise ValidationError("amount debe ser mayor que cero.")
        transaction_type = TransactionType.from_value(payload["type"])
        suggestion = self._categorizer.categorize(description, money, transaction_type)
        return {
            "category_name": suggestion.category_name,
            "confidence": suggestion.confidence,
            "source": suggestion.source.value,
        }
