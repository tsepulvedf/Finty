"""Adaptador REST con respaldo local para mantener el contrato de Categorizer."""
import json
import logging
import math
from urllib.request import Request, urlopen

from finance.domain.interfaces import Categorizer
from finance.domain.value_objects import CategorySuggestion, CategorizationSource, TransactionType
from finance.infra.categorizers import (
    FALLBACK_BY_TYPE, KEYWORDS_BY_TYPE, RuleBasedCategorizer,
)

logger = logging.getLogger(__name__)


class RemoteCategorizer(Categorizer):
    def __init__(self, url, token, timeout=1.0, fallback=None):
        self._url = url
        self._token = token
        self._timeout = timeout
        self._fallback = fallback or RuleBasedCategorizer()

    def categorize(self, description, amount, transaction_type):
        try:
            resolved_type = TransactionType.from_value(transaction_type)
            payload = {"description": description, "amount": str(amount.amount),
                       "currency": amount.currency, "type": resolved_type.value}
            request = Request(self._url, data=json.dumps(payload).encode(), method="POST",
                              headers={"Content-Type": "application/json",
                                       "X-Service-Token": self._token})
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read(16 * 1024 + 1)
                if len(raw) > 16 * 1024:
                    raise ValueError("Respuesta demasiado grande")
                data = json.loads(raw)
            allowed = set(KEYWORDS_BY_TYPE[resolved_type]) | {FALLBACK_BY_TYPE[resolved_type]}
            if set(data) != {"category_name", "confidence", "source"}:
                raise ValueError("Contrato inesperado")
            if data["category_name"] not in allowed or data["source"] != "rule":
                raise ValueError("Categoria o procedencia incompatible")
            confidence = data["confidence"]
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
                raise ValueError("Confianza invalida")
            return CategorySuggestion(data["category_name"], confidence, CategorizationSource.RULE)
        except Exception:
            # Sin descripciones financieras ni credenciales en el log.
            logger.warning("Clasificacion remota no disponible; se usa el respaldo local.")
            suggestion = self._fallback.categorize(description, amount, transaction_type)
            return CategorySuggestion(suggestion.category_name,
                                      min(suggestion.confidence, 0.20), suggestion.source)
