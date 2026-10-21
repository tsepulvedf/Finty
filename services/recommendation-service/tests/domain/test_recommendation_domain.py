"""Reglas del dominio: RiskProfile, Recommendation, InvestmentPlan y ExchangeRate.

Sin base de datos ni red. Cada regla con los numeros exactos que la justifican.
"""
from dataclasses import FrozenInstanceError
from datetime import datetime
from decimal import Decimal

import pytest

from domain.analytics import AnalyticsSnapshot
from domain.exceptions import (
    InstrumentNotRecommendedError,
    InvalidHorizonError,
    InvalidMonthlyContributionError,
    InvalidRiskAnswerError,
    UnsupportedCurrencyPairError,
)
from domain.exchange import ExchangeRate, ensure_supported_currency, ensure_supported_pair, seconds_until_next_day
from domain.investment_plan import build_plan, project
from domain.period import Period
from domain.recommendations import (
    investment_recommendations,
    monthly_surpluses,
    optimization_recommendations,
)
from domain.risk_profile import QUESTIONS, RiskProfile
from domain.shared.value_objects import Money
from domain.value_objects import (
    ExchangeRateSource,
    InstrumentType,
    RecommendationKind,
    RecommendationSource,
    RiskProfileType,
)
from tests.doubles import negative, nets, recurring, spike

OCT = Period(2026, 10)


def answers(*values):
    return dict(zip(QUESTIONS, values))


def params(r):
    return dict(r.params)


def evidence(r):
    return dict(r.evidence)


class TestRiskProfile:
    @pytest.mark.parametrize("values, expected", [
        ((1, 1, 1, 1, 1), RiskProfileType.CONSERVATIVE),   # 5
        ((2, 2, 2, 1, 1), RiskProfileType.CONSERVATIVE),   # 8
        ((2, 2, 2, 2, 1), RiskProfileType.MODERATE),       # 9
        ((3, 2, 2, 2, 2), RiskProfileType.MODERATE),       # 11
        ((3, 3, 2, 2, 2), RiskProfileType.AGGRESSIVE),     # 12
        ((3, 3, 3, 3, 3), RiskProfileType.AGGRESSIVE),     # 15
    ])
    def test_rangos(self, values, expected):
        profile = RiskProfile.from_answers(answers(*values))
        assert (profile.score, profile.profile_type) == (sum(values), expected)

    @pytest.mark.parametrize("bad", [0, 4, -1, True, "2", None])
    def test_respuesta_fuera_de_rango(self, bad):
        with pytest.raises(InvalidRiskAnswerError):
            RiskProfile.from_answers(answers(bad, 1, 1, 1, 1))

    def test_falta_una_pregunta(self):
        with pytest.raises(InvalidRiskAnswerError):
            RiskProfile.from_answers({"investment_horizon": 1})

    def test_son_cinco_preguntas_en_orden(self):
        assert QUESTIONS == ("investment_horizon", "loss_reaction", "experience", "income_stability", "goal")


class TestOptimizacion:
    def snapshot(self, **kwargs):
        return AnalyticsSnapshot(OCT, **kwargs)

    def test_spike_reduce_la_categoria(self):
        [r] = optimization_recommendations(self.snapshot(spikes=(spike(),)))
        assert (r.code, r.kind, r.source) == ("reduce_category", RecommendationKind.OPTIMIZATION, RecommendationSource.INSIGHT)
        assert params(r) == {"category_name": "Alimentación", "currency": "COP", "increase_pct": Decimal("100.0")}
        assert evidence(r)["potential_saving"] == Money("100000", "COP")
        assert not r.has_disclaimer

    def test_ahorro_negativo_arma_presupuesto(self):
        [r] = optimization_recommendations(self.snapshot(negative_savings=(negative(),)))
        assert r.code == "build_budget"
        assert params(r) == {"currency": "COP", "deficit": Money("50000", "COP")}
        assert evidence(r) == {"income": Money("100000", "COP"), "expense": Money("150000", "COP")}

    def test_patron_revisa_el_gasto_fijo(self):
        [r] = optimization_recommendations(self.snapshot(recurring=(recurring(),)))
        assert (r.code, r.source) == ("review_recurring_expense", RecommendationSource.PATTERN)
        assert evidence(r)["annualized_cost"] == Money("478800", "COP")  # 39 900 x 1 x 12

    def test_orden_estable(self):
        found = optimization_recommendations(self.snapshot(
            spikes=(spike(),), negative_savings=(negative(),), recurring=(recurring(),),
        ))
        assert [r.code for r in found] == ["build_budget", "reduce_category", "review_recurring_expense"]


