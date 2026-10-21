"""Contrato HTTP de recommendation-service (ARCHITECTURE.md §10.8)."""
import os
from uuid import uuid4

import pytest

from tests.doubles import negative, nets, recurring, spike

RISK = "/api/v1/recommendations/risk-profile/"
RECOMMENDATIONS = "/api/v1/recommendations/"
PLANS = "/api/v1/investment-plans/"
RATES = "/api/v1/exchange-rates/"

CONSERVATIVE = {"investment_horizon": 1, "loss_reaction": 1, "experience": 1, "income_stability": 1, "goal": 1}
MODERATE = {"investment_horizon": 2, "loss_reaction": 2, "experience": 2, "income_stability": 2, "goal": 2}
AGGRESSIVE = {"investment_horizon": 3, "loss_reaction": 3, "experience": 3, "income_stability": 3, "goal": 3}
DISCLAIMER_CODE = "investment_disclaimer"


def codes(body):
    return [r["code"] for r in body["recommendations"]]


def test_la_zona_horaria_del_proceso_es_la_de_time_zone(app):
    assert os.environ["TZ"] == app.config["TIME_ZONE"] == "America/Bogota"


class TestAutenticacion:
    @pytest.mark.parametrize("method, url", [
        ("get", RISK), ("put", RISK), ("get", RECOMMENDATIONS), ("get", PLANS), ("post", PLANS),
        ("get", f"{PLANS}{uuid4()}/"), ("delete", f"{PLANS}{uuid4()}/"), ("get", f"{RATES}?base=USD&target=COP"),
    ])
    def test_sin_identidad_401(self, anonimo, method, url):
        response = getattr(anonimo, method)(url)
        assert response.status_code == 401
        assert response.json == {"detail": "Las credenciales de autenticación no se proveyeron."}

    def test_metodo_no_permitido(self, ana):
        response = ana.post(RISK, CONSERVATIVE)
        assert response.status_code == 405
        assert response.json == {"detail": 'Método "POST" no permitido.'}


class TestPerfilDeRiesgo:
    def test_sin_responder_404(self, ana):
        response = ana.get(RISK)
        assert response.status_code == 404
        assert response.json["error"]["code"] == "risk_profile_not_found"

    @pytest.mark.parametrize("answers, expected", [
        (CONSERVATIVE, "conservative"), (MODERATE, "moderate"), (AGGRESSIVE, "aggressive"),
    ])
    def test_guardar_y_leer(self, ana, answers, expected):
        saved = ana.put(RISK, answers)
        assert saved.status_code == 200
        assert (saved.json["risk_profile_type"], saved.json["score"]) == (expected, sum(answers.values()))
        assert ana.get(RISK).json["answers"] == answers

    def test_responder_otra_vez_reemplaza(self, ana):
        ana.put(RISK, CONSERVATIVE)
        ana.put(RISK, AGGRESSIVE)
        assert ana.get(RISK).json["risk_profile_type"] == "aggressive"

    def test_validacion_sintactica_400(self, ana):
        response = ana.put(RISK, {"investment_horizon": "x", "loss_reaction": 2.5, "experience": None})
        assert response.status_code == 400
        assert response.json == {
            "investment_horizon": ["Introduzca un número entero válido."],
            "loss_reaction": ["Introduzca un número entero válido."],
            "experience": ["Este campo no puede ser nulo."],
            "income_stability": ["Este campo es requerido."],
            "goal": ["Este campo es requerido."],
        }

    def test_rango_es_del_dominio_422(self, ana):
        response = ana.put(RISK, dict(CONSERVATIVE, goal=4))
        assert response.status_code == 422
        assert response.json["error"]["code"] == "invalid_risk_answer"

    def test_cada_usuario_el_suyo(self, ana, juan):
        ana.put(RISK, AGGRESSIVE)
        assert juan.get(RISK).status_code == 404


