"""Contrato HTTP de subscription-service (§10.9), INV-05 e idempotencia."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from domain.interfaces import PaymentOutcome
from domain.value_objects import PaymentStatus
from models import PaymentRecord, SubscriptionRecord
from services import SubscriptionService

PLANS = "/api/v1/subscriptions/plans/"
ME = "/api/v1/subscriptions/me/"
CHECKOUT = "/api/v1/subscriptions/checkout/"
CANCEL = "/api/v1/subscriptions/me/cancel/"


def entitlements(user):
    return f"/internal/entitlements/{user.user_id}"


def count(session, model, **filters):
    query = select(func.count()).select_from(model)
    for name, value in filters.items():
        query = query.where(getattr(model, name) == value)
    return session.execute(query).scalar_one()


def test_la_zona_horaria_del_proceso_es_la_de_time_zone(app):
    assert os.environ["TZ"] == app.config["TIME_ZONE"] == "America/Bogota"


class TestAutenticacion:
    @pytest.mark.parametrize("method, url", [("get", PLANS), ("get", ME), ("post", CHECKOUT), ("post", CANCEL)])
    def test_sin_identidad_401(self, anonimo, method, url):
        response = getattr(anonimo, method)(url)
        assert response.status_code == 401
        assert response.json == {"detail": "Las credenciales de autenticación no se proveyeron."}

    def test_el_endpoint_interno_no_pide_identidad(self, anonimo):
        assert anonimo.get(f"/internal/entitlements/{uuid4()}").json == {"premium": False, "until": None}


class TestPlanes:
    def test_catalogo(self, ana):
        free, premium = ana.get(PLANS).json["results"]
        assert (free["code"], free["price"], free["history_months"]) == ("FREE", "0.00", 3)
        assert (premium["code"], premium["price"], premium["price_in_cents"], premium["currency"]) == (
            "PREMIUM", "29900.00", 2990000, "COP",
        )
        assert free["benefits"] == ["transaction_tracking", "standard_dashboard", "history_3_months", "optimization_recommendations"]
        assert premium["benefits"] == [
            "transaction_tracking", "standard_dashboard", "optimization_recommendations", "insights", "spending_patterns",
            "unlimited_history", "investment_recommendations", "investment_plans",
        ]


class TestCheckout:
    def test_sin_suscripcion_es_free(self, ana):
        body = ana.get(ME).json
        assert (body["plan"], body["premium"], body["status"], body["current_period_end"]) == ("FREE", False, None, None)
        assert body["benefits"] == ["transaction_tracking", "standard_dashboard", "history_3_months", "optimization_recommendations"]

    def test_aprobado_activa_un_mes(self, ana, adapters):
        response = ana.post(CHECKOUT, {"plan": "PREMIUM"})
        assert response.status_code == 201
        body = response.json
        assert body["payment"]["status"] == "APPROVED"
        assert (body["payment"]["amount_in_cents"], body["payment"]["currency"]) == (2990000, "COP")
        assert body["payment"]["reference"].startswith("finty-")
        sub = body["subscription"]
        assert (sub["plan"], sub["status"], sub["premium"]) == ("PREMIUM", "ACTIVE", True)
        assert sub["current_period_end"] == "2026-11-21T10:00:00-05:00"
        assert adapters["gateway"].requests[0].amount_in_cents == 2990000

    @pytest.mark.parametrize("outcome", [PaymentStatus.DECLINED, PaymentStatus.ERROR])
    def test_rechazado_no_activa_inv_05(self, ana, adapters, outcome):
        adapters["gateway"].outcome = outcome
        body = ana.post(CHECKOUT, {"plan": "PREMIUM"}).json
        assert body["payment"]["status"] == outcome.value
        assert (body["subscription"]["status"], body["subscription"]["premium"]) == ("PENDING_PAYMENT", False)
        assert ana.get(entitlements(ana)).json["premium"] is False

    def test_una_pasarela_que_lanza_deja_el_pago_en_error(self, ana, adapters):
        adapters["gateway"].error = TimeoutError("sin respuesta")
        assert ana.post(CHECKOUT, {"plan": "PREMIUM"}).json["payment"]["status"] == "ERROR"

    def test_tras_un_rechazo_se_reintenta_sobre_la_misma_suscripcion(self, ana, adapters, session):
        adapters["gateway"].outcome = PaymentStatus.DECLINED
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        adapters["gateway"].outcome = PaymentStatus.APPROVED
        assert ana.post(CHECKOUT, {"plan": "PREMIUM"}).json["subscription"]["status"] == "ACTIVE"
        assert count(session, SubscriptionRecord, user_id=ana.user_id) == 1
        assert count(session, PaymentRecord, user_id=ana.user_id) == 2

    def test_segundo_checkout_con_una_activa_no_crea_otra(self, ana, session):
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        response = ana.post(CHECKOUT, {"plan": "PREMIUM"})
        assert (response.status_code, response.json["error"]["code"]) == (409, "subscription_already_active")
        assert count(session, SubscriptionRecord, user_id=ana.user_id) == 1
        assert count(session, PaymentRecord, user_id=ana.user_id) == 1

    def test_free_no_se_compra(self, ana):
        response = ana.post(CHECKOUT, {"plan": "FREE"})
        assert (response.status_code, response.json["error"]["code"]) == (422, "plan_not_purchasable")

    def test_validacion_400(self, ana):
        assert ana.post(CHECKOUT, {"plan": "GOLD"}).json == {"plan": ['"GOLD" no es una elección válida.']}
        assert ana.post(CHECKOUT, {}).json == {"plan": ["Este campo es requerido."]}

    def test_cada_usuario_la_suya(self, ana, juan):
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        assert juan.get(ME).json["plan"] == "FREE"


class TestIdempotencia:
    def test_confirmar_dos_veces_el_mismo_pago_no_extiende_el_periodo(self, ana, app, session, adapters):
        payment_id = ana.post(CHECKOUT, {"plan": "PREMIUM"}).json["payment"]["id"]
        end = ana.get(ME).json["current_period_end"]
        adapters["clock"].advance(days=10)
        with app.app_context():
            service = SubscriptionService(session, adapters["gateway"], app.config["SUBSCRIPTION_PLANS"], adapters["clock"])
            service.confirm_payment(payment_id, PaymentOutcome(PaymentStatus.APPROVED))
            service.confirm_payment(payment_id, PaymentOutcome(PaymentStatus.DECLINED))
        body = ana.get(ME).json
        assert (body["current_period_end"], body["last_payment"]["status"]) == (end, "APPROVED")

    def test_el_constraint_impide_dos_vigentes(self, session):
        from sqlalchemy.exc import IntegrityError

        user = uuid4()
        session.add(SubscriptionRecord(user_id=user, plan="PREMIUM", status="PENDING_PAYMENT"))
        session.flush()
        session.add(SubscriptionRecord(user_id=user, plan="PREMIUM", status="PENDING_PAYMENT"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


class TestCancelarYExpirar:
    def test_cancelar_mantiene_el_acceso_hasta_el_fin(self, ana, adapters):
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        body = ana.post(CANCEL).json
        assert (body["status"], body["premium"], body["plan"]) == ("CANCELED", True, "PREMIUM")
        assert ana.get(entitlements(ana)).json == {"premium": True, "until": "2026-11-21T10:00:00-05:00"}

        adapters["clock"].advance(days=31)
        body = ana.get(ME).json
        assert (body["status"], body["premium"], body["plan"]) == ("EXPIRED", False, "FREE")
        assert ana.get(entitlements(ana)).json == {"premium": False, "until": None}

    def test_cancelar_dos_veces(self, ana):
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        ana.post(CANCEL)
        assert ana.post(CANCEL).status_code == 200

    def test_sin_suscripcion_activa_409(self, ana):
        response = ana.post(CANCEL)
        assert (response.status_code, response.json["error"]["code"]) == (409, "no_active_subscription")

    def test_renovar_es_un_pago_nuevo_tras_el_vencimiento(self, ana, adapters, session):
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        assert ana.post(CHECKOUT, {"plan": "PREMIUM"}).status_code == 409
        adapters["clock"].advance(days=31)
        body = ana.post(CHECKOUT, {"plan": "PREMIUM"}).json
        assert body["subscription"]["status"] == "ACTIVE"
        assert count(session, SubscriptionRecord, user_id=ana.user_id, status="EXPIRED") == 1
        assert count(session, PaymentRecord, user_id=ana.user_id) == 2


class TestFactory:
    def test_mock_por_defecto_e_insensible_a_mayusculas(self):
        from infra.factories import PaymentGatewayFactory
        from infra.gateways import MockPaymentGateway

        assert isinstance(PaymentGatewayFactory.get_gateway({}), MockPaymentGateway)
        assert isinstance(PaymentGatewayFactory.get_gateway({"PAYMENT_GATEWAY": " mock "}), MockPaymentGateway)

    def test_valor_desconocido_impide_arrancar(self, monkeypatch, connection):
        from app import create_app
        from infra.configuration import ConfigurationError

        monkeypatch.setenv("PAYMENT_GATEWAY", "OTRA")
        with pytest.raises(ConfigurationError, match="Valores validos: MOCK"):
            create_app(session_factory=lambda: None)

    def test_el_mock_aprueba_de_forma_determinista(self):
        from domain.interfaces import PaymentRequest
        from infra.gateways import MockPaymentGateway

        outcome = MockPaymentGateway().submit(PaymentRequest("r", 1, "COP", uuid4()))
        assert outcome.status is PaymentStatus.APPROVED
