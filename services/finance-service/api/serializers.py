"""Representacion de salida del contrato `/api/v1/` (anillo externo).

Mismos campos, mismo orden y mismos formatos que los `ModelSerializer` de salida
del monolito:

- Dinero como cadena con dos decimales (`"1000000.00"`), nunca como float.
- Fechas `AAAA-MM-DD`; instantes en ISO 8601 en la zona `TIME_ZONE`
  (`America/Bogota`, como `settings.py`), con `Z` si la zona es UTC.
- `user_id` **no se expone**: quien consulta ya sabe quien es.
- `account_name` y `category_name` aplanan las relaciones.
"""
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import current_app

CENTS = Decimal("0.01")
UTC_SUFFIX = "+00:00"


def _money(value):
    return f"{value.quantize(CENTS):f}"


def _instant(value):
    local = value.astimezone(ZoneInfo(current_app.config["TIME_ZONE"]))
    text = local.isoformat()
    return text[: -len(UTC_SUFFIX)] + "Z" if text.endswith(UTC_SUFFIX) else text


def _optional_id(value):
    return str(value) if value is not None else None


def category_to_dict(category):
    """Salida de `CategoryOutputSerializer`."""
    return {
        "id": str(category.id),
        "name": category.name,
        "applies_to": category.applies_to,
    }


def account_to_dict(account):
    """Salida de `AccountOutputSerializer`."""
    return {
        "id": str(account.id),
        "name": account.name,
        "type": account.type,
        "balance": _money(account.balance),
        "opening_balance": _money(account.opening_balance),
        "currency": account.currency,
        "is_archived": account.is_archived,
        "created_at": _instant(account.created_at),
    }


def summary_to_dict(balances):
    """`GET /accounts/summary/`: una fila por moneda, sin un total que las mezcle."""
    return {
        "currencies": [
            {
                "currency": item.currency,
                "balance": _money(item.balance.amount),
                "accounts": item.accounts,
            }
            for item in balances
        ]
    }


def transaction_to_dict(movement):
    """Salida de `TransactionOutputSerializer`."""
    category = movement.category
    confidence = movement.categorization_confidence
    return {
        "id": str(movement.id),
        "account": str(movement.account_id),
        "account_name": movement.account.name,
        "amount": _money(movement.amount),
        "type": movement.type,
        "category": _optional_id(movement.category_id),
        "category_name": category.name if category is not None else None,
        "description": movement.description,
        "occurred_on": movement.occurred_on.isoformat(),
        "categorization_source": movement.categorization_source,
        "categorization_confidence": float(confidence) if confidence is not None else None,
        "created_at": _instant(movement.created_at),
    }
