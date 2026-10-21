"""Eventos de dominio y outbox transaccional (ADR-15, E2-M4a).

- Los eventos son value objects inmutables, y su serializacion es el contrato
  de §10.5.
- Registrar, reclasificar y eliminar escriben su evento en la misma transaccion
  que el cambio. Atomicidad en los dos sentidos: si el cambio falla no queda
  evento, y si el evento no se puede escribir no queda cambio.
- El relay publica en orden, marca lo publicado y no pierde nada si el stream
  falla. El backfill es idempotente.
"""
import json
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import redis
from sqlalchemy import func, select, update

from commands import EVENT_STREAM_FACTORY_KEY
from domain import events
from domain.exceptions import NegativeBalanceNotAllowedError, ZeroAmountError
from domain.interfaces import EventOutbox, EventStream, EventStreamUnavailable
from domain.shared.exceptions import ValidationError
from domain.shared.value_objects import Money
from domain.value_objects import CategorizationSource, TransactionType
from infra.event_serialization import to_stream_message
from infra.outbox import SqlAlchemyOutbox
from infra.redis_stream import FINANCE_EVENTS_STREAM, RedisEventStream
from models import Account, OutboxEvent, Transaction
from services import AccountService, OutboxBackfill, OutboxRelay, TransactionService
from tests.doubles import MockCategorizer

YESTERDAY = date.today() - timedelta(days=1)
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def facts(**overrides):
    values = {
        "user_id": uuid4(),
        "transaction_id": uuid4(),
        "account_id": uuid4(),
        "amount": Money("120000", "COP"),
        "transaction_type": "expense",
        "category_name": "Alimentación",
        "categorization_source": "rule",
        "occurred_on": date(2026, 10, 19),
    }
    values.update(overrides)
    return events.TransactionFacts(**values)


class MemoryStream(EventStream):
    """Stream en memoria que puede fallar a voluntad."""

    def __init__(self):
        self.messages = []
        self.down = False

    def publish(self, message):
        if self.down:
            raise EventStreamUnavailable("caido")
        self.messages.append(dict(message))
        return f"{len(self.messages)}-0"


class FailingOutbox(EventOutbox):
    def record(self, event):
        raise RuntimeError("no se pudo escribir el evento")


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def account(session, user_id):
    return AccountService(session).create_account(
        user_id, "Cuenta corriente", "bank", initial_balance=Decimal("1000000.00")
    )


@pytest.fixture
def service(session):
    return TransactionService(session, MockCategorizer("Alimentación", 0.9), SqlAlchemyOutbox(session))


def register(service, user_id, account, amount="120000", kind="expense", **extra):
    return service.register_transaction(
        user_id=user_id, account_id=account.id, amount=Decimal(amount),
        transaction_type=kind, occurred_on=YESTERDAY, **extra,
    )


def outbox_rows(session):
    session.expire_all()
    return session.execute(select(OutboxEvent).order_by(OutboxEvent.id)).scalars().all()


def count(session, model):
    return session.execute(select(func.count()).select_from(model)).scalar_one()


# ---------------------------------------------------------------------------
# Dominio y serializacion
# ---------------------------------------------------------------------------


class TestEventosDeDominio:
    def test_son_inmutables(self):
        event = events.transaction_manually_added(facts(), NOW)
        with pytest.raises(FrozenInstanceError):
            event.event_type = events.EventType.TRANSACTION_DELETED

    def test_cada_evento_tiene_su_propio_id(self):
        assert events.transaction_deleted(facts(), NOW).event_id != events.transaction_deleted(facts(), NOW).event_id

    @pytest.mark.parametrize(
        "builder,name",
        [
            (events.transaction_manually_added, "TransactionManuallyAdded"),
            (events.transaction_categorized, "TransactionCategorized"),
            (events.transaction_deleted, "TransactionDeleted"),
        ],
    )
    def test_tipos_y_version(self, builder, name):
        event = builder(facts(), NOW)
        assert (event.event_type.value, event.version) == (name, events.EVENT_SCHEMA_VERSION)

    def test_occurred_at_sin_zona_horaria_se_rechaza(self):
        with pytest.raises(ValidationError):
            events.transaction_deleted(facts(), datetime(2026, 10, 20, 12, 0))

    def test_el_monto_debe_ser_money(self):
        with pytest.raises(ValidationError):
            facts(amount=Decimal("1"))


