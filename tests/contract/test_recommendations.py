"""recommendation-service por el Gateway (§10.8): perfil, recomendaciones, planes y tasas.

Las recomendaciones salen de analytics, que es **eventualmente consistente**
(ADR-15): los tests que dependen de transacciones recien registradas sondean con
un limite de tiempo.

Opcionales, con el stack preparado a mano (procedimiento en `tests/contract/runs/`):
- `CONTRACT_EXCHANGE_SOURCE=live|cached|fallback`: procedencia esperada de la tasa.
- `CONTRACT_ANALYTICS_DOWN=1`, con `docker compose stop analytics-service`: las
  recomendaciones responden 200 con `degraded: true`.
"""
import os
from datetime import date, timedelta

import pytest

from helpers import NOT_AUTHENTICATED, create_account, register
from test_analytics import wait_until

RISK = "/api/v1/recommendations/risk-profile/"
RECOMMENDATIONS = "/api/v1/recommendations/"
PLANS = "/api/v1/investment-plans/"
RATES = "/api/v1/exchange-rates/"

EXCHANGE_SOURCE_ENV = "CONTRACT_EXCHANGE_SOURCE"
ANALYTICS_DOWN_ENV = "CONTRACT_ANALYTICS_DOWN"

CONSERVATIVE = {"investment_horizon": 1, "loss_reaction": 1, "experience": 1, "income_stability": 1, "goal": 1}
MODERATE = {"investment_horizon": 2, "loss_reaction": 2, "experience": 2, "income_stability": 2, "goal": 2}
AGGRESSIVE = {"investment_horizon": 3, "loss_reaction": 3, "experience": 3, "income_stability": 3, "goal": 3}

TODAY = date.today()
# Dia 15 del mes anterior: dentro de los 3 meses completos que promedia el excedente.
PREVIOUS_MONTH = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=15).isoformat()

analytics_down = os.environ.get(ANALYTICS_DOWN_ENV) == "1"
requires_analytics = pytest.mark.skipif(analytics_down, reason=f"{ANALYTICS_DOWN_ENV}=1")


def recommendations(user):
    return user.client.get(RECOMMENDATIONS).json["recommendations"]


def by_code(user, code):
    return next((r for r in recommendations(user) if r["code"] == code), None)


@pytest.fixture(scope="module")
def ahorradora(eva):
    """Excedente positivo: un ingreso de 300 000 el mes anterior → promedio 100 000.

    Es `eva`: cada usuario nuevo cuesta dos peticiones de la zona `finty_auth`
    (rafaga de 10), asi que la suite no crea mas de cuatro.
    """
    account = create_account(eva, initial_balance="1000000")
    created = register(eva, account["id"], "300000", "income", occurred_on=PREVIOUS_MONTH, description="Pago de nomina")
    assert created.status == 201, created.text
    return eva


@pytest.fixture(scope="module")
def deficitario(mateo):
    """Excedente negativo el mes anterior y gastos sin ingresos este mes."""
    account = create_account(mateo, initial_balance="5000000")
    assert register(mateo, account["id"], "900000", occurred_on=PREVIOUS_MONTH, category_name="Compras").status == 201
    assert register(mateo, account["id"], "250000", occurred_on=TODAY.isoformat(), category_name="Compras").status == 201
    return mateo


class TestAutenticacion:
    @pytest.mark.parametrize("path", [RISK, RECOMMENDATIONS, PLANS, f"{RATES}?base=USD&target=COP", "/api/v1/investment-plans"])
    def test_sin_token_401_del_gateway(self, anonimo, path):
        response = anonimo.get(path)
        assert response.status == 401
        assert response.json == NOT_AUTHENTICATED
        assert response.header("X-Finty-Route") == "recommendation"


class TestPerfilDeRiesgo:
    def test_guardar_y_leer(self, eva):
        saved = eva.client.put(RISK, MODERATE)
        assert saved.status == 200
        assert (saved.json["risk_profile_type"], saved.json["score"]) == ("moderate", 10)
        assert eva.client.get(RISK).json["answers"] == MODERATE

    def test_rango_invalido_422(self, eva):
        response = eva.client.put(RISK, dict(MODERATE, goal=7))
        assert (response.status, response.json["error"]["code"]) == (422, "invalid_risk_answer")


