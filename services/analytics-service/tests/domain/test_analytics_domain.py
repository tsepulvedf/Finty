"""Reglas del dominio de analytics: Period, Dashboard, Insight, SpendingPattern y resumen.

Sin base de datos. Cada regla se prueba con los numeros exactos que la
justifican, porque son reglas explicables (Phase 0).
"""
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.dashboard import Dashboard
from domain.exceptions import InvalidPeriodError
from domain.facts import normalize_description
from domain.insights import InsightType, Severity, detect_insights
from domain.patterns import detect_patterns
from domain.period import Period
from domain.shared.value_objects import Money
from domain.summary import SpendingSummary
from domain.thresholds import AnalyticsThresholds
from tests.domain.helpers import fact

OCT = Period(2026, 10)
T = AnalyticsThresholds()


def money(text, currency="COP"):
    return Money(text, currency)


def params(insight):
    return dict(insight.params)


def evidence(insight):
    return dict(insight.evidence)


class TestPeriod:
    def test_parse(self):
        assert Period.parse("2026-10") == OCT
        assert str(OCT) == "2026-10"

    @pytest.mark.parametrize("text", ["2026-13", "2026-1", "26-10", "2026/10", "", None, "2026-00"])
    def test_parse_invalido(self, text):
        with pytest.raises(InvalidPeriodError):
            Period.parse(text)

    def test_shift_cruza_anios(self):
        assert Period(2026, 1).shift(-1) == Period(2025, 12)
        assert Period(2025, 12).shift(1) == Period(2026, 1)

    def test_previous_y_window(self):
        assert Period(2026, 2).previous(3) == (Period(2025, 11), Period(2025, 12), Period(2026, 1))
        assert OCT.window(2) == (Period(2026, 9), OCT)

    def test_limites(self):
        assert (OCT.start, OCT.end) == (date(2026, 10, 1), date(2026, 11, 1))

    def test_inmutable(self):
        with pytest.raises(FrozenInstanceError):
            OCT.month = 11


class TestDashboard:
    def test_totales_neto_y_desglose(self):
        facts = [
            fact("500000", "income", "Salario"),
            fact("120000", "expense", "Alimentación"),
            fact("30000", "expense", "Transporte"),
            fact("50000", "expense", "Alimentación"),
        ]
        [cop] = Dashboard.build(OCT, facts).currencies

        assert (cop.totals.income, cop.totals.expense, cop.totals.net) == (
            money("500000"), money("200000"), money("300000"),
        )
        expenses = [(c.category_name, c.total, c.share) for c in cop.categories if c.transaction_type.value == "expense"]
        assert expenses == [
            ("Alimentación", money("170000"), Decimal("0.8500")),
            ("Transporte", money("30000"), Decimal("0.1500")),
        ]

    def test_nunca_mezcla_monedas(self):
        facts = [fact("100", currency="COP"), fact("7", currency="USD")]
        sections = {s.currency: s for s in Dashboard.build(OCT, facts).currencies}

        assert sections["COP"].totals.expense == money("100")
        assert sections["USD"].totals.expense == money("7", "USD")

    def test_tendencia_de_seis_meses_con_ceros(self):
        facts = [fact("100", on=date(2026, 5, 1)), fact("50", on=date(2026, 10, 1)), fact("999", on=date(2026, 4, 30))]
        [cop] = Dashboard.build(OCT, facts).currencies

        assert [str(p.period) for p in cop.trend] == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
        assert [p.totals.expense.amount for p in cop.trend] == [100, 0, 0, 0, 0, 50]

    def test_totales_por_cuenta(self):
        a, b = uuid4(), uuid4()
        facts = [fact("100", account=a), fact("40", "income", "Salario", account=b)]
        accounts = {x.account_id: x.totals for x in Dashboard.build(OCT, facts).currencies[0].accounts}
        assert accounts[a].expense == money("100") and accounts[b].income == money("40")

    def test_periodo_vacio(self):
        assert Dashboard.build(OCT, []).currencies == ()