class TestSerializacion:
    def test_mensaje_plano_de_cadenas(self):
        message = to_stream_message(events.transaction_manually_added(facts(), NOW))

        assert list(message) == ["event_id", "event_type", "version", "occurred_at", "payload"]
        assert all(isinstance(value, str) for value in message.values())
        assert message["version"] == "1"
        assert message["occurred_at"] == "2026-10-20T12:00:00Z"

    def test_payload_suficiente_para_analytics(self):
        payload = json.loads(to_stream_message(events.transaction_manually_added(facts(), NOW))["payload"])

        assert set(payload) == {
            "user_id", "transaction_id", "account_id", "amount", "currency",
            "transaction_type", "category_name", "categorization_source", "occurred_on",
        }
        assert (payload["amount"], payload["currency"]) == ("120000.00", "COP")
        assert payload["occurred_on"] == "2026-10-19"
        assert payload["category_name"] == "Alimentación"

    def test_sin_categoria_viaja_null(self):
        message = to_stream_message(
            events.transaction_deleted(facts(category_name=None, categorization_source=None), NOW)
        )
        payload = json.loads(message["payload"])
        assert payload["category_name"] is None and payload["categorization_source"] is None


# ---------------------------------------------------------------------------
# Escritura en el outbox
# ---------------------------------------------------------------------------


class TestCadaEscrituraRegistraSuEvento:
    def test_registrar(self, session, service, user_id, account):
        created = register(service, user_id, account)

        [row] = outbox_rows(session)
        payload = json.loads(row.message["payload"])
        assert row.event_type == "TransactionManuallyAdded"
        assert row.aggregate_id == created.id
        assert row.published_at is None
        assert payload == {
            "user_id": str(user_id),
            "transaction_id": str(created.id),
            "account_id": str(account.id),
            "amount": "120000.00",
            "currency": "COP",
            "transaction_type": "expense",
            "category_name": "Alimentación",
            "categorization_source": "mock",
            "occurred_on": YESTERDAY.isoformat(),
        }

    def test_reclasificar(self, session, service, user_id, account):
        created = register(service, user_id, account)
        service.recategorize(user_id, created.id, "Compras")

        row = outbox_rows(session)[-1]
        payload = json.loads(row.message["payload"])
        assert row.event_type == "TransactionCategorized"
        assert (payload["category_name"], payload["categorization_source"]) == ("Compras", "manual")

    def test_eliminar_lleva_la_foto_previa(self, session, service, user_id, account):
        created = register(service, user_id, account)
        service.delete_transaction(user_id, created.id)

        row = outbox_rows(session)[-1]
        payload = json.loads(row.message["payload"])
        assert row.event_type == "TransactionDeleted"
        assert (payload["transaction_id"], payload["amount"]) == (str(created.id), "120000.00")

    def test_los_eventos_quedan_en_orden(self, session, service, user_id, account):
        created = register(service, user_id, account)
        service.recategorize(user_id, created.id, "Compras")
        service.delete_transaction(user_id, created.id)

        assert [r.event_type for r in outbox_rows(session)] == [
            "TransactionManuallyAdded", "TransactionCategorized", "TransactionDeleted",
        ]


