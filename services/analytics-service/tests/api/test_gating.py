"""INV-06 en analytics-service: premium, FREE con 3 meses, y subscription-service caido."""
from datetime import date

import pytest

from domain.period import Period

INSIGHTS = "/api/v1/analytics/insights/"
PATTERNS = "/api/v1/analytics/spending-patterns/"
DASHBOARD = "/api/v1/analytics/dashboard/"
SUMMARY = "/api/v1/public/spending-summary/"

CURRENT = Period.of(date.today())


def period(offset):
    return str(CURRENT.shift(offset))


class TestFree:
    @pytest.fixture(autouse=True)
    def free(self, entitlements):
        entitlements.premium = False

    @pytest.mark.parametrize("url", [INSIGHTS, PATTERNS])
    def test_premium_403(self, ana, url):
        response = ana.get(url)
        assert response.status_code == 403
        assert response.json["error"]["code"] == "premium_required"

    @pytest.mark.parametrize("offset", [0, -1, -2])
    def test_dashboard_de_los_ultimos_3_meses(self, ana, offset):
        assert ana.get(f"{DASHBOARD}?period={period(offset)}").status_code == 200

    def test_dashboard_fuera_de_la_ventana_403(self, ana):
        response = ana.get(f"{DASHBOARD}?period={period(-3)}")
        assert response.status_code == 403
        assert response.json["error"] == {
            "code": "premium_required",
            "message": "El plan FREE incluye los últimos 3 meses de historial. "
                       "El historial completo es parte del plan PREMIUM.",
        }

    def test_periodo_invalido_sigue_siendo_400(self, ana):
        assert ana.get(f"{DASHBOARD}?period=2026-13").status_code == 400

    def test_el_resumen_publico_no_consulta_derechos(self, anonimo, entitlements):
        assert anonimo.get(SUMMARY).status_code == 200
        assert entitlements.calls == []

    def test_la_llamada_interna_no_pasa_por_el_gating(self, ana, entitlements):
        response = ana.get(INSIGHTS, headers={"X-Finty-Caller": "recommendation-service"})
        assert response.status_code == 200 and entitlements.calls == []


class TestTendencia:
    def feed(self, session, user_id):
        from services import EventProjector
        from tests.streams import Transaction, event

        on = CURRENT.start
        EventProjector(session).project(event(Transaction(user_id=user_id, on=on).added()), "1-0")

    def test_free_ve_3_meses(self, ana, entitlements, session):
        entitlements.premium = False
        self.feed(session, ana.user_id)
        [section] = ana.get(DASHBOARD).json["currencies"]
        assert [p["period"] for p in section["trend"]] == [period(-2), period(-1), period(0)]

    def test_premium_ve_6_meses(self, ana, session):
        self.feed(session, ana.user_id)
        [section] = ana.get(DASHBOARD).json["currencies"]
        assert len(section["trend"]) == 6


class TestComparacionSegunElPlan:
    """D-29: el plan Free solo compara con un periodo de su ventana de 3 meses."""

    def feed(self, session, user_id, periods):
        from services import EventProjector
        from tests.streams import Transaction, event

        projector = EventProjector(session)
        for i, period in enumerate(periods):
            on = Period.parse(period).start
            projector.project(event(Transaction(user_id=user_id, on=on, amount="1000.00").added()), f"{i}-0")

    def test_free_dentro_de_la_ventana_compara(self, ana, entitlements, session):
        entitlements.premium = False
        self.feed(session, ana.user_id, [period(-1), period(0)])
        [section] = ana.get(f"{DASHBOARD}?period={period(0)}").json["currencies"]
        assert section["previous"]["period"] == period(-1)
        assert section["expense_change_pct"] == "0.0"

    def test_free_en_el_borde_de_la_ventana_no_compara(self, ana, entitlements, session):
        entitlements.premium = False
        self.feed(session, ana.user_id, [period(-3), period(-2)])
        [section] = ana.get(f"{DASHBOARD}?period={period(-2)}").json["currencies"]
        assert section["previous"] is None and section["expense_change_pct"] is None

    def test_premium_compara_siempre(self, ana, session):
        self.feed(session, ana.user_id, [period(-3), period(-2)])
        [section] = ana.get(f"{DASHBOARD}?period={period(-2)}").json["currencies"]
        assert section["previous"]["period"] == period(-3)


class TestPremium:
    @pytest.mark.parametrize("url", [INSIGHTS, PATTERNS, f"{DASHBOARD}?period={period(-12)}"])
    def test_acceso_completo(self, ana, url):
        assert ana.get(url).status_code == 200


class TestSubscriptionCaido:
    @pytest.fixture(autouse=True)
    def down(self, entitlements):
        entitlements.down = True

    @pytest.mark.parametrize("url", [INSIGHTS, PATTERNS, f"{DASHBOARD}?period={period(-6)}"])
    def test_lo_premium_se_niega_503(self, ana, url):
        response = ana.get(url)
        assert response.status_code == 503
        assert response.json["error"]["code"] == "entitlements_unavailable"

    def test_lo_gratuito_sigue(self, ana):
        assert ana.get(DASHBOARD).status_code == 200
