"""Casos de uso de `analytics-service` (anillo de Servicios).

- `EventProjector` aplica un evento de finance-service al modelo de lectura,
  una sola vez por `event_id`.
- `EventConsumer` lleva los mensajes del stream al proyector y los confirma
  solo despues del commit.
- `AnalyticsService` arma `Dashboard`, `Insight` y `SpendingPattern` de un
  usuario a partir de sus transacciones vigentes.
- `PublicSummaryService` arma el resumen publico con k-anonimato.
- `ReportService` pide, genera y entrega el reporte mensual (E2-M7). La
  generacion la ejecuta una tarea de Celery (`tasks.py`).

Las reglas viven en `domain/`; aqui solo se orquesta y se lee la base.
"""
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.dialects.postgresql import insert

from domain.dashboard import Dashboard
from domain.events import EventType
from domain.exceptions import InvalidEventError, ReportNotFoundError, ReportNotReadyError
from domain.facts import TransactionFact
from domain.insights import detect_insights
from domain.patterns import detect_patterns
from domain.period import Period
from domain.report import MonthlyReport, ReportStatus, can_generate, report_language
from domain.shared.value_objects import Money
from domain.summary import SpendingSummary
from models import MonthlyReportRecord, ProcessedEvent, TransactionFactRecord

logger = logging.getLogger(__name__)

APPLIED = "applied"
IGNORED = "ignored"
DUPLICATE = "duplicate"
INVALID = "invalid"


@contextmanager
def atomic(session):
    """Confirma al salir; revierte ante cualquier excepcion (igual que finance)."""
    try:
        yield
        session.commit()
    except BaseException:
        session.rollback()
        raise


class EventProjector:
    """Aplica eventos al modelo de lectura, idempotente por `event_id` (ADR-15)."""

    def __init__(self, session):
        self._session = session

    def project(self, event, stream_id):
        """Aplica `event` y devuelve `applied`, `ignored` o `duplicate`.

        El registro en `processed_event` y el cambio en `transaction_fact` van en
        la misma transaccion: o queda aplicado y registrado, o ninguna de las dos.
        """
        with atomic(self._session):
            inserted = self._session.execute(
                insert(ProcessedEvent)
                .values(
                    event_id=event.event_id,
                    event_type=event.event_type.value,
                    stream_id=stream_id,
                    outcome=APPLIED,
                )
                .on_conflict_do_nothing(index_elements=["event_id"])
                .returning(ProcessedEvent.event_id)
            ).scalar_one_or_none()
            if inserted is None:
                return DUPLICATE

            outcome = self._apply(event)
            if outcome != APPLIED:
                self._session.get(ProcessedEvent, event.event_id).outcome = outcome
            return outcome

    def _apply(self, event):
        snapshot = event.payload
        row = self._session.get(TransactionFactRecord, snapshot.transaction_id, with_for_update=True)
        deleted = event.event_type is EventType.TRANSACTION_DELETED

        if row is None:
            # Cualquier evento trae la foto completa, asi que el primero que
            # llegue crea la fila, aunque llegue fuera de orden.
            self._session.add(TransactionFactRecord(
                **self._snapshot_columns(snapshot),
                deleted_at=event.occurred_at if deleted else None,
                last_event_at=event.occurred_at,
            ))
            return APPLIED

        if row.deleted_at is not None:
            return IGNORED  # una transaccion borrada no vuelve
        if deleted:
            row.deleted_at = event.occurred_at
        elif event.occurred_at < row.last_event_at:
            return IGNORED  # ya se aplico un estado mas reciente
        elif event.event_type is EventType.TRANSACTION_CATEGORIZED:
            row.category_name = snapshot.category_name
            row.categorization_source = snapshot.categorization_source
        else:
            for column, value in self._snapshot_columns(snapshot).items():
                setattr(row, column, value)
        row.last_event_at = max(row.last_event_at, event.occurred_at)
        return APPLIED

    @staticmethod
    def _snapshot_columns(snapshot):
        return {
            "transaction_id": snapshot.transaction_id,
            "user_id": snapshot.user_id,
            "account_id": snapshot.account_id,
            "amount": snapshot.amount.amount,
            "currency": snapshot.amount.currency,
            "transaction_type": snapshot.transaction_type.value,
            "category_name": snapshot.category_name,
            "categorization_source": snapshot.categorization_source,
            "description": snapshot.description,
            "occurred_on": snapshot.occurred_on,
        }


