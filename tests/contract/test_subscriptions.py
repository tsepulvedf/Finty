"""subscription-service y el gating de INV-06 por el Gateway (§10.9, §7.1).

`lucia` es la unica usuaria FREE de la suite: el recorrido FREE → checkout →
PREMIUM → cancelacion va en un solo test, en orden, para no depender del orden
de los tests.

Opcional: `CONTRACT_SUBSCRIPTION_DOWN=1`, con `docker compose stop
subscription-service`. Se corre aparte (`-k SubscriptionCaido`): lo premium se
niega con 503 y lo gratuito sigue respondiendo.
"""
import os
from datetime import date

import pytest

from helpers import NOT_AUTHENTICATED

PLANS = "/api/v1/subscriptions/plans/"
ME = "/api/v1/subscriptions/me/"
CHECKOUT = "/api/v1/subscriptions/checkout/"
CANCEL = "/api/v1/subscriptions/me/cancel/"
INSIGHTS = "/api/v1/analytics/insights/"
PATTERNS = "/api/v1/analytics/spending-patterns/"
DASHBOARD = "/api/v1/analytics/dashboard/"
RECOMMENDATIONS = "/api/v1/recommendations/"
RISK = "/api/v1/recommendations/risk-profile/"
INVESTMENT_PLANS = "/api/v1/investment-plans/"

SUBSCRIPTION_DOWN_ENV = "CONTRACT_SUBSCRIPTION_DOWN"
subscription_down = os.environ.get(SUBSCRIPTION_DOWN_ENV) == "1"

FREE_BENEFITS = ["transaction_tracking", "standard_dashboard", "history_3_months"]
MODERATE = {"investment_horizon": 2, "loss_reaction": 2, "experience": 2, "income_stability": 2, "goal": 2}


def period(offset):
    """`AAAA-MM` desplazado `offset` meses desde el actual."""
    today = date.today()
    index = today.year * 12 + today.month - 1 + offset
    return f"{index // 12}-{index % 12 + 1:02d}"


def error_code(response):
    return response.json["error"]["code"]


