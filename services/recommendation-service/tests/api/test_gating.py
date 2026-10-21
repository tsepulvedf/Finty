"""INV-06 en recommendation-service: planes premium, inversion bloqueada para FREE."""
from uuid import uuid4

import pytest

from tests.doubles import nets, spike

RISK = "/api/v1/recommendations/risk-profile/"
RECOMMENDATIONS = "/api/v1/recommendations/"
PLANS = "/api/v1/investment-plans/"
RATES = "/api/v1/exchange-rates/?base=USD&target=COP"
MODERATE = {"investment_horizon": 2, "loss_reaction": 2, "experience": 2, "income_stability": 2, "goal": 2}


@pytest.fixture
def with_data(ana, adapters):
    adapters["analytics"].spikes = (spike(),)
    adapters["analytics"].monthly_nets = nets({"2026-09": "300000"})
    ana.put(RISK, MODERATE)
    return ana


class TestFree:
    @pytest.fixture(autouse=True)
    def free(self, adapters):
        adapters["entitlements"].premium = False

    @pytest.mark.parametrize("method, url", [
        ("get", PLANS), ("post", PLANS), ("get", f"{PLANS}{uuid4()}/"), ("delete", f"{PLANS}{uuid4()}/"),
    ])
    def test_planes_403(self, ana, method, url):
        response = getattr(ana, method)(url)
        assert response.status_code == 403
        assert response.json["error"]["code"] == "premium_required"

    def test_solo_optimizacion_y_la_inversion_bloqueada(self, with_data):
        body = with_data.get(RECOMMENDATIONS).json
        assert [r["kind"] for r in body["recommendations"]] == ["optimization"]
        assert body["locked"] == [{"kind": "investment", "code": "premium_required"}]
        assert body["degraded"] is False

    def test_perfil_y_tasas_son_gratuitos(self, ana):
        assert ana.put(RISK, MODERATE).status_code == 200
        assert ana.get(RISK).status_code == 200
        assert ana.get(RATES).status_code == 200


class TestPremium:
    def test_todo(self, with_data):
        body = with_data.get(RECOMMENDATIONS).json
        assert [r["kind"] for r in body["recommendations"]] == ["optimization", "investment"]
        assert body["locked"] == []
        assert with_data.get(PLANS).status_code == 200


class TestSubscriptionCaido:
    @pytest.fixture(autouse=True)
    def down(self, adapters):
        adapters["entitlements"].down = True

    def test_planes_503(self, ana):
        response = ana.get(PLANS)
        assert (response.status_code, response.json["error"]["code"]) == (503, "entitlements_unavailable")

    def test_recomendaciones_sin_inversion_pero_responden(self, with_data):
        response = with_data.get(RECOMMENDATIONS)
        assert response.status_code == 200
        assert [r["kind"] for r in response.json["recommendations"]] == ["optimization"]
        assert response.json["locked"] == [{"kind": "investment", "code": "entitlements_unavailable"}]

    def test_lo_gratuito_sigue(self, ana):
        assert ana.put(RISK, MODERATE).status_code == 200
        assert ana.get(RATES).status_code == 200
