"""Planes, maquina de estados de Subscription y Payment, INV-05 y Entitlement.

Sin base de datos.
"""
from datetime import datetime, timedelta, timezone

import pytest

from domain.exceptions import InvalidTransitionError
from domain.plans import plan_catalog
from domain.subscription import Entitlement, Payment, Subscription, add_months
from domain.value_objects import Benefit, PaymentStatus, PlanCode, SubscriptionStatus

NOW = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)


def approved():
    payment = Payment(2_990_000, "COP", "ref")
    payment.resolve(PaymentStatus.APPROVED)
    return payment


def active(now=NOW):
    subscription = Subscription(PlanCode.PREMIUM)
    subscription.activate(approved(), now, 1)
    return subscription


class TestPlanes:
    def test_precio_y_beneficios(self):
        plans = plan_catalog()
        free, premium = plans[PlanCode.FREE], plans[PlanCode.PREMIUM]
        assert (free.price_in_cents, premium.price_in_cents, premium.currency) == (0, 2_990_000, "COP")
        assert free.benefits == (Benefit.TRANSACTION_TRACKING, Benefit.STANDARD_DASHBOARD, Benefit.HISTORY_3_MONTHS)
        assert {Benefit.INSIGHTS, Benefit.SPENDING_PATTERNS, Benefit.UNLIMITED_HISTORY,
                Benefit.INVESTMENT_RECOMMENDATIONS, Benefit.INVESTMENT_PLANS} <= set(premium.benefits)
        assert (free.history_months, premium.history_months) == (3, None)

    def test_precio_configurable(self):
        assert plan_catalog(1_000_000)[PlanCode.PREMIUM].price_in_cents == 1_000_000

    def test_solo_premium_se_paga(self):
        plans = plan_catalog()
        assert (plans[PlanCode.FREE].is_paid, plans[PlanCode.PREMIUM].is_paid) == (False, True)


class TestPeriodo:
    @pytest.mark.parametrize("start, end", [
        (datetime(2026, 10, 21), datetime(2026, 11, 21)),
        (datetime(2026, 1, 31), datetime(2026, 2, 28)),
        (datetime(2026, 12, 15), datetime(2027, 1, 15)),
    ])
    def test_un_mes_calendario(self, start, end):
        assert add_months(start, 1) == end


class TestPago:
    @pytest.mark.parametrize("outcome", [PaymentStatus.APPROVED, PaymentStatus.DECLINED, PaymentStatus.ERROR])
    def test_pendiente_a_final(self, outcome):
        payment = Payment(1, "COP", "r")
        assert payment.resolve(outcome) is True and payment.status is outcome

    def test_un_pago_resuelto_no_cambia(self):
        payment = approved()
        assert payment.resolve(PaymentStatus.DECLINED) is False
        assert payment.status is PaymentStatus.APPROVED

    def test_pending_no_resuelve(self):
        assert Payment(1, "COP", "r").resolve(PaymentStatus.PENDING) is False


class TestInv05:
    def test_solo_activa_con_pago_aprobado(self):
        subscription = Subscription(PlanCode.PREMIUM)
        with pytest.raises(InvalidTransitionError):
            subscription.activate(Payment(1, "COP", "r"), NOW, 1)
        assert subscription.status is SubscriptionStatus.PENDING_PAYMENT

    def test_activa_un_mes(self):
        subscription = active()
        assert subscription.status is SubscriptionStatus.ACTIVE
        assert (subscription.current_period_start, subscription.current_period_end) == (NOW, add_months(NOW, 1))

    def test_confirmar_dos_veces_no_extiende(self):
        subscription = active()
        end = subscription.current_period_end
        assert subscription.activate(approved(), NOW + timedelta(days=5), 1) is False
        assert subscription.current_period_end == end


class TestCancelarYExpirar:
    def test_cancelada_sigue_dando_acceso_hasta_el_fin(self):
        subscription = active()
        subscription.cancel(NOW + timedelta(days=1))
        assert subscription.status is SubscriptionStatus.CANCELED
        assert subscription.grants_premium(subscription.current_period_end - timedelta(seconds=1))
        assert not subscription.grants_premium(subscription.current_period_end)

    def test_cancelar_dos_veces_es_idempotente(self):
        subscription = active()
        assert subscription.cancel(NOW) is True and subscription.cancel(NOW) is False

    def test_no_se_cancela_una_pendiente(self):
        with pytest.raises(InvalidTransitionError):
            Subscription(PlanCode.PREMIUM).cancel(NOW)

    def test_expira_al_terminar_el_periodo(self):
        subscription = active()
        assert subscription.effective_status(subscription.current_period_end) is SubscriptionStatus.EXPIRED
        with pytest.raises(InvalidTransitionError):
            subscription.cancel(subscription.current_period_end)


class TestEntitlement:
    def test_premium_hasta_el_fin(self):
        subscription = active()
        assert Entitlement.of(subscription, NOW) == Entitlement(True, subscription.current_period_end)

    def test_sin_suscripcion_o_pendiente_o_vencida(self):
        assert Entitlement.of(None, NOW) == Entitlement(False, None)
        assert Entitlement.of(Subscription(PlanCode.PREMIUM), NOW).premium is False
        subscription = active()
        assert Entitlement.of(subscription, subscription.current_period_end).premium is False
