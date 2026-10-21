"""Casos de uso de `analytics-service` (anillo de Servicios).

- `EventProjector` aplica un evento de finance-service al modelo de lectura,
  una sola vez por `event_id`.
- `EventConsumer` lleva los mensajes del stream al proyector y los confirma
  solo despues del commit.
- `AnalyticsService` arma `Dashboard`, `Insight` y `SpendingPattern` de un
  usuario a partir de sus transacciones vigentes.
- `PublicSummaryService` arma el resumen publico con k-anonimato.

Las reglas viven en `domain/`; aqui solo se orquesta y se lee la base.
"""
import logging
from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from domain.dashboard import Dashboard
from domain.events import EventType
from domain.exceptions import InvalidEventError
from domain.facts import TransactionFact
from domain.insights import detect_insights
from domain.patterns import detect_patterns
from domain.shared.value_objects import Money
from domain.summary import SpendingSummary
from models import ProcessedEvent, TransactionFactRecord

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

    def dashboard(self, user_id, period):
        window = period.window(self._thresholds.trend_months)
        facts = self._facts(user_id, window[0], period)
        return Dashboard.build(period, facts, self._thresholds.trend_months)

    def insights(self, user_id, period):
        first = period.shift(-self._thresholds.spike_lookback_months)
        return detect_insights(period, self._facts(user_id, first, period), self._thresholds)

    def spending_patterns(self, user_id, reference):
        window = reference.window(self._thresholds.pattern_window_months)
        return detect_patterns(reference, self._facts(user_id, window[0], reference), self._thresholds)

    def _facts(self, user_id, first, last):
        rows = self._session.execute(
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