class TestInsights:
    def spike_facts(self, current="200000"):
        history = [fact("100000", on=date(2026, m, 5)) for m in (7, 8, 9)]
        return history + [fact(current, on=date(2026, 10, 5))]

    def test_category_spike_con_su_evidencia(self):
        [spike] = [i for i in detect_insights(OCT, self.spike_facts(), T) if i.type is InsightType.CATEGORY_SPIKE]

        assert (spike.severity, spike.code) == (Severity.WARNING, "category_spike")
        assert params(spike) == {"category_name": "Alimentación", "currency": "COP", "increase_pct": Decimal("100.0")}
        assert evidence(spike)["current"] == money("200000")
        assert evidence(spike)["previous_average"] == money("100000")
        assert evidence(spike)["previous_months"] == (
            ("2026-07", money("100000")), ("2026-08", money("100000")), ("2026-09", money("100000")),
        )

    def test_spike_justo_en_el_umbral(self):
        found = detect_insights(OCT, self.spike_facts("130000"), T)
        assert InsightType.CATEGORY_SPIKE in {i.type for i in found}

    def test_bajo_el_umbral_no_hay_spike(self):
        found = detect_insights(OCT, self.spike_facts("129999"), T)
        assert InsightType.CATEGORY_SPIKE not in {i.type for i in found}

    def test_el_minimo_absoluto_evita_ruido(self):
        facts = [fact("10", on=date(2026, m, 5)) for m in (7, 8, 9)] + [fact("40", on=date(2026, 10, 5))]
        assert InsightType.CATEGORY_SPIKE not in {i.type for i in detect_insights(OCT, facts, T)}

    def test_sin_historia_no_hay_base(self):
        assert InsightType.CATEGORY_SPIKE not in {i.type for i in detect_insights(OCT, [fact("900000")], T)}

    def test_los_meses_sin_gasto_cuentan_como_cero(self):
        facts = [fact("90000", on=date(2026, 9, 5)), fact("60000", on=date(2026, 10, 5))]
        [spike] = [i for i in detect_insights(OCT, facts, T) if i.type is InsightType.CATEGORY_SPIKE]
        assert evidence(spike)["previous_average"] == money("30000")

    def test_umbral_configurable(self):
        strict = replace(T, spike_ratio=Decimal("1.5"))
        assert InsightType.CATEGORY_SPIKE not in {i.type for i in detect_insights(OCT, self.spike_facts(), strict)}

    def test_top_category(self):
        facts = [fact("300", category="Vivienda"), fact("100", category="Compras")]
        [top] = [i for i in detect_insights(OCT, facts, T) if i.type is InsightType.TOP_CATEGORY]

        assert top.severity is Severity.INFO
        assert params(top) == {"category_name": "Vivienda", "currency": "COP", "share_pct": Decimal("75.0")}
        assert evidence(top) == {"category_total": money("300"), "expense_total": money("400")}

    def test_negative_savings(self):
        facts = [fact("100", "income", "Salario"), fact("250")]
        [negative] = [i for i in detect_insights(OCT, facts, T) if i.type is InsightType.NEGATIVE_SAVINGS]

        assert params(negative) == {"currency": "COP", "deficit": money("150")}
        assert evidence(negative) == {"income": money("100"), "expense": money("250")}

    def test_ahorro_positivo_no_genera_alerta(self):
        facts = [fact("300", "income", "Salario"), fact("250")]
        assert InsightType.NEGATIVE_SAVINGS not in {i.type for i in detect_insights(OCT, facts, T)}

    def test_por_moneda(self):
        facts = [fact("100", "income", "Salario"), fact("50"), fact("9", currency="USD")]
        negatives = [i for i in detect_insights(OCT, facts, T) if i.type is InsightType.NEGATIVE_SAVINGS]
        assert [params(i)["currency"] for i in negatives] == ["USD"]

    def test_advertencias_primero(self):
        facts = self.spike_facts() + [fact("1", "income", "Salario", on=date(2026, 10, 1))]
        severities = [i.severity for i in detect_insights(OCT, facts, T)]
        assert severities == sorted(severities, key=lambda s: s is not Severity.WARNING)


class TestSpendingPatterns:
    def netflix(self, months, amount="39900"):
        return [fact(amount, category="Entretenimiento", on=date(2026, m, 3), description="Netflix PREMIUM") for m in months]

    def test_detecta_el_gasto_recurrente(self):
        [pattern] = detect_patterns(OCT, self.netflix((6, 8, 10)), T)

        assert (pattern.description, pattern.category_name, pattern.currency) == ("netflix premium", "Entretenimiento", "COP")
        assert (pattern.months_present, pattern.occurrences, pattern.window_months) == (3, 3, 6)
        assert pattern.average_amount == money("39900")
        assert pattern.monthly_frequency == Decimal("1.00")
        assert pattern.last_seen == date(2026, 10, 3)

    def test_dos_meses_no_bastan(self):
        assert detect_patterns(OCT, self.netflix((9, 10)), T) == ()

    def test_fuera_de_la_ventana_no_cuenta(self):
        assert detect_patterns(OCT, self.netflix((3, 4, 10)), T) == ()

    def test_el_monto_debe_estar_a_mas_o_menos_diez_por_ciento(self):
        facts = self.netflix((6, 8)) + [fact("60000", category="Entretenimiento", on=date(2026, 10, 3), description="netflix premium")]
        assert detect_patterns(OCT, facts, T) == ()

    def test_descripcion_normalizada(self):
        assert normalize_description("  Café   del  Señor!! ") == "cafe del senor"

    def test_descripcion_vacia_no_es_patron(self):
        assert detect_patterns(OCT, [fact("100", on=date(2026, m, 1)) for m in (6, 7, 8)], T) == ()

    def test_otra_categoria_es_otro_patron(self):
        facts = self.netflix((6, 8)) + [fact("39900", category="Compras", on=date(2026, 10, 3), description="netflix premium")]
        assert detect_patterns(OCT, facts, T) == ()

    def test_los_ingresos_no_son_gasto_recurrente(self):
        facts = [fact("100", "income", "Salario", on=date(2026, m, 1), description="nomina") for m in (6, 7, 8)]
        assert detect_patterns(OCT, facts, T) == ()


class TestResumenPublico:
    def test_k_anonimato(self):
        summary = SpendingSummary.build(OCT, [
            ("Alimentación", "COP", 3, Decimal("300000")),
            ("Salud", "COP", 2, Decimal("90000")),
        ], min_users=3)

        assert [(c.category_name, c.users) for c in summary.categories] == [("Alimentación", 3)]
        assert summary.categories[0].average_per_user == money("100000")

    def test_promedio_redondeado(self):
        [row] = SpendingSummary.build(OCT, [("Compras", "COP", 3, Decimal("100"))], min_users=3).categories
        assert row.average_per_user == money("33.33")
