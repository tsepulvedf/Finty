"""Blueprints del contrato `/api/v1/` de `finance` (anillo externo).

Mismas rutas, metodos y codigos de estado que `finance/api/urls.py` y
`finance/api/views.py` del monolito. Cada vista hace exactamente cuatro cosas:
validar la entrada, construir el servicio con sus dependencias, llamarlo y
traducir el resultado a HTTP. Ningun calculo, ningun `if` sobre reglas de
negocio y ningun `try`: los errores los traduce `api/errors.py` (RULES.md,
regla 3).

La identidad sale solo de `X-User-Id` (`api/context.py`).
"""
from flask import Blueprint, jsonify

from api.context import current_user_id, db_session
from api.errors import or_404
from api.pagination import paginate
from api.parsing import query_flag, query_values, request_data
from api.schemas import (
    AccountInput,
    AccountRename,
    RecategorizeInput,
    TransactionFilter,
    TransactionInput,
    validate_input,
)
from api.serializers import account_to_dict, category_to_dict, transaction_to_dict
from infra.factories import CategorizerFactory
from services import AccountService, CategoryService, TransactionService

blueprint = Blueprint("finance", __name__, url_prefix="/api/v1")

NO_CONTENT = ("", 204)
CREATED = 201


def _transaction_service():
    """Servicio con el categorizador de la fabrica inyectado.

    El blueprint es el unico punto del servicio que conoce `CategorizerFactory`;
    `TransactionService` solo conoce la ABC `Categorizer` (DIP).
    """
    return TransactionService(db_session(), CategorizerFactory.get_categorizer())


# --- /categories/ ------------------------------------------------------------


@blueprint.get("/categories/")
def list_categories():
    """Catalogo global de solo lectura, paginado."""
    listing = CategoryService(db_session()).list_categories()
    return jsonify(paginate(listing, category_to_dict))


@blueprint.get("/categories/<lookup:pk>/")
def retrieve_category(pk):
    """Una categoria del catalogo."""
    category = or_404(CategoryService(db_session()).find_category(pk), "Category", pk)
    return jsonify(category_to_dict(category))


# --- /accounts/ --------------------------------------------------------------


@blueprint.get("/accounts/")
def list_accounts():
    """Cuentas del usuario; las archivadas solo con `include_archived`."""
    listing = AccountService(db_session()).list_accounts(
        current_user_id(), include_archived=query_flag("include_archived")
    )
    return jsonify(paginate(listing, account_to_dict))


@blueprint.post("/accounts/")
def create_account():
    """Crea una cuenta y devuelve 201."""
    data = validate_input(AccountInput, request_data())
    account = AccountService(db_session()).create_account(
        user_id=current_user_id(),
        name=data.name,
        account_type=data.type,
        initial_balance=data.initial_balance,
        currency=data.currency,
    )
    return jsonify(account_to_dict(account)), CREATED


@blueprint.get("/accounts/<lookup:pk>/")
def retrieve_account(pk):
    """Una cuenta del usuario, buscada dentro de su listado."""
    account = or_404(
        AccountService(db_session()).find_listed_account(
            current_user_id(), pk, include_archived=query_flag("include_archived")
        ),
        "Account",
        pk,
    )
    return jsonify(account_to_dict(account))


@blueprint.route("/accounts/<lookup:pk>/", methods=["PUT", "PATCH"])
def update_account(pk):
    """Renombra la cuenta; `PATCH` se comporta igual que `PUT`."""
    data = validate_input(AccountRename, request_data())
    account = AccountService(db_session()).rename_account(
        current_user_id(), pk, data.name
    )
    return jsonify(account_to_dict(account))


@blueprint.delete("/accounts/<lookup:pk>/")
def delete_account(pk):
    """Elimina una cuenta sin transacciones (INV-13) y devuelve 204."""
    AccountService(db_session()).delete_account(current_user_id(), pk)
    return NO_CONTENT


@blueprint.post("/accounts/<lookup:pk>/archive/")
def archive_account(pk):
    """Archiva sin borrar."""
    account = AccountService(db_session()).archive_account(current_user_id(), pk)
    return jsonify(account_to_dict(account))


# --- /transactions/ ----------------------------------------------------------


@blueprint.get("/transactions/")
def list_transactions():
    """Transacciones del usuario, con filtros opcionales, paginadas."""
    filters = validate_input(TransactionFilter, query_values())
    listing = _transaction_service().list_transactions(
        current_user_id(), **filters.model_dump(exclude_unset=True)
    )
    return jsonify(paginate(listing, transaction_to_dict))


@blueprint.post("/transactions/")
def register_transaction():
    """Registra una transaccion y devuelve 201."""
    data = validate_input(TransactionInput, request_data())
    movement = _transaction_service().register_transaction(
        user_id=current_user_id(),
        account_id=data.account_id,
        amount=data.amount,
        transaction_type=data.type,
        occurred_on=data.occurred_on,
        description=data.description,
        category_name=data.category_name,
    )
    return jsonify(transaction_to_dict(movement)), CREATED


@blueprint.get("/transactions/<django_uuid:pk>/")
def retrieve_transaction(pk):
    """Una transaccion del usuario."""
    movement = _transaction_service().get_transaction(current_user_id(), pk)
    return jsonify(transaction_to_dict(movement))


@blueprint.delete("/transactions/<django_uuid:pk>/")
def delete_transaction(pk):
    """Elimina la transaccion y deshace su efecto sobre el balance."""
    _transaction_service().delete_transaction(current_user_id(), pk)
    return NO_CONTENT


@blueprint.post("/transactions/<django_uuid:pk>/categorize/")
def recategorize_transaction(pk):
    """Reasigna la categoria. No mueve el balance."""
    data = validate_input(RecategorizeInput, request_data())
    movement = _transaction_service().recategorize(
        current_user_id(), pk, data.category_name
    )
    return jsonify(transaction_to_dict(movement))
