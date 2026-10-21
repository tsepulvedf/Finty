"""Contrato interno de `categorization-service` (ARCHITECTURE.md §10.4).

Un unico endpoint, alcanzable solo por la red interna de Docker: el servicio no
publica puertos y Nginx no lo enruta. No lleva `X-User-Id`: la clasificacion no
depende del usuario.

    POST /v1/suggestions/
    Content-Type: application/json

    {"description": "Almuerzo en el restaurante", "transaction_type": "expense"}

    200 {"category_name": "Alimentación", "confidence": 0.75, "source": "rule"}
    400 {"error": {"code": "invalid_request", "message": "...", "fields": {...}}}
    500 {"error": {"code": "configuration_error", ...}}   CATEGORIZER_PROVIDER invalido

- `description`: texto libre, opcional (por defecto ""), hasta 255 caracteres.
- `transaction_type`: `"income"` o `"expense"`.
- `source`: el mecanismo que realmente clasifico (A-14): `rule`, `mock` o `ai`.
  Con `CATEGORIZER_PROVIDER=AI` y sin cliente configurado (D-07), es `rule`.

El blueprint valida, construye el servicio con el categorizador que da la
fabrica, lo llama y serializa. Nada mas (RULES.md, regla 3).
"""
from flask import Blueprint, jsonify, request

from api.schemas import parse_suggestion_request
from infra.factories import CategorizerFactory
from services import CategorizationService

blueprint = Blueprint("categorization", __name__, url_prefix="/v1")


@blueprint.post("/suggestions/")
def suggest():
    """Sugiere categoria, confianza y procedencia para una transaccion."""
    data = parse_suggestion_request(request.get_data(cache=True))
    suggestion = CategorizationService(CategorizerFactory.get_categorizer()).suggest(
        data.description, data.transaction_type
    )
    return jsonify(
        {
            "category_name": suggestion.category_name,
            "confidence": suggestion.confidence,
            "source": suggestion.source.value,
        }
    )