class TestExcedente:
    def test_promedio_de_los_tres_meses_completos_anteriores(self):
        data = nets({"2026-07": "300000", "2026-08": "600000", "2026-09": "0", "2026-10": "9999999"})
        [s] = monthly_surpluses(OCT, data, 3)
        assert s.average == Money("300000", "COP")
        assert [str(p) for p, _ in s.months] == ["2026-07", "2026-08", "2026-09"]

    def test_un_mes_sin_datos_cuenta_cero(self):
        [s] = monthly_surpluses(OCT, nets({"2026-09": "90000"}), 3)
        assert s.average == Money("30000", "COP")

    def test_por_moneda(self):
        data = nets({"2026-09": "300"}) + nets({"2026-09": "-30"}, "USD")
        assert {s.currency: s.average.amount for s in monthly_surpluses(OCT, data, 3)} == {
            "COP": Decimal("100.00"), "USD": Decimal("-10.00"),
        }

    def test_sin_datos_es_cero_en_cop(self):
        [s] = monthly_surpluses(OCT, (), 3)
        assert s.average == Money("0", "COP")


class TestInversion:
    @pytest.mark.parametrize("profile, instruments", [
        (RiskProfileType.CONSERVATIVE, (InstrumentType.CDT, InstrumentType.LIQUIDITY_FUND)),
        (RiskProfileType.MODERATE, (InstrumentType.COLLECTIVE_INVESTMENT_FUND,)),
        (RiskProfileType.AGGRESSIVE, (InstrumentType.ETF, InstrumentType.STOCKS)),
    ])
    def test_cada_perfil_su_instrumento(self, profile, instruments):
        surpluses = monthly_surpluses(OCT, nets({"2026-09": "300000"}), 3)
        [r] = investment_recommendations(profile, surpluses)
        assert (r.code, r.source) == ("invest_by_risk_profile", RecommendationSource.RISK_PROFILE)
        assert params(r)["instrument_types"] == instruments
        assert params(r)["monthly_surplus"] == Money("100000", "COP")
        assert r.has_disclaimer

    @pytest.mark.parametrize("value", ["0", "-300000"])
    def test_excedente_no_positivo_solo_fondo_de_emergencia(self, value):
        surpluses = monthly_surpluses(OCT, nets({"2026-09": value}), 3)
        found = investment_recommendations(RiskProfileType.AGGRESSIVE, surpluses)
        assert [r.code for r in found] == ["build_emergency_fund"]
        assert found[0].has_disclaimer

    def test_sin_perfil_no_hay_inversion(self):
        assert investment_recommendations(None, monthly_surpluses(OCT, (), 3)) == ()

    def test_degradado_solo_con_el_perfil(self):
        [r] = investment_recommendations(RiskProfileType.MODERATE, None)
        assert params(r)["monthly_surplus"] is None and r.evidence == ()

    def test_nunca_nombra_productos_ni_entidades(self):
        assert {i.value for i in InstrumentType} == {"cdt", "liquidity_fund", "collective_investment_fund", "etf", "stocks"}


class TestPlan:
    def test_proyeccion_con_capitalizacion_mensual(self):
        p = project(Money("100000", "COP"), 12, Decimal("0.12"))
        assert (p.total_contributed, p.projected_value, p.projected_gain) == (
            Money("1200000", "COP"), Money("1268250.30", "COP"), Money("68250.30", "COP"),
        )

    def test_tasa_cero(self):
        assert project(Money("10", "COP"), 5, Decimal("0")).projected_value == Money("50", "COP")

    def test_instrumento_de_otro_perfil(self):
        with pytest.raises(InstrumentNotRecommendedError):
            build_plan("stocks", "conservative", Money("1", "COP"), 12, 600)

    @pytest.mark.parametrize("amount", ["0", "-1"])
    def test_aporte_positivo(self, amount):
        with pytest.raises(InvalidMonthlyContributionError):
            build_plan("cdt", "conservative", Money(amount, "COP"), 12, 600)

    @pytest.mark.parametrize("months", [0, 601])
    def test_horizonte(self, months):
        with pytest.raises(InvalidHorizonError):
            build_plan("cdt", "conservative", Money("1", "COP"), months, 600)


class TestExchangeRate:
    RATE = ExchangeRate("USD", "COP", Decimal("3163.76"), ExchangeRateSource.LIVE)

    def test_convierte(self):
        assert self.RATE.convert(Money("10", "USD")) == Money("31637.60", "COP")

    def test_inversa_conserva_la_procedencia(self):
        inverse = self.RATE.inverse()
        assert (inverse.base, inverse.target, inverse.source) == ("COP", "USD", ExchangeRateSource.LIVE)
        assert inverse.convert(Money("3163.76", "COP")) == Money("1", "USD")

    def test_moneda_equivocada(self):
        with pytest.raises(UnsupportedCurrencyPairError):
            self.RATE.convert(Money("1", "EUR"))

    @pytest.mark.parametrize("pair", [("USD", "USD"), ("EUR", "COP"), ("COP", "EUR")])
    def test_solo_usd_cop(self, pair):
        with pytest.raises(UnsupportedCurrencyPairError):
            ensure_supported_pair(*pair)

    def test_moneda_de_presentacion(self):
        assert ensure_supported_currency(" usd ") == "USD"
        with pytest.raises(UnsupportedCurrencyPairError):
            ensure_supported_currency("EUR")

    def test_ttl_hasta_la_medianoche(self):
        assert seconds_until_next_day(datetime(2026, 10, 21, 23, 0)) == 3600

    def test_inmutable(self):
        with pytest.raises(FrozenInstanceError):
            self.RATE.rate = Decimal("1")