class TestRecomendaciones:
    def test_optimizacion_desde_analytics(self, ana, adapters):
        analytics = adapters["analytics"]
        analytics.spikes, analytics.negative_savings, analytics.recurring = (spike(),), (negative(),), (recurring(),)
        body = ana.get(RECOMMENDATIONS).json

        assert (body["period"], body["degraded"], body["risk_profile_type"]) == ("2026-10", False, None)
        assert codes(body) == ["build_budget", "reduce_category", "review_recurring_expense"]
        reduce = body["recommendations"][1]
        assert reduce["source"] == "insight" and reduce["kind"] == "optimization"
        assert reduce["evidence"] == {"current": "200000.00", "previous_average": "100000.00", "potential_saving": "100000.00"}
        assert reduce["disclaimer"] is None and reduce["display"] is None
        assert analytics.calls[0][0] == ana.user_id

    @pytest.mark.parametrize("answers, instruments", [
        (CONSERVATIVE, ["cdt", "liquidity_fund"]),
        (MODERATE, ["collective_investment_fund"]),
        (AGGRESSIVE, ["etf", "stocks"]),
    ])
    def test_cada_perfil_su_instrumento(self, ana, adapters, answers, instruments):
        adapters["analytics"].monthly_nets = nets({"2026-07": "100000", "2026-08": "200000", "2026-09": "300000"})
        ana.put(RISK, answers)
        [invest] = ana.get(RECOMMENDATIONS).json["recommendations"]

        assert (invest["code"], invest["source"]) == ("invest_by_risk_profile", "risk_profile")
        assert invest["params"]["instrument_types"] == instruments
        assert invest["params"]["monthly_surplus"] == "200000.00"
        assert invest["evidence"]["surplus_months"] == [
            {"period": "2026-07", "net": "100000.00"},
            {"period": "2026-08", "net": "200000.00"},
            {"period": "2026-09", "net": "300000.00"},
        ]
        assert invest["disclaimer"]["code"] == DISCLAIMER_CODE

    def test_excedente_negativo_solo_fondo_de_emergencia(self, ana, adapters):
        adapters["analytics"].monthly_nets = nets({"2026-09": "-90000"})
        ana.put(RISK, AGGRESSIVE)
        body = ana.get(RECOMMENDATIONS).json
        assert codes(body) == ["build_emergency_fund"]
        assert body["recommendations"][0]["params"] == {"currency": "COP", "monthly_surplus": "-30000.00"}
        assert body["recommendations"][0]["disclaimer"]["code"] == DISCLAIMER_CODE

    def test_analytics_caido_degrada_sin_500(self, ana, adapters):
        adapters["analytics"].down = True
        adapters["analytics"].spikes = (spike(),)
        ana.put(RISK, MODERATE)
        response = ana.get(RECOMMENDATIONS)

        assert response.status_code == 200
        assert response.json["degraded"] is True
        [invest] = response.json["recommendations"]
        assert invest["code"] == "invest_by_risk_profile"
        assert invest["params"]["monthly_surplus"] is None and invest["evidence"] == {}

    def test_analytics_caido_y_sin_perfil(self, ana, adapters):
        adapters["analytics"].down = True
        body = ana.get(RECOMMENDATIONS).json
        assert (body["degraded"], body["recommendations"]) == (True, [])

    def test_presentacion_en_otra_moneda(self, ana, adapters):
        adapters["analytics"].monthly_nets = nets({"2026-09": "9491280"})  # promedio 3 163 760
        ana.put(RISK, MODERATE)
        body = ana.get(f"{RECOMMENDATIONS}?display_currency=usd").json

        assert body["display_currency"] == "USD"
        [rate] = body["exchange_rates"]
        assert (rate["base"], rate["target"], rate["source"]) == ("COP", "USD", "live")
        invest = body["recommendations"][0]
        assert invest["display"] == {"currency": "USD", "amounts": {"monthly_surplus": "1000.00"}}
        assert invest["params"]["monthly_surplus"] == "3163760.00"  # el original no cambia (INV-11)

    def test_presentacion_en_la_misma_moneda_no_consulta_tasas(self, ana, adapters):
        adapters["analytics"].monthly_nets = nets({"2026-09": "300"})
        ana.put(RISK, MODERATE)
        body = ana.get(f"{RECOMMENDATIONS}?display_currency=COP").json
        assert body["exchange_rates"] == [] and adapters["provider"].calls == 0

    def test_moneda_no_soportada_422(self, ana):
        response = ana.get(f"{RECOMMENDATIONS}?display_currency=EUR")
        assert response.status_code == 422
        assert response.json["error"]["code"] == "unsupported_currency_pair"

    def test_moneda_mal_formada_400(self, ana):
        assert ana.get(f"{RECOMMENDATIONS}?display_currency=EURO").json == {
            "display_currency": ["Asegúrese de que este campo no tenga más de 3 caracteres."],
        }


