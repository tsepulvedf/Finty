"""Constantes y ayudantes de la suite de contrato.

Los textos esperados son los que respondia el monolito (DRF 3.17, `es-co`).
"""
import uuid
from datetime import date, timedelta
from urllib.parse import urlsplit

ACCOUNTS = "/api/v1/accounts/"
CATEGORIES = "/api/v1/categories/"
TRANSACTIONS = "/api/v1/transactions/"

YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()

NOT_AUTHENTICATED = {"detail": "Las credenciales de autenticación no se proveyeron."}
INVALID_TOKEN = {"detail": "Token inválido."}
TOKEN_WITHOUT_CREDENTIALS = {
    "detail": "Cabecera token inválida. Las credenciales no fueron suministradas."
}
TOKEN_WITH_SPACES = {
    "detail": "Cabecera token inválida. La cadena token no debe contener espacios."
}
NOT_FOUND = {"detail": "No encontrado."}
INVALID_PAGE = {"detail": "Página inválida."}
THROTTLED = {"detail": "Solicitud fue regulada (throttled)."}

REQUIRED = "Este campo es requerido."
NULL = "Este campo no puede ser nulo."
BLANK = "Este campo no puede estar en blanco."
INVALID_UUID = "Debe ser un UUID válido."
INVALID_NUMBER = "Se requiere un número válido."
INVALID_DATE = (
    "Fecha con formato erróneo. Use uno de los siguientes formatos en su lugar: "
    "YYYY-MM-DD."
)

ACCOUNT_FIELDS = [
    "id", "name", "type", "balance", "opening_balance", "currency", "is_archived",
    "created_at",
]
TRANSACTION_FIELDS = [
    "id", "account", "account_name", "amount", "type", "category", "category_name",
    "description", "occurred_on", "categorization_source",
    "categorization_confidence", "created_at",
]


def method_not_allowed(method):
    return {"detail": f'Método "{method}" no permitido.'}


def model_not_found(model):
    """404 de `get_object_or_404` con un id valido que no existe (D-19)."""
    return {"detail": f"No {model} matches the given query."}


def unique(prefix):
    """Nombre unico para que las corridas no choquen entre si."""
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def create_account(user, name=None, kind="bank", **extra):
    """Crea una cuenta y devuelve su cuerpo."""
    body = {"name": name or unique("Cuenta"), "type": kind}
    body.update(extra)
    response = user.client.post(ACCOUNTS, body)
    assert response.status == 201, response.text
    return response.json


def register(user, account_id, amount="120000", kind="expense", **extra):
    """Registra una transaccion y devuelve la respuesta cruda."""
    body = {
        "account_id": account_id,
        "amount": amount,
        "type": kind,
        "occurred_on": extra.pop("occurred_on", YESTERDAY),
    }
    body.update(extra)
    return user.client.post(TRANSACTIONS, body)


def error_code(response):
    return response.json["error"]["code"]


def all_ids(client, path):
    """Ids de todas las paginas de un listado, siguiendo los enlaces `next`."""
    ids = set()
    while path:
        body = client.get(path).json
        ids |= {item["id"] for item in body["results"]}
        following = body["next"]
        path = None
        if following:
            parts = urlsplit(following)
            path = f"{parts.path}?{parts.query}" if parts.query else parts.path
    return ids