@requires_analytics
class TestInversionPorPerfil:
    @pytest.mark.parametrize("answers, instruments", [
        (CONSERVATIVE, ["cdt", "liquidity_fund"]),
        (MODERATE, ["collective_investment_fund"]),
        (AGGRESSIVE, ["etf", "stocks"]),
    ])
    def test_cada_perfil_su_instrumento(self, ahorradora, answers, instruments):
        assert ahorradora.client.put(RISK, answers).status == 200

        def invest():
            found = by_code(ahorradora, "invest_by_risk_profile")
            return found if found and found["params"]["instrument_types"] == instruments else None

        found = wait_until(invest)
        assert found["params"]["monthly_surplus"] == "100000.00"
        assert found["source"] == "risk_profile"
        assert found["disclaimer"]["code"] == "investment_disclaimer"
        assert len(found["evidence"]["surplus_months"]) == 3

    def test_excedente_negativo_solo_fondo_de_emergencia(self, deficitario):
        deficitario.client.put(RISK, AGGRESSIVE)

        def emergency_only():
            # Con excedente 0 (antes de que llegue el evento) ya seria solo fondo
            # de emergencia: se espera la cifra del mes anterior ya proyectada.
            investment = [r for r in recommendations(deficitario) if r["kind"] == "investment"]
            settled = investment and investment[0]["params"]["monthly_surplus"] == "-300000.00"
            return investment if settled else None

        investment = wait_until(emergency_only)
        assert [r["code"] for r in investment] == ["build_emergency_fund"]
        assert investment[0]["params"] == {"currency": "COP", "monthly_surplus": "-300000.00"}

    def test_optimizacion_desde_los_insights(self, deficitario):
        budget = wait_until(lambda: by_code(deficitario, "build_budget"))
        assert (budget["source"], budget["kind"]) == ("insight", "optimization")
        assert budget["params"] == {"currency": "COP", "deficit": "250000.00"}
        assert budget["disclaimer"] is None

    def test_presentacion_en_dolares(self, ahorradora):
        wait_until(lambda: by_code(ahorradora, "invest_by_risk_profile"))
        body = ahorradora.client.get(f"{RECOMMENDATIONS}?display_currency=USD").json
        [rate] = body["exchange_rates"]
        assert (rate["base"], rate["target"]) == ("COP", "USD")
        assert rate["source"] in {"live", "cached", "fallback"}
        invest = next(r for r in body["recommendations"] if r["code"] == "invest_by_risk_profile")
        assert invest["display"]["currency"] == "USD"
        assert invest["params"]["monthly_surplus"] == "100000.00"  # el original no cambia


class TestDegradacion:
    @pytest.mark.skipif(not analytics_down, reason=f"activar con {ANALYTICS_DOWN_ENV}=1 y analytics-service detenido")
    def test_analytics_caido_responde_degradado(self, eva):
        eva.client.put(RISK, MODERATE)
        response = eva.client.get(RECOMMENDATIONS)
        assert response.status == 200
        assert response.json["degraded"] is True
        assert [r["code"] for r in response.json["recommendations"]] == ["invest_by_risk_profile"]
        assert response.json["recommendations"][0]["params"]["monthly_surplus"] is None


class TestPlanes:
    PLAN = {"instrument_type": "collective_investment_fund", "monthly_contribution": "100000", "horizon_months": 12}

    def test_sin_perfil_409(self, juan):
        """`juan` nunca responde el cuestionario en esta suite."""
        response = juan.client.post(PLANS, self.PLAN)
        assert (response.status, response.json["error"]["code"]) == (409, "risk_profile_required")

    def test_ciclo_completo_y_aislamiento(self, eva, juan):
        eva.client.put(RISK, MODERATE)
        created = eva.client.post(PLANS, self.PLAN)
        assert created.status == 201, created.text
        plan = created.json
        assert plan["projection"]["rate_is_illustrative"] is True
        assert plan["projection"]["projected_value"] == "1256556.81"
        assert plan["disclaimer"]["code"] == "investment_disclaimer"

        assert plan["id"] in {p["id"] for p in eva.client.get(PLANS).json["results"]}
        assert juan.client.get(f"{PLANS}{plan['id']}/").status == 404
        assert eva.client.delete(f"{PLANS}{plan['id']}/").status == 204
        assert eva.client.get(f"{PLANS}{plan['id']}/").status == 404

    def test_instrumento_de_otro_perfil_422(self, eva):
        eva.client.put(RISK, MODERATE)
        response = eva.client.post(PLANS, dict(self.PLAN, instrument_type="stocks"))
        assert (response.status, response.json["error"]["code"]) == (422, "instrument_not_recommended")


class TestTasas:
    def test_forma_y_procedencia(self, ana):
        response = ana.client.get(f"{RATES}?base=USD&target=COP")
        assert response.status == 200
        body = response.json
        assert list(body) == ["base", "target", "rate", "source", "valid_from", "valid_until", "fetched_on"]
        assert (body["base"], body["target"]) == ("USD", "COP")
        expected = os.environ.get(EXCHANGE_SOURCE_ENV)
        assert body["source"] == expected if expected else body["source"] in {"live", "cached", "fallback"}

    def test_par_no_soportado_422(self, ana):
        response = ana.client.get(f"{RATES}?base=EUR&target=COP")
        assert (response.status, response.json["error"]["code"]) == (422, "unsupported_currency_pair")
