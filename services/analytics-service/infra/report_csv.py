"""El reporte mensual como CSV, en espanol o en ingles (E2-M7).

Adaptador de `ReportRenderer`. Dos bloques separados por una linea vacia:

1. **Movimientos**: fecha, tipo, categoria, descripcion, monto y moneda.
2. **Resumen por categoria y moneda**: moneda, tipo, categoria, total y numero
   de movimientos.

Los encabezados, los tipos y las categorias del catalogo van en el idioma de la
peticion (`Accept-Language`). Los montos van como texto decimal con punto
(`38000.00`), sin separador de miles, para que una hoja de calculo los lea como
numeros en cualquier idioma. Lleva BOM de UTF-8 para que Excel muestre las
tildes. Los servicios Flask no usan gettext (ADR-11); este archivo es la unica
traduccion del lado del servidor, porque el reporte no pasa por el navegador.
"""
import csv
import io

from domain.interfaces import ReportRenderer

LABELS = {
    "es": {
        "transactions": "Movimientos",
        "summary": "Resumen por categoría y moneda",
        "date": "Fecha",
        "type": "Tipo",
        "category": "Categoría",
        "description": "Descripción",
        "amount": "Monto",
        "currency": "Moneda",
        "total": "Total",
        "count": "Movimientos",
        "income": "Ingreso",
        "expense": "Gasto",
        "uncategorized": "Sin categoría",
        "filename": "finty-reporte-{period}.csv",
    },
    "en": {
        "transactions": "Transactions",
        "summary": "Summary by category and currency",
        "date": "Date",
        "type": "Type",
        "category": "Category",
        "description": "Description",
        "amount": "Amount",
        "currency": "Currency",
        "total": "Total",
        "count": "Transactions",
        "income": "Income",
        "expense": "Expense",
        "uncategorized": "No category",
        "filename": "finty-report-{period}.csv",
    },
}

# Categorias del catalogo de finance (sus nombres son datos en espanol). Una que
# no este aqui sale tal cual, como en el frontend.
CATEGORY_NAMES_EN = {
    "Alimentación": "Food",
    "Transporte": "Transportation",
    "Vivienda": "Housing",
    "Servicios públicos": "Utilities",
    "Salud": "Health",
    "Educación": "Education",
    "Entretenimiento": "Entertainment",
    "Compras": "Shopping",
    "Deudas y créditos": "Debt and loans",
    "Otros gastos": "Other expenses",
    "Salario": "Salary",
    "Freelance": "Freelance",
    "Inversiones": "Investments",
    "Reembolsos": "Refunds",
    "Otros ingresos": "Other income",
}


class CsvReportRenderer(ReportRenderer):
    media_type = "text/csv; charset=utf-8"
    extension = "csv"

    def render(self, report, language):
        labels = LABELS[language]
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow([labels["transactions"]])
        writer.writerow([labels[k] for k in ("date", "type", "category", "description", "amount", "currency")])
        for line in report.lines:
            writer.writerow([
                line.occurred_on.isoformat(),
                labels[line.transaction_type.value],
                self._category(line.category_name, language, labels),
                line.description,
                f"{line.amount.amount:.2f}",
                line.amount.currency,
            ])
        writer.writerow([])
        writer.writerow([labels["summary"]])
        writer.writerow([labels[k] for k in ("currency", "type", "category", "total", "count")])
        for item in report.summary:
            writer.writerow([
                item.currency,
                labels[item.transaction_type.value],
                self._category(item.category_name, language, labels),
                f"{item.total.amount:.2f}",
                item.count,
            ])
        return ("﻿" + buffer.getvalue()).encode("utf-8")

    def filename(self, period, language):
        return LABELS[language]["filename"].format(period=period)

    @staticmethod
    def _category(name, language, labels):
        if not name:
            return labels["uncategorized"]
        return CATEGORY_NAMES_EN.get(name, name) if language == "en" else name
