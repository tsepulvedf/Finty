"""Reporte mensual (E2-M7, ADR-15): que contiene y en que estados pasa.

Lo arma una tarea de Celery fuera de la peticion. El contenido sale de las
transacciones vigentes del periodo que conoce analytics (sus eventos, ADR-10):

- **Movimientos**, por fecha y despues por tipo, categoria y descripcion.
- **Resumen** por moneda, tipo y categoria: total y numero de movimientos. Nunca
  suma monedas distintas.

El formato (CSV, encabezados en el idioma pedido) lo pone el adaptador de
`infra/`; aqui solo hay datos.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from domain.shared.value_objects import Money
from domain.value_objects import TransactionType

SUPPORTED_LANGUAGES = ("es", "en")
DEFAULT_LANGUAGE = "es"
DEFAULT_RETENTION_DAYS = 7


class ReportStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


def report_language(code):
    """`es` o `en` a partir de una etiqueta como `en-US`; cualquier otra, `es`."""
    prefix = (code or "").split("-")[0].strip().lower()
    return prefix if prefix in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def retention_cutoff(now, retention_days=DEFAULT_RETENTION_DAYS):
    """Un reporte creado antes de este instante ya cumplio su retencion (D-33).

    Se cuenta desde que se pidio, en cualquier estado: un PENDING de hace una
    semana tampoco sirve. La retencion es de al menos un dia.
    """
    if retention_days < 1:
        raise ValueError(f"La retencion de reportes debe ser de al menos 1 dia: {retention_days}")
    return now - timedelta(days=retention_days)


def can_generate(status):
    """Solo un reporte pendiente se genera: la tarea es idempotente."""
    return ReportStatus(status) is ReportStatus.PENDING


@dataclass(frozen=True)
class ReportLine:
    occurred_on: date
    transaction_type: TransactionType
    category_name: str | None
    description: str
    amount: Money


@dataclass(frozen=True)
class ReportSummaryLine:
    currency: str
    transaction_type: TransactionType
    category_name: str | None
    total: Money
    count: int


@dataclass(frozen=True)
class MonthlyReport:
    period: object
    lines: tuple
    summary: tuple

    @classmethod
    def build(cls, period, facts):
        """Movimientos y resumen de `period`; ignora los de otros meses."""
        own = [fact for fact in facts if fact.period == period]
        lines = tuple(sorted(
            (
                ReportLine(f.occurred_on, f.transaction_type, f.category_name, f.description, f.amount)
                for f in own
            ),
            key=lambda line: (
                line.occurred_on, line.transaction_type.value, line.category_name or "",
                line.description, line.amount.currency, line.amount.amount,
            ),
        ))
        groups = {}
        for fact in own:
            key = (fact.currency, fact.transaction_type, fact.category_name)
            total, count = groups.get(key, (Money.zero(fact.currency), 0))
            groups[key] = (total.add(fact.amount), count + 1)
        summary = tuple(
            ReportSummaryLine(currency, kind, category, total, count)
            for (currency, kind, category), (total, count) in sorted(
                groups.items(), key=lambda item: (item[0][0], item[0][1].value, item[0][2] or "")
            )
        )
        return cls(period, lines, summary)