class TestPlanes:
    PLAN = {"instrument_type": "collective_investment_fund", "monthly_contribution": "100000", "horizon_months": 12}

    def test_sin_perfil_409(self, ana):
        response = ana.post(PLANS, self.PLAN)
        assert response.status_code == 409
        assert response.json["error"]["code"] == "risk_profile_required"

    def test_crear_con_proyeccion_ilustrativa(self, ana):
        ana.put(RISK, MODERATE)
        response = ana.post(PLANS, self.PLAN)

        assert response.status_code == 201
        body = response.json
        assert (body["instrument_type"], body["risk_profile_type"], body["currency"]) == ("collective_investment_fund", "moderate", "COP")
        projection = body["projection"]
        assert projection["rate_is_illustrative"] is True and projection["annual_rate"] == "0.10"
        assert projection["total_contributed"] == "1200000.00"
        assert projection["projected_value"] == "1256556.81"  # 100 000 x ((1 + 0.10/12)^12 - 1) / (0.10/12)
        assert body["disclaimer"]["code"] == DISCLAIMER_CODE

    def test_instrumento_de_otro_perfil_422(self, ana):
        ana.put(RISK, CONSERVATIVE)
        response = ana.post(PLANS, dict(self.PLAN, instrument_type="stocks"))
        assert response.status_code == 422
        assert response.json["error"]["code"] == "instrument_not_recommended"

    def test_validacion_400(self, ana):
        ana.put(RISK, MODERATE)
        response = ana.post(PLANS, {"instrument_type": "bitcoin", "monthly_contribution": "x"})
        assert response.status_code == 400
        assert set(response.json) == {"instrument_type", "monthly_contribution", "horizon_months"}

    @pytest.mark.parametrize("change, code", [
        ({"monthly_contribution": "0"}, "invalid_monthly_contribution"),
        ({"horizon_months": 0}, "invalid_horizon"),
        ({"horizon_months": 601}, "invalid_horizon"),
    ])
    def test_reglas_del_dominio_422(self, ana, change, code):
        ana.put(RISK, MODERATE)
        response = ana.post(PLANS, dict(self.PLAN, **change))
        assert (response.status_code, response.json["error"]["code"]) == (422, code)

    def test_listar_leer_y_eliminar(self, ana):
        ana.put(RISK, MODERATE)
        plan_id = ana.post(PLANS, self.PLAN).json["id"]

        listing = ana.get(PLANS).json
        assert listing["count"] == 1 and listing["results"][0]["id"] == plan_id
        assert ana.get(f"{PLANS}{plan_id}/").status_code == 200
        assert ana.delete(f"{PLANS}{plan_id}/").status_code == 204
        assert ana.get(f"{PLANS}{plan_id}/").status_code == 404

    def test_plan_ajeno_404(self, ana, juan):
        ana.put(RISK, MODERATE)
        plan_id = ana.post(PLANS, self.PLAN).json["id"]
        for response in (juan.get(f"{PLANS}{plan_id}/"), juan.delete(f"{PLANS}{plan_id}/")):
            assert (response.status_code, response.json["error"]["code"]) == (404, "investment_plan_not_found")
        assert juan.get(PLANS).json == {"count": 0, "results": []}

    def test_id_mal_formado_404(self, ana):
        assert ana.get(f"{PLANS}no-es-uuid/").json == {"detail": "No encontrado."}

    def test_el_plan_conserva_su_perfil(self, ana):
        ana.put(RISK, MODERATE)
        plan_id = ana.post(PLANS, self.PLAN).json["id"]
        ana.put(RISK, CONSERVATIVE)
        assert ana.get(f"{PLANS}{plan_id}/").json["risk_profile_type"] == "moderate"


class TestTasas:
    def test_live(self, ana):
        body = ana.get(f"{RATES}?base=USD&target=COP").json
        assert body == {
            "base": "USD", "target": "COP", "rate": "3163.76", "source": "live",
            "valid_from": "2026-10-21", "valid_until": "2026-10-21", "fetched_on": "2026-10-21",
        }

    def test_cached_y_fallback(self, ana, adapters):
        ana.get(f"{RATES}?base=USD&target=COP")
        adapters["provider"].down = True
        assert ana.get(f"{RATES}?base=USD&target=COP").json["source"] == "cached"
        adapters["cache"].days.clear()
        assert ana.get(f"{RATES}?base=USD&target=COP").json["source"] == "cached"
        adapters["cache"].last = None
        assert ana.get(f"{RATES}?base=USD&target=COP").json["source"] == "fallback"

    def test_inversa(self, ana):
        body = ana.get(f"{RATES}?base=COP&target=USD").json
        assert (body["rate"], body["source"]) == ("0.0003160796", "live")

    def test_faltan_parametros_400(self, ana):
        assert ana.get(RATES).json == {"base": ["Este campo es requerido."], "target": ["Este campo es requerido."]}

    def test_par_no_soportado_422(self, ana):
        response = ana.get(f"{RATES}?base=EUR&target=COP")
        assert (response.status_code, response.json["error"]["code"]) == (422, "unsupported_currency_pair")
