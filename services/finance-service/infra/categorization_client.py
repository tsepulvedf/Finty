"""Cliente de `categorization-service`: implementa el puerto `Categorizer` (E2-M3b).

`TransactionService` sigue dependiendo solo de la ABC `Categorizer`; este
adaptador la implementa contra `POST /v1/suggestions/` del servicio de
categorizacion (contrato en ARCHITECTURE.md §10.4). Es el mismo patron de
respaldo que `AICategorizer`, un nivel mas afuera.

**Respaldo (A-22).** El servicio remoto es una dependencia de red, asi que
puede no estar. Ante timeout, error de red, una respuesta 4xx o 5xx o un cuerpo
que no cumple el contrato, el adaptador clasifica con el `RuleBasedCategorizer`
local y la transaccion se registra igual. Como el `Categorizer` de siempre,
**nunca propaga una excepcion** (LSP).

**Procedencia veraz (A-14).** Si responde el remoto, se graba la procedencia
que el declara (`rule`, `mock`, o `rule` cuando su `AI` degrada). Si actua el
respaldo, se graba la del respaldo: `rule`. Una respuesta que diga `manual` se
rechaza: solo una persona clasifica manualmente.

**Catalogo (A-12).** La categoria que sugiere el remoto tiene que existir en el
catalogo de `finty_finance` y aplicar al tipo de la transaccion. Si no, se
rechaza y actua el respaldo, cuyas reglas si estan verificadas contra el
catalogo de este servicio (`tests/persistence/test_catalog_contract.py`). Asi una
regla nueva del remoto que no este sembrada aqui nunca rompe un registro.
"""
import json
import logging
import urllib.request

from domain.interfaces import Categorizer
from domain.value_objects import CategorizationSource, CategorySuggestion, TransactionType

logger = logging.getLogger(__name__)

SUGGESTIONS_PATH = "/v1/suggestions/"
DEFAULT_TIMEOUT_SECONDS = 1.0

# Procedencias que puede declarar el remoto: las de los mecanismos que viven alli.
REMOTE_SOURCES = frozenset(
    {CategorizationSource.RULE, CategorizationSource.MOCK, CategorizationSource.AI}
)


class SuggestionRejected(Exception):
    """La respuesta del remoto llego, pero no se puede usar."""


class RemoteCategorizer(Categorizer):
    """Pide la sugerencia a `categorization-service`, con respaldo local.

    Args:
        base_url: URL interna del servicio, por ejemplo
            `http://categorization-service:8000`.
        catalog: funcion sin argumentos que devuelve `{nombre: applies_to}` del
            catalogo persistido. Se llama solo cuando hay una sugerencia que
            validar, asi que construir el adaptador no consulta la base.
        fallback: `Categorizer` local que actua cuando el remoto no sirve.
        timeout: segundos maximos de espera por el remoto. Corto: registrar una
            transaccion no puede quedar colgado de la red.
    """

    def __init__(self, base_url, catalog, fallback, timeout=DEFAULT_TIMEOUT_SECONDS):
        self._url = base_url.rstrip("/") + SUGGESTIONS_PATH
        self._catalog = catalog
        self._fallback = fallback
        self._timeout = timeout

    def categorize(self, description, amount, transaction_type):
        """Sugerencia del remoto si es valida; si no, la del respaldo."""
        resolved_type = TransactionType.from_value(transaction_type)
        try:
            suggestion = self._ask(description, resolved_type)
            self._ensure_in_catalog(suggestion, resolved_type)
        except Exception as exc:  # noqa: BLE001 — el contrato del puerto es no propagar
            logger.warning(
                "categorization-service no utilizable (%s: %s); clasifica el respaldo local",
                type(exc).__name__,
                exc,
            )
            return self._fallback.categorize(description, amount, resolved_type)
        return suggestion

    def _ask(self, description, transaction_type):
        payload = json.dumps(
            {"description": description or "", "transaction_type": transaction_type.value}
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        # urlopen lanza HTTPError ante 4xx y 5xx, y URLError o TimeoutError ante
        # fallos de red: todos terminan en el respaldo.
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            body = json.loads(response.read().decode("utf-8"))

        source = CategorizationSource(body["source"])
        if source not in REMOTE_SOURCES:
            raise SuggestionRejected(f"procedencia '{source.value}' no valida para el remoto")
        return CategorySuggestion(body["category_name"], body["confidence"], source)

    def _ensure_in_catalog(self, suggestion, transaction_type):
        applies_to = self._catalog().get(suggestion.category_name)
        if applies_to != transaction_type.value:
            raise SuggestionRejected(
                f"'{suggestion.category_name}' no esta en el catalogo para "
                f"'{transaction_type.value}'"
            )
