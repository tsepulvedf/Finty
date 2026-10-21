"""Blueprints de analytics-service (contrato en ARCHITECTURE.md §10.6).

Autenticadas (el Gateway hace `auth_request` y pone `X-User-Id`):

    GET /api/v1/analytics/dashboard/?period=AAAA-MM
    GET /api/v1/analytics/insights/?period=AAAA-MM
    GET /api/v1/analytics/spending-patterns/?period=AAAA-MM   (periodo de referencia)

Publica, sin autenticacion (ADR-13, contrato provisional):

    GET /api/v1/public/spending-summary/?period=AAAA-MM

Sin `period`, el mes actual. Cada vista valida, construye el servicio, lo llama
y serializa; nada mas (RULES.md, regla 3). INV-06 lo aplica `api/gating.py` antes
del despacho: insights y patrones son premium, y el dashboard FREE cubre 3 meses.
"""
from flask import Blueprint, jsonify

from api.context import current_user_id, db_session, requested_period
from api.gating import effective_thresholds
from api.serializers import dashboard_to_dict, insights_to_dict, patterns_to_dict, summary_to_dict
from services import AnalyticsService, PublicSummaryService

analytics = Blueprint("analytics", __name__, url_prefix="/api/v1/analytics")
public = Blueprint("public", __name__, url_prefix="/api/v1/public")


def _thresholds():
    # Sin premium, la tendencia del dashboard cubre 3 meses (INV-06, api/gating.py).
    return effective_thresholds()


def _service():
    return AnalyticsService(db_session(), _thresholds())


@analytics.get("/dashboard/")
def dashboard():
    period = requested_period()
    return jsonify(dashboard_to_dict(_service().dashboard(current_user_id(), period)))


@analytics.get("/insights/")
def insights():
    period = requested_period()
    return jsonify(insights_to_dict(period, _service().insights(current_user_id(), period)))


@analytics.get("/spending-patterns/")
def spending_patterns():
    reference = requested_period()
    patterns = _service().spending_patterns(current_user_id(), reference)
    return jsonify(patterns_to_dict(reference, _thresholds().pattern_window_months, patterns))


@public.get("/spending-summary/")
def spending_summary():
    period = requested_period()
    summary = PublicSummaryService(db_session(), _thresholds()).spending_summary(period)
    return jsonify(summary_to_dict(summary))
