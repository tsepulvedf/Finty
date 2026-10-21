"""Representacion JSON de perfiles, recomendaciones, planes y tasas.

Dinero como texto decimal con dos cifras y su moneda al lado, nunca un float.
"""
from datetime import date
from decimal import Decimal
from enum import Enum

import messages
from domain.period import Period
from domain.shared.value_objects import Money

DISCLAIMER = {"code": messages.INVESTMENT_DISCLAIMER_CODE, "message": messages.INVESTMENT_DISCLAIMER}


def _value(value):
    if isinstance(value, Money):
        return f"{value.amount:f}"
    if isinstance(value, Decimal):
        return f"{value:f}"
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (Period, date)):
        return str(value) if isinstance(value, Period) else value.isoformat()
    if isinstance(value, tuple):
        # Meses del excedente: ((Period, Money), ...).
        if value and all(isinstance(item, tuple) and len(item) == 2 for item in value):
            return [{"period": str(p), "net": _value(m)} for p, m in value]
        return [_value(item) for item in value]
    return value


def _pairs(pairs):
    return {key: _value(value) for key, value in pairs}


def risk_profile_to_dict(saved):
    profile = saved.profile
    return {
        "answers": dict(profile.answers),
        "score": profile.score,
        "risk_profile_type": profile.profile_type.value,
        "updated_at": saved.updated_at.isoformat(),
    }


def exchange_rate_to_dict(rate):
    return {
        "base": rate.base,
        "target": rate.target,
        "rate": f"{rate.rate:f}",
        "source": rate.source.value,
        "valid_from": rate.valid_from.isoformat() if rate.valid_from else None,
        "valid_until": rate.valid_until.isoformat() if rate.valid_until else None,
        "fetched_on": rate.fetched_on.isoformat() if rate.fetched_on else None,
    }


def report_to_dict(report):
    return {
        "period": str(report.period),
        "degraded": report.degraded,
        "risk_profile_type": report.risk_profile_type.value if report.risk_profile_type else None,
        "display_currency": report.display_currency,
        "exchange_rates": [exchange_rate_to_dict(r) for r in report.exchange_rates],
        "recommendations": [
            {
                "code": item.recommendation.code,
                "kind": item.recommendation.kind.value,
                "source": item.recommendation.source.value,
                "params": _pairs(item.recommendation.params),
                "evidence": _pairs(item.recommendation.evidence),
                "display": (
                    {"currency": report.display_currency, "amounts": _pairs(item.display)}
                    if report.display_currency else None
                ),
                "disclaimer": DISCLAIMER if item.recommendation.has_disclaimer else None,
            }
            for item in report.items
        ],
    }


def plan_to_dict(view):
    record, projection = view.record, view.projection
    return {
        "id": str(record.id),
        "instrument_type": record.instrument_type,
        "risk_profile_type": record.risk_profile_type,
        "monthly_contribution": f"{record.monthly_contribution:f}",
        "currency": record.currency,
        "horizon_months": record.horizon_months,
        "created_at": record.created_at.isoformat(),
        "projection": {
            "annual_rate": f"{projection.annual_rate:f}",
            "rate_is_illustrative": True,
            "rate_note": messages.ILLUSTRATIVE_RATE_NOTE,
            "total_contributed": _value(projection.total_contributed),
            "projected_value": _value(projection.projected_value),
            "projected_gain": _value(projection.projected_gain),
        },
        "disclaimer": DISCLAIMER,
    }


def plans_to_dict(views):
    return {"count": len(views), "results": [plan_to_dict(v) for v in views]}
