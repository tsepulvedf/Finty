"""Reporte mensual en el dominio (E2-M7). Sin base de datos."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.facts import TransactionFact
from domain.period import Period
from domain.report import (
    MonthlyReport,
    ReportStatus,
    can_generate,
    report_language,
    retention_cutoff,
    stale_cutoff,
    validate_positive_seconds,
)
from domain.shared.value_objects import Money
from domain.value_objects import TransactionType

OCTOBER = Period.parse("2026-10")


def fact(amount, kind="expense", category="Alimentación", on=date(2026, 10, 10), currency="COP", description=""):
    return TransactionFact(uuid4(), uuid4(), Money(amount, currency), kind, category, description, on)


class TestContenido:
    def test_solo_entran_los_movimientos_del_periodo(self):
        report = MonthlyReport.build(OCTOBER, [fact("100"), fact("50", on=date(2026, 9, 30))])
        assert [line.amount.amount for line in report.lines] == [Decimal("100.00")]

    def test_ordena_por_fecha(self):
        report = MonthlyReport.build(OCTOBER, [
            fact("1", on=date(2026, 10, 20)), fact("2", on=date(2026, 10, 1)), fact("3", on=date(2026, 10, 5)),
        ])
        assert [line.occurred_on.day for line in report.lines] == [1, 5, 20]

    def test_resumen_por_moneda_tipo_y_categoria(self):
        report = MonthlyReport.build(OCTOBER, [
            fact("100"), fact("50"), fact("30", category="Transporte"),
            fact("2000", kind="income", category="Salario"),
            fact("10", currency="USD"),
        ])
        resumen = [(s.currency, s.transaction_type, s.category_name, s.total.amount, s.count) for s in report.summary]
        assert resumen == [
            ("COP", TransactionType.EXPENSE, "Alimentación", Decimal("150.00"), 2),
            ("COP", TransactionType.EXPENSE, "Transporte", Decimal("30.00"), 1),
            ("COP", TransactionType.INCOME, "Salario", Decimal("2000.00"), 1),
            ("USD", TransactionType.EXPENSE, "Alimentación", Decimal("10.00"), 1),
        ]

    def test_nunca_suma_monedas_distintas(self):
        report = MonthlyReport.build(OCTOBER, [fact("100"), fact("100", currency="USD")])
        assert {s.total.currency for s in report.summary} == {"COP", "USD"}
        assert all(s.total.amount == Decimal("100.00") for s in report.summary)

    def test_sin_categoria(self):
        report = MonthlyReport.build(OCTOBER, [fact("5", category=None)])
        assert report.summary[0].category_name is None

    def test_periodo_sin_movimientos(self):
        report = MonthlyReport.build(OCTOBER, [])
        assert report.lines == () and report.summary == ()


class TestEstadoEIdioma:
    @pytest.mark.parametrize("code, esperado", [
        ("en", "en"), ("en-US", "en"), ("EN-gb", "en"), ("es-CO", "es"), ("es", "es"),
        ("fr", "es"), ("", "es"), (None, "es"),
    ])
    def test_idioma_del_reporte(self, code, esperado):
        assert report_language(code) == esperado

    def test_solo_un_pendiente_se_genera(self):
        assert can_generate("PENDING")
        assert not can_generate(ReportStatus.READY)
        assert not can_generate("FAILED")


class TestRetencion:
    NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)

    def test_por_defecto_7_dias(self):
        assert retention_cutoff(self.NOW) == self.NOW - timedelta(days=7)

    def test_configurable(self):
        assert retention_cutoff(self.NOW, 30) == self.NOW - timedelta(days=30)

    @pytest.mark.parametrize("days", [0, -1])
    def test_al_menos_un_dia(self, days):
        with pytest.raises(ValueError):
            retention_cutoff(self.NOW, days)


class TestRecuperacion:
    """E2-M9c: un PENDING con mas de 60 s (configurable) se vuelve a encolar."""

    NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)

    def test_por_defecto_un_minuto(self):
        assert stale_cutoff(self.NOW) == self.NOW - timedelta(seconds=60)

    def test_configurable(self):
        assert stale_cutoff(self.NOW, 90) == self.NOW - timedelta(seconds=90)

    @pytest.mark.parametrize("valor", [0, -1, 1.5, "60", True, None])
    def test_rechaza_lo_que_no_es_un_entero_positivo(self, valor):
        with pytest.raises(ValueError):
            validate_positive_seconds("REPORT_STALE_AFTER_SECONDS", valor)