@pytest.mark.skipif(subscription_down, reason=f"{SUBSCRIPTION_DOWN_ENV}=1")
class TestSuscripciones:
    @pytest.mark.parametrize("path", [PLANS, ME, "/api/v1/subscriptions"])
    def test_sin_token_401_del_gateway(self, anonimo, path):
        response = anonimo.get(path)
        assert (response.status, response.json) == (401, NOT_AUTHENTICATED)
        assert response.header("X-Finty-Route") == "subscription"

    def test_el_endpoint_interno_no_se_alcanza_desde_fuera(self, anonimo, ana):
        assert anonimo.get(f"/internal/entitlements/{ana.user_id}").status == 404

    def test_planes(self, ana):
        free, premium = ana.client.get(PLANS).json["results"]
        assert (free["code"], free["benefits"], free["history_months"]) == ("FREE", FREE_BENEFITS, 3)
        assert (premium["code"], premium["price"], premium["currency"], premium["period_months"]) == (
            "PREMIUM", "29900.00", "COP", 1,
        )

    @pytest.mark.parametrize("field, value", [
        ("card_number", "4242424242424242"), ("cvc", "987"), ("expiry", "12/31"),
    ])
    def test_el_checkout_rechaza_datos_de_tarjeta(self, ana, field, value):
        """ADR-14, C-33: el backend nunca recibe datos de tarjeta; solo `{plan}`."""
        response = ana.client.post(CHECKOUT, {"plan": "PREMIUM", field: value})
        assert response.status == 400
        assert response.json == {field: ["Este campo no está permitido."]}
        assert value not in response.text

    def test_free_no_se_compra(self, ana):
        response = ana.client.post(CHECKOUT, {"plan": "FREE"})
        assert (response.status, error_code(response)) == (422, "plan_not_purchasable")

    def test_de_free_a_premium_y_cancelacion(self, lucia):
        client = lucia.client

        # FREE: sin suscripcion.
        me = client.get(ME).json
        assert (me["plan"], me["premium"], me["status"], me["benefits"]) == ("FREE", False, None, FREE_BENEFITS)

        # INV-06: lo premium se niega con 403; lo gratuito responde.
        for path in (INSIGHTS, PATTERNS, f"{DASHBOARD}?period={period(-3)}", INVESTMENT_PLANS):
            response = client.get(path)
            assert (response.status, error_code(response)) == (403, "premium_required"), path
        for offset in (0, -1, -2):
            assert client.get(f"{DASHBOARD}?period={period(offset)}").status == 200
        assert client.put(RISK, MODERATE).status == 200
        free_recommendations = client.get(RECOMMENDATIONS).json
        assert free_recommendations["locked"] == [{"kind": "investment", "code": "premium_required"}]
        assert all(r["kind"] == "optimization" for r in free_recommendations["recommendations"])

        # La cabecera de llamada interna no sirve desde fuera: Nginx la borra.
        spoofed = client.get(INSIGHTS, headers={"X-Finty-Caller": "recommendation-service"})
        assert spoofed.status == 403

        # Checkout con el mock: aprueba y activa (INV-05).
        checkout = client.post(CHECKOUT, {"plan": "PREMIUM"})
        assert checkout.status == 201, checkout.text
        assert checkout.json["payment"]["status"] == "APPROVED"
        assert (checkout.json["payment"]["amount_in_cents"], checkout.json["payment"]["currency"]) == (2990000, "COP")
        active = checkout.json["subscription"]
        assert (active["plan"], active["status"], active["premium"]) == ("PREMIUM", "ACTIVE", True)

        # Ahora premium: el "no" no se cachea, asi que el acceso es inmediato.
        for path in (INSIGHTS, PATTERNS, f"{DASHBOARD}?period={period(-3)}", INVESTMENT_PLANS):
            assert client.get(path).status == 200, path
        assert client.get(RECOMMENDATIONS).json["locked"] == []

        # Un segundo checkout no crea otra suscripcion.
        again = client.post(CHECKOUT, {"plan": "PREMIUM"})
        assert (again.status, error_code(again)) == (409, "subscription_already_active")
        assert client.get(ME).json["last_payment"]["id"] == checkout.json["payment"]["id"]

        # Cancelar: sigue con acceso hasta el fin del periodo.
        canceled = client.post(CANCEL)
        assert canceled.status == 200
        body = canceled.json
        assert (body["status"], body["premium"], body["plan"]) == ("CANCELED", True, "PREMIUM")
        assert body["current_period_end"] == active["current_period_end"]
        assert client.get(INSIGHTS).status == 200
        assert client.post(CHECKOUT, {"plan": "PREMIUM"}).status == 409


@pytest.mark.skipif(not subscription_down, reason=f"activar con {SUBSCRIPTION_DOWN_ENV}=1 y subscription-service detenido")
class TestSubscriptionCaido:
    """Fail-closed: lo premium se niega con su propio code; lo gratuito sigue."""

    def test_lo_premium_se_niega(self, lucia):
        for path in (INSIGHTS, PATTERNS, f"{DASHBOARD}?period={period(-6)}", INVESTMENT_PLANS):
            response = lucia.client.get(path)
            assert (response.status, error_code(response)) == (503, "entitlements_unavailable"), path

    def test_lo_gratuito_sigue(self, lucia):
        assert lucia.client.get(f"{DASHBOARD}?period={period(0)}").status == 200
        assert lucia.client.put(RISK, MODERATE).status == 200
        body = lucia.client.get(RECOMMENDATIONS).json
        assert body["locked"] == [{"kind": "investment", "code": "entitlements_unavailable"}]
        assert lucia.client.get("/api/v1/accounts/").status == 200
