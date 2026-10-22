"""Representacion JSON de Dashboard, Insight, SpendingPattern y el resumen publico.

Dinero como texto decimal con dos cifras y su moneda al lado, nunca un float;
fracciones y porcentajes como texto decimal.
"""
from decimal import Decimal

from domain.period import Period
from domain.shared.value_objects import Money


def _value(value):
    if isinstance(value, Money):
        return f"{value.amount:f}"
    if isinstance(value, Decimal):
        return f"{value:f}"
    if isinstance(value, Period):
        return str(value)
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 for item in value):
            return [{"period": k, "total": _value(v)} for k, v in value]
        return [_value(item) for item in value]
    return value


def _totals(totals):
    return {
        "income": _value(totals.income),
        "expense": _value(totals.expense),
        "net": _value(totals.net),
    }


def dashboard_to_dict(dashboard):
    return {
        "period": str(dashboard.period),
        "currencies": [
            {
                "currency": section.currency,
                **_totals(section.totals),
                "categories": [
                    {
                        "category_name": c.category_name,
                        "transaction_type": c.transaction_type.value,
                        "total": _value(c.total),
                        "share": _value(c.share),
                    }
                    for c in section.categories
                ],
                "accounts": [
                    {"account_id": str(a.account_id), **_totals(a.totals)} for a in section.accounts
                ],
                "trend": [{"period": str(p.period), **_totals(p.totals)} for p in section.trend],
                # D-29: comparacion con el periodo anterior y tasa de ahorro.
                "previous": (
                    {"period": str(section.comparison.period), **_totals(section.comparison.totals)}
                    if section.comparison else None
                ),
                "expense_change_pct": (
                    _value(section.comparison.expense_change_pct)
                    if section.comparison and section.comparison.expense_change_pct is not None else None
                ),
                "savings_rate": _value(section.savings_rate) if section.savings_rate is not None else None,
            }
            for section in dashboard.currencies
        ],
    }


def insights_to_dict(period, insights):
    return {
        "period": str(period),
        "insights": [
            {
                "type": i.type.value,
                "code": i.code,
                "severity": i.severity.value,
                "period": str(i.period),
                "params": {k: _value(v) for k, v in i.params},
                "evidence": {k: _value(v) for k, v in i.evidence},
            }
            for i in insights
        ],
    }


def patterns_to_dict(reference, window_months, patterns):
    return {
        "reference_period": str(reference),
        "window_months": window_months,
        "patterns": [
            {
                "description": p.description,
                "category_name": p.category_name,
                "currency": p.currency,
                "average_amount": _value(p.average_amount),
                "months_present": p.months_present,
                "window_months": p.window_months,
                "occurrences": p.occurrences,
                "monthly_frequency": _value(p.monthly_frequency),
                "last_seen": p.last_seen.isoformat(),
            }
            for p in patterns
        ],
    }


def summary_to_dict(summary):
    return {
        "period": str(summary.period),
        "min_users": summary.min_users,
        "categories": [
            {
                "category_name": c.category_name,
                "currency": c.currency,
                "users": c.users,
                "total": _value(c.total),
                "average_per_user": _value(c.average_per_user),
            }
            for c in summary.categories
        ],
    }


def report_to_dict(record):
    """Estado de un reporte mensual (E2-M7). El archivo se pide aparte."""
    ready = record.status == "READY"
    return {
        "id": str(record.id),
        "period": record.period,
        "language": record.language,
        "status": record.status,
        "created_at": record.created_at.astimezone().isoformat(),
        "completed_at": record.completed_at.astimezone().isoformat() if record.completed_at else None,
        "filename": record.filename if ready else None,
        "download_url": f"/api/v1/analytics/reports/{record.id}/download/" if ready else None,
    }


def report_download_headers(record):
    """Cabeceras de la descarga: el navegador lo guarda con su nombre."""
    return {"Content-Disposition": f'attachment; filename="{record.filename}"'}
