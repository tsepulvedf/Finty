"""El reporte como CSV en espanol y en ingles (E2-M7). Sin base de datos."""
import csv
import io
from datetime import date
from uuid import uuid4

import pytest

from domain.facts import TransactionFact
from domain.period import Period
from domain.report import MonthlyReport
from domain.shared.value_objects import Money
from infra.report_csv import CsvReportRenderer

OCTOBER = Period.parse("2026-10")


def report():
    facts = [
        TransactionFact(uuid4(), uuid4(), Money("38000", "COP"), "expense", "Alimentación", "Almuerzo, con café", date(2026, 10, 2)),
        TransactionFact(uuid4(), uuid4(), Money("3100000", "COP"), "income", "Salario", "Nómina", date(2026, 10, 1)),
        TransactionFact(uuid4(), uuid4(), Money("12.5", "USD"), "expense", None, "Suscripción", date(2026, 10, 3)),
    ]
    return MonthlyReport.build(OCTOBER, facts)


def rows(content):
    text = content.decode("utf-8")
    assert text.startswith("﻿"), "BOM para que Excel lea las tildes"
    return list(csv.reader(io.StringIO(text[1:])))


class TestCsv:
    def test_espanol(self):
        data = rows(CsvReportRenderer().render(report(), "es"))
        assert data[0] == ["Movimientos"]
        assert data[1] == ["Fecha", "Tipo", "Categoría", "Descripción", "Monto", "Moneda"]
        assert data[2] == ["2026-10-01", "Ingreso", "Salario", "Nómina", "3100000.00", "COP"]
        assert data[3] == ["2026-10-02", "Gasto", "Alimentación", "Almuerzo, con café", "38000.00", "COP"]
        assert data[4] == ["2026-10-03", "Gasto", "Sin categoría", "Suscripción", "12.50", "USD"]
        assert data[5] == []
        assert data[6] == ["Resumen por categoría y moneda"]
        assert data[7] == ["Moneda", "Tipo", "Categoría", "Total", "Movimientos"]
        assert data[8:] == [
            ["COP", "Gasto", "Alimentación", "38000.00", "1"],
            ["COP", "Ingreso", "Salario", "3100000.00", "1"],
            ["USD", "Gasto", "Sin categoría", "12.50", "1"],
        ]

    def test_ingles_traduce_encabezados_tipos_y_categorias_del_catalogo(self):
        data = rows(CsvReportRenderer().render(report(), "en"))
        assert data[0] == ["Transactions"]
        assert data[1] == ["Date", "Type", "Category", "Description", "Amount", "Currency"]
        assert data[2] == ["2026-10-01", "Income", "Salary", "Nómina", "3100000.00", "COP"]
        assert data[4][2] == "No category"
        assert data[6] == ["Summary by category and currency"]
        assert data[8] == ["COP", "Expense", "Food", "38000.00", "1"]

    def test_una_categoria_fuera_del_catalogo_sale_tal_cual(self):
        facts = [TransactionFact(uuid4(), uuid4(), Money("1", "COP"), "expense", "Mascotas", "", date(2026, 10, 1))]
        data = rows(CsvReportRenderer().render(MonthlyReport.build(OCTOBER, facts), "en"))
        assert data[2][2] == "Mascotas"

    @pytest.mark.parametrize("language, nombre", [("es", "finty-reporte-2026-10.csv"), ("en", "finty-report-2026-10.csv")])
    def test_nombre_del_archivo(self, language, nombre):
        assert CsvReportRenderer().filename("2026-10", language) == nombre

    def test_periodo_vacio_tiene_solo_encabezados(self):
        data = rows(CsvReportRenderer().render(MonthlyReport.build(OCTOBER, []), "es"))
        assert data == [["Movimientos"], ["Fecha", "Tipo", "Categoría", "Descripción", "Monto", "Moneda"], [],
                        ["Resumen por categoría y moneda"], ["Moneda", "Tipo", "Categoría", "Total", "Movimientos"]]