class TestAtomicidad:
    """El cambio y su evento se confirman juntos o no se confirman."""

    @pytest.mark.parametrize(
        "amount,error", [("0", ZeroAmountError), ("5000000", NegativeBalanceNotAllowedError)]
    )
    def test_si_el_registro_falla_no_queda_evento(self, session, user_id, error, amount):
        cash = AccountService(session).create_account(user_id, "Efectivo", "cash")
        service = TransactionService(session, MockCategorizer(), SqlAlchemyOutbox(session))

        with pytest.raises(error):
            register(service, user_id, cash, amount)

        assert count(session, OutboxEvent) == 0
        assert count(session, Transaction) == 0

    def test_si_el_evento_no_se_escribe_no_queda_registro(self, session, user_id, account):
        service = TransactionService(session, MockCategorizer(), FailingOutbox())

        with pytest.raises(RuntimeError):
            register(service, user_id, account)

        assert count(session, Transaction) == 0
        session.expire_all()
        assert session.get(Account, account.id).balance == Decimal("1000000.00")

    def test_si_la_base_rechaza_el_evento_tampoco_queda_registro(self, session, user_id, account):
        """La fila del outbox viola su unicidad al confirmar: se revierte todo."""
        taken = uuid4()
        session.add(OutboxEvent(
            event_id=taken, event_type="TransactionDeleted", aggregate_id=uuid4(),
            version=1, occurred_at=NOW, message={},
        ))
        session.commit()

        class DuplicatedIdOutbox(SqlAlchemyOutbox):
            def record(self, event):
                super().record(events.DomainEvent(taken, event.event_type, event.occurred_at, event.version, event.payload))

        service = TransactionService(session, MockCategorizer(), DuplicatedIdOutbox(session))
        with pytest.raises(Exception):
            register(service, user_id, account)

        assert count(session, Transaction) == 0
        assert count(session, OutboxEvent) == 1

    def test_si_el_borrado_se_rechaza_no_queda_evento(self, session, user_id):
        cash = AccountService(session).create_account(user_id, "Efectivo", "cash")
        service = TransactionService(session, MockCategorizer(), SqlAlchemyOutbox(session))
        income = register(service, user_id, cash, "100", "income", category_name="Salario")
        register(service, user_id, cash, "100", "expense")

        with pytest.raises(NegativeBalanceNotAllowedError):
            service.delete_transaction(user_id, income.id)

        assert "TransactionDeleted" not in [r.event_type for r in outbox_rows(session)]


# ---------------------------------------------------------------------------
# Relay
# ---------------------------------------------------------------------------


class TestRelay:
    def test_publica_en_orden_y_marca(self, session, service, user_id, account):
        created = register(service, user_id, account)
        service.recategorize(user_id, created.id, "Compras")
        stream = MemoryStream()

        published = OutboxRelay(session, stream).publish_pending()

        assert published == 2
        assert [m["event_type"] for m in stream.messages] == ["TransactionManuallyAdded", "TransactionCategorized"]
        rows = outbox_rows(session)
        assert all(r.published_at is not None for r in rows)
        assert [r.stream_id for r in rows] == ["1-0", "2-0"]

    def test_publica_el_mensaje_tal_cual_se_guardo(self, session, service, user_id, account):
        register(service, user_id, account)
        stream = MemoryStream()
        OutboxRelay(session, stream).publish_pending()
        assert stream.messages[0] == outbox_rows(session)[0].message

    def test_no_republica_lo_publicado(self, session, service, user_id, account):
        register(service, user_id, account)
        stream = MemoryStream()
        relay = OutboxRelay(session, stream)
        relay.publish_pending()

        assert relay.publish_pending() == 0
        assert len(stream.messages) == 1

    def test_con_el_stream_caido_no_pierde_eventos(self, session, service, user_id, account):
        register(service, user_id, account)
        stream = MemoryStream()
        stream.down = True
        relay = OutboxRelay(session, stream)

        with pytest.raises(EventStreamUnavailable):
            relay.publish_pending()
        assert relay.pending_count() == 1

        stream.down = False
        assert relay.publish_pending() == 1
        assert relay.pending_count() == 0

    def test_respeta_el_limite(self, session, service, user_id, account):
        for _ in range(3):
            register(service, user_id, account, "1")
        assert OutboxRelay(session, MemoryStream()).publish_pending(limit=2) == 2


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


