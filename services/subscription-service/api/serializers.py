"""Representacion JSON de planes, suscripciones, pagos y derechos.

El precio viaja como texto decimal (`"29900.00"`) y tambien en centavos, que es
como lo guarda `Payment`.
"""


def _iso(moment):
    """En la zona del proceso (`America/Bogota`), como las fechas de finance-service."""
    return moment.astimezone().isoformat() if moment else None


def _price(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def plan_to_dict(plan):
    return {
        "code": plan.code.value,
        "price": _price(plan.price_in_cents),
        "price_in_cents": plan.price_in_cents,
        "currency": plan.currency,
        "period_months": plan.period_months,
        "history_months": plan.history_months,
        "benefits": [b.value for b in plan.benefits],
    }


def plans_to_dict(plans):
    return {"results": [plan_to_dict(p) for p in plans]}


def payment_to_dict(payment):
    if payment is None:
        return None
    return {
        "id": str(payment.id),
        "reference": payment.reference,
        "status": payment.status,
        "amount_in_cents": payment.amount_in_cents,
        "currency": payment.currency,
        "gateway": payment.gateway,
        "created_at": _iso(payment.created_at),
        "resolved_at": _iso(payment.resolved_at),
    }


def view_to_dict(view):
    record = view.record
    return {
        "plan": view.plan.code.value,
        "premium": view.entitlement.premium,
        "status": view.status.value if view.status else None,
        "current_period_start": _iso(record.current_period_start) if record else None,
        "current_period_end": _iso(record.current_period_end) if record else None,
        "canceled_at": _iso(record.canceled_at) if record else None,
        "benefits": [b.value for b in view.plan.benefits],
        "last_payment": payment_to_dict(view.last_payment),
    }


def checkout_to_dict(result):
    return {"subscription": view_to_dict(result.view), "payment": payment_to_dict(result.payment)}


def entitlement_to_dict(entitlement):
    return {"premium": entitlement.premium, "until": _iso(entitlement.until)}