class EventConsumer:
    """Lleva mensajes del stream al proyector. Confirma solo tras el commit.

    `decode` convierte los campos de un mensaje en `FinanceEvent` (lo inyecta el
    comando, desde `infra/`). Un mensaje fuera de contrato se registra en el log
    y se confirma, para no bloquear el grupo; un error de base o de Redis sube,
    el mensaje queda pendiente y se recupera despues.
    """

    def __init__(self, source, projector, decode):
        self._source = source
        self._projector = projector
        self._decode = decode

    def recover(self):
        """Procesa los pendientes sin confirmar. Devuelve cuantos proceso."""
        return self._handle_all(self._source.claim_pending())

    def poll(self):
        """Procesa los mensajes nuevos. Devuelve cuantos proceso."""
        return self._handle_all(self._source.read_new())

    def _handle_all(self, messages):
        for message_id, fields in messages:
            self._handle(message_id, fields)
        return len(messages)

    def _handle(self, message_id, fields):
        try:
            event = self._decode(fields)
        except InvalidEventError as exc:
            logger.warning("Mensaje %s descartado: %s", message_id, exc)
            self._source.ack(message_id)
            return INVALID
        outcome = self._projector.project(event, message_id)
        self._source.ack(message_id)
        return outcome


class AnalyticsService:
    """Dashboard, insights y patrones de un usuario. Se calculan al leer."""

    def __init__(self, session, thresholds):
        self._session = session
        self._thresholds = thresholds

    def dashboard(self, user_id, period, earliest_period=None):
        """`earliest_period`: primer periodo visible para el plan del usuario (INV-06)."""
        window = period.window(self._thresholds.trend_months)
        first = min(window[0], period.shift(-1))
        facts = self._facts(user_id, first, period)
        return Dashboard.build(period, facts, self._thresholds.trend_months, earliest_period)

    def insights(self, user_id, period):
        first = period.shift(-self._thresholds.spike_lookback_months)
        return detect_insights(period, self._facts(user_id, first, period), self._thresholds)

    def spending_patterns(self, user_id, reference):
        window = reference.window(self._thresholds.pattern_window_months)
        return detect_patterns(reference, self._facts(user_id, window[0], reference), self._thresholds)

    def _facts(self, user_id, first, last):
        return load_facts(self._session, user_id, first, last)


def load_facts(session, user_id, first, last):
    """Transacciones vigentes de `user_id` entre los periodos `first` y `last`."""
    rows = session.execute(
        select(TransactionFactRecord).where(
            TransactionFactRecord.user_id == user_id,
            TransactionFactRecord.deleted_at.is_(None),
            TransactionFactRecord.occurred_on >= first.start,
            TransactionFactRecord.occurred_on < last.end,
        )
    ).scalars()
    return [
        TransactionFact(
            transaction_id=row.transaction_id,
            account_id=row.account_id,
            amount=Money(row.amount, row.currency),
            transaction_type=row.transaction_type,
            category_name=row.category_name,
            description=row.description,
            occurred_on=row.occurred_on,
        )
        for row in rows
    ]


class PublicSummaryService:
    """Resumen publico de gasto por categoria (ADR-13), con k-anonimato."""

    def __init__(self, session, thresholds):
        self._session = session
        self._thresholds = thresholds

    def spending_summary(self, period):
        fact = TransactionFactRecord
        aggregates = self._session.execute(
            select(
                fact.category_name,
                fact.currency,
                func.count(func.distinct(fact.user_id)),
                func.sum(fact.amount),
            )
            .where(
                fact.transaction_type == "expense",
                fact.deleted_at.is_(None),
                fact.occurred_on >= period.start,
                fact.occurred_on < period.end,
            )
            .group_by(fact.category_name, fact.currency)
        ).all()
        return SpendingSummary.build(period, aggregates, self._thresholds.public_min_users)