class TestBackfill:
    @pytest.fixture
    def previas(self, session, account):
        """Dos transacciones escritas sin evento, como antes del outbox."""
        for amount in ("10", "20"):
            session.add(Transaction(
                account_id=account.id, amount=Decimal(amount), type="expense",
                occurred_on=YESTERDAY, category=None,
            ))
        session.commit()

    def test_genera_un_evento_por_transaccion_sin_evento(self, session, account, previas):
        created = OutboxBackfill(session, SqlAlchemyOutbox(session)).run()

        rows = outbox_rows(session)
        assert created == 2
        assert {r.event_type for r in rows} == {"TransactionManuallyAdded"}

    def test_es_idempotente(self, session, account, previas):
        backfill = OutboxBackfill(session, SqlAlchemyOutbox(session))
        backfill.run()
        assert backfill.run() == 0
        assert count(session, OutboxEvent) == 2

    def test_no_duplica_las_que_ya_tienen_evento(self, session, service, user_id, account, previas):
        register(service, user_id, account)
        assert OutboxBackfill(session, SqlAlchemyOutbox(session)).run() == 2
        assert count(session, OutboxEvent) == 3

    def test_occurred_at_es_el_registro_original(self, session, account, previas):
        OutboxBackfill(session, SqlAlchemyOutbox(session)).run()
        row = outbox_rows(session)[0]
        movement = session.get(Transaction, row.aggregate_id)
        assert row.occurred_at == movement.created_at

    def test_la_base_impide_un_segundo_manually_added(self, session, service, user_id, account):
        created = register(service, user_id, account)
        session.add(OutboxEvent(
            event_id=uuid4(), event_type="TransactionManuallyAdded", aggregate_id=created.id,
            version=1, occurred_at=NOW, message={},
        ))
        with pytest.raises(Exception, match="uq_outbox_manually_added_once"):
            session.commit()


# ---------------------------------------------------------------------------
# Adaptador de Redis y comandos
# ---------------------------------------------------------------------------


class TestRedisEventStream:
    def test_publica_con_xadd_en_el_stream(self):
        class Client:
            def xadd(self, stream, fields):
                self.call = (stream, fields)
                return "1-0"

        client = Client()
        assert RedisEventStream(client).publish({"a": "b"}) == "1-0"
        assert client.call == (FINANCE_EVENTS_STREAM, {"a": "b"})

    def test_un_error_de_redis_es_event_stream_unavailable(self):
        class Client:
            def xadd(self, stream, fields):
                raise redis.exceptions.ConnectionError("sin conexion")

        with pytest.raises(EventStreamUnavailable):
            RedisEventStream(Client()).publish({"a": "b"})

    def test_contra_un_redis_inexistente_tambien(self):
        with pytest.raises(EventStreamUnavailable):
            RedisEventStream.from_url("redis://127.0.0.1:9/0").publish({"a": "b"})


class TestComandos:
    @pytest.fixture
    def stream(self, app):
        memory = MemoryStream()
        app.extensions[EVENT_STREAM_FACTORY_KEY] = lambda: memory
        return memory

    def test_relay_once_publica(self, app, session, service, user_id, account, stream):
        register(service, user_id, account)

        result = app.test_cli_runner().invoke(args=["relay-outbox", "--once"])

        assert result.exit_code == 0
        assert "1 evento(s) publicados" in result.output
        assert len(stream.messages) == 1

    def test_relay_con_redis_caido_no_termina_con_error(self, app, session, service, user_id, account, stream):
        register(service, user_id, account)
        stream.down = True

        result = app.test_cli_runner().invoke(args=["relay-outbox", "--once"])

        assert result.exit_code == 0
        assert "reintento en" in result.output
        assert OutboxRelay(session, stream).pending_count() == 1

    def test_backfill(self, app, session, account):
        session.add(Transaction(account_id=account.id, amount=Decimal("5"), type="expense", occurred_on=YESTERDAY))
        session.commit()

        first = app.test_cli_runner().invoke(args=["outbox-backfill"])
        second = app.test_cli_runner().invoke(args=["outbox-backfill"])

        assert "1 evento(s)" in first.output
        assert "0 evento(s)" in second.output


class TestPorHttp:
    def test_registrar_por_la_api_deja_el_evento(self, session, ana):
        cuenta = ana.post("/api/v1/accounts/", {"name": "Banco", "type": "bank", "initial_balance": "1000"}).json
        creada = ana.post("/api/v1/transactions/", {
            "account_id": cuenta["id"], "amount": "10", "type": "expense",
            "occurred_on": YESTERDAY.isoformat(), "description": "taxi",
        }).json

        [row] = outbox_rows(session)
        assert str(row.aggregate_id) == creada["id"]
        assert json.loads(row.message["payload"])["user_id"] == str(ana.user_id)
