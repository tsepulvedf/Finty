"""Blueprints de analytics-service (contrato en ARCHITECTURE.md §10.6).

Autenticadas (el Gateway hace `auth_request` y pone `X-User-Id`):

    GET /api/v1/analytics/dashboard/?period=AAAA-MM
    GET /api/v1/analytics/insights/?period=AAAA-MM
    GET /api/v1/analytics/spending-patterns/?period=AAAA-MM   (periodo de referencia)
    POST /api/v1/analytics/reports/                  {period} -> 202, reporte PENDING (E2-M7)
    GET  /api/v1/analytics/reports/<id>/             estado: PENDING, READY o FAILED
    GET  /api/v1/analytics/reports/<id>/download/    el archivo (solo READY)

Publica, sin autenticacion (ADR-13, contrato provisional):

    GET /api/v1/public/spending-summary/?period=AAAA-MM

Sin `period`, el mes actual. Cada vista valida, construye el servicio, lo llama
y serializa; nada mas (RULES.md, regla 3). INV-06 lo aplica `api/gating.py` antes
del despacho: insights y patrones son premium, y el dashboard FREE cubre 3 meses.
"""
from flask import Blueprint, Response, jsonify

from api.context import (
    body_period,
    current_user_id,
    db_session,
    report_service,
    requested_language,
    requested_period,
)
from api.gating import earliest_visible_period, effective_thresholds, require_visible_period
from api.serializers import (
    dashboard_to_dict,
    insights_to_dict,
    patterns_to_dict,
    report_download_headers,
    report_to_dict,
    summary_to_dict,
)
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
    result = _service().dashboard(current_user_id(), period, earliest_visible_period())
    return jsonify(dashboard_to_dict(result))


@analytics.get("/insights/")
def insights():
    period = requested_period()
    return jsonify(insights_to_dict(period, _service().insights(current_user_id(), period)))


@analytics.get("/spending-patterns/")
def spending_patterns():
    reference = requested_period()
    patterns = _service().spending_patterns(current_user_id(), reference)
    return jsonify(patterns_to_dict(reference, _thresholds().pattern_window_months, patterns))


@analytics.post("/reports/")
def request_report():
    period = body_period()
    require_visible_period(period)
    record = report_service().request(current_user_id(), period, requested_language())
    return jsonify(report_to_dict(record)), 202


@analytics.get("/reports/<uuid:report_id>/")
def report_status(report_id):
    return jsonify(report_to_dict(report_service().get(current_user_id(), report_id)))


@analytics.get("/reports/<uuid:report_id>/download/")
def report_download(report_id):
    record = report_service().download(current_user_id(), report_id)
    return Response(record.content, content_type=record.media_type, headers=report_download_headers(record))


@public.get("/spending-summary/")
def spending_summary():
    period = requested_period()
    summary = PublicSummaryService(db_session(), _thresholds()).spending_summary(period)
    return jsonify(summary_to_dict(summary))
