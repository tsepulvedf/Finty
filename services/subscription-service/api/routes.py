"""Blueprints de subscription-service (§10.9).

Autenticadas por el Gateway:

    GET  /api/v1/subscriptions/plans/
    GET  /api/v1/subscriptions/me/
    POST /api/v1/subscriptions/checkout/      {"plan": "PREMIUM"}
    POST /api/v1/subscriptions/me/cancel/

Interna, solo por la red de Compose (Nginx bloquea `/internal/`):

    GET  /internal/entitlements/<user_id>     → {"premium": bool, "until": ...}
"""
from flask import Blueprint, jsonify

from api.context import current_user_id, subscription_service
from api.parsing import request_data
from api.schemas import CheckoutInput, validate_input
from api.serializers import checkout_to_dict, entitlement_to_dict, plans_to_dict, view_to_dict

subscriptions = Blueprint("subscriptions", __name__, url_prefix="/api/v1/subscriptions")
internal = Blueprint("internal", __name__, url_prefix="/internal")


@subscriptions.get("/plans/")
def plans():
    return jsonify(plans_to_dict(subscription_service().plans()))


@subscriptions.get("/me/")
def me():
    return jsonify(view_to_dict(subscription_service().current(current_user_id())))


@subscriptions.post("/checkout/")
def checkout():
    data = validate_input(CheckoutInput, request_data())
    result = subscription_service().checkout(current_user_id(), data.plan)
    return jsonify(checkout_to_dict(result)), 201


@subscriptions.post("/me/cancel/")
def cancel():
    return jsonify(view_to_dict(subscription_service().cancel(current_user_id())))


@internal.get("/entitlements/<uuid:user_id>")
def entitlements(user_id):
    return jsonify(entitlement_to_dict(subscription_service().entitlement(user_id)))