# --- Reporte mensual (E2-M7) ----------------------------------------------------

# Errores que pasan solos: la tarea reintenta con espera creciente.
TRANSIENT_ERRORS = (OperationalError, DBAPIError, ConnectionError, TimeoutError)
# Un PENDING mas viejo que esto se vuelve a encolar (se perdio el mensaje, o el
# broker no respondio al pedirlo).
STALE_AFTER = timedelta(minutes=2)
FAILURE_DETAIL_LENGTH = 200


def utcnow():
    return datetime.now(timezone.utc)


class ReportService:
    """Casos de uso del reporte mensual.

    La peticion solo crea el registro PENDING y lo encola; la tarea de Celery
    llama a `generate`, que es idempotente: un reporte que ya no esta PENDING no
    se vuelve a generar, y la fila se bloquea con `SKIP LOCKED` para que dos
    entregas del mismo mensaje no lo generen a la vez.
    """

    def __init__(self, session, renderer, queue=None, clock=utcnow):
        self._session = session
        self._renderer = renderer
        self._queue = queue
        self._clock = clock

    def request(self, user_id, period, language):
        with atomic(self._session):
            record = MonthlyReportRecord(
                user_id=user_id,
                period=str(period),
                language=report_language(language),
                status=ReportStatus.PENDING.value,
                created_at=self._clock(),
            )
            self._session.add(record)
        self._enqueue(record.id)
        return record

    def get(self, user_id, report_id):
        record = self._session.get(MonthlyReportRecord, report_id)
        if record is None or record.user_id != user_id:
            raise ReportNotFoundError()
        return record

    def download(self, user_id, report_id):
        record = self.get(user_id, report_id)
        if ReportStatus(record.status) is not ReportStatus.READY:
            raise ReportNotReadyError()
        return record

    def generate(self, report_id):
        """Genera el archivo de un reporte PENDING. Devuelve el estado final.

        Un error transitorio (la base) se propaga para que la tarea reintente y
        el reporte sigue PENDING. Cualquier otro lo deja FAILED.
        """
        with atomic(self._session):
            record = self._session.scalars(
                select(MonthlyReportRecord)
                .where(MonthlyReportRecord.id == report_id)
                .with_for_update(skip_locked=True)
            ).one_or_none()
            if record is None or not can_generate(record.status):
                return record.status if record is not None else None
            period = Period.parse(record.period)
            facts = load_facts(self._session, record.user_id, period, period)
            try:
                report = MonthlyReport.build(period, facts)
                content = self._renderer.render(report, record.language)
            except TRANSIENT_ERRORS:
                raise
            except Exception as exc:  # noqa: BLE001 — un reporte que no se puede armar queda FAILED
                logger.exception("reporte %s fallo al generarse", report_id)
                record.status = ReportStatus.FAILED.value
                record.failure = f"{type(exc).__name__}: {exc}"[:FAILURE_DETAIL_LENGTH]
                record.completed_at = self._clock()
                return record.status
            record.content = content
            record.media_type = self._renderer.media_type
            record.filename = self._renderer.filename(record.period, record.language)
            record.status = ReportStatus.READY.value
            record.completed_at = self._clock()
            return record.status

    def requeue_stale(self):
        """Vuelve a encolar los PENDING viejos. Devuelve cuantos encolo."""
        limit = self._clock() - STALE_AFTER
        ids = self._session.scalars(
            select(MonthlyReportRecord.id).where(
                MonthlyReportRecord.status == ReportStatus.PENDING.value,
                MonthlyReportRecord.created_at < limit,
            )
        ).all()
        self._session.rollback()
        return sum(1 for report_id in ids if self._enqueue(report_id))

    def _enqueue(self, report_id):
        """Encola sin fallar la peticion: si el broker no responde, queda PENDING
        y `requeue_stale` lo recoge despues."""
        if self._queue is None:
            return False
        try:
            self._queue.enqueue(report_id)
        except Exception as exc:  # noqa: BLE001 — el broker caido no tumba la peticion
            logger.warning("no se pudo encolar el reporte %s (%s): queda PENDING", report_id, exc)
            return False
        return True
