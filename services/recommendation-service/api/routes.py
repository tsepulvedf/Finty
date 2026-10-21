"""Blueprints de recommendation-service (§10.8).

Los blueprints no piensan (RULES.md, regla 3): validan la entrada, llaman al
servicio y traducen el resultado a JSON. La identidad viene de `X-User-Id`, y
INV-06 lo aplica `api/gating.py` antes del despacho.
"""
from flask import Blueprint, jsonify

from api.context import (
    current_user_id,
    exchange_rate_service,
    investment_plan_service,
    recommendation_service,
    risk_profile_service,
)
from api.gating import investment_lock
from api.parsing import query_values, request_data
from api.schemas import (
    ExchangeRateQuery,
    InvestmentPlanInput,
    RecommendationQuery,
    RiskProfileInput,
    validate_input,
)
from api.serializers import (
    exchange_rate_to_dict,
    plan_to_dict,
    plans_to_dict,
    report_to_dict,
    risk_profile_to_dict,
)

recommendations = Blueprint("recommendations", __name__, url_prefix="/api/v1/recommendations")
investment_plans = Blueprint("investment_plans", __name__, url_prefix="/api/v1/investment-plans")
exchange_rates = Blueprint("exchange_rates", __name__, url_prefix="/api/v1/exchange-rates")


@recommendations.get("/")
def list_recommendations():
    query = validate_input(RecommendationQuery, query_values())
    report = recommendation_service().recommendations(current_user_id(), query.display_currency, investment_lock())
    return jsonify(report_to_dict(report))


@recommendations.get("/risk-profile/")
def get_risk_profile():
    return jsonify(risk_profile_to_dict(risk_profile_service().get(current_user_id())))


@recommendations.put("/risk-profile/")
def put_risk_profile():
    answers = validate_input(RiskProfileInput, request_data())
    saved = risk_profile_service().save(current_user_id(), answers.model_dump())
    return jsonify(risk_profile_to_dict(saved))


@investment_plans.get("/")
def list_plans():
    return jsonify(plans_to_dict(investment_plan_service().list(current_user_id())))


@investment_plans.post("/")
def create_plan():
    data = validate_input(InvestmentPlanInput, request_data())
    view = investment_plan_service().create(
        current_user_id(),
        data.instrument_type,
        data.monthly_contribution,
        data.currency,
        data.horizon_months,
    )
    return jsonify(plan_to_dict(view)), 201


@investment_plans.get("/<uuid:plan_id>/")
def get_plan(plan_id):
    return jsonify(plan_to_dict(investment_plan_service().get(current_user_id(), plan_id)))


@investment_plans.delete("/<uuid:plan_id>/")
def delete_plan(plan_id):
    investment_plan_service().delete(current_user_id(), plan_id)
    return "", 204


@exchange_rates.get("/")
def get_exchange_rate():
    query = validate_input(ExchangeRateQuery, query_values())
    return jsonify(exchange_rate_to_dict(exchange_rate_service().rate(query.base, query.target)))
