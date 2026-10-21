"""Proyeccion de eventos al modelo de lectura, idempotencia y worker (ADR-15)."""
import json
from decimal import Decimal

import pytest
import redis
from sqlalchemy import func, select

from commands import EVENT_SOURCE_FACTORY_KEY
from domain.exceptions import InvalidEventError
from domain.interfaces import EventSourceUnavailable
from infra.event_deserialization import from_stream_fields
from infra.redis_source import RedisEventSource
from models import ProcessedEvent, TransactionFactRecord
from services import EventConsumer, EventProjector
from tests.streams import MemorySource, Transaction, event


def fact_row(session, tx):
    session.expire_all()
    return session.get(TransactionFactRecord, tx.transaction_id)


def count(session, model):
    return session.execute(select(func.count()).select_from(model)).scalar_one()


@pytest.fixture
def projector(session):
    return EventProjector(session)


class TestDeserializacion:
    def test_lee_el_contrato(self):
        tx = Transaction(description="Netflix")
        parsed = event(tx.added())
        assert parsed.payload.amount.amount == Decimal("120000.00")
        assert parsed.payload.description == "Netflix"
        assert parsed.event_type.value == "TransactionManuallyAdded"

    def test_un_evento_sin_descripcion_vale(self):
        fields = Transaction().added()
        payload = json.loads(fields["payload"])
        payload.pop("description")
        fields["payload"] = json.dumps(payload)
        assert event(fields).payload.description == ""

    @pytest.mark.parametrize("change", [
        {"version": "2"}, {"event_type": "Otro"}, {"payload": "no-json"}, {"occurred_at": "ayer"},
    ])
    def test_fuera_de_contrato(self, change):
        fields = Transaction().added()
        fields.update(change)
        with pytest.raises(InvalidEventError):
            from_stream_fields(fields)


class TestProyector:
    def test_manually_added_inserta(self, session, projector):
        tx = Transaction(description="Almuerzo")
        assert projector.project(event(tx.added()), "1-0") == "applied"

        row = fact_row(session, tx)
        assert (row.amount, row.currency, row.category_name, row.description) == (
            Decimal("120000.00"), "COP", "Alimentación", "Almuerzo",
        )
        assert row.deleted_at is None

    def test_categorized_actualiza_la_categoria(self, session, projector):
        tx = Transaction()
        projector.project(event(tx.added()), "1-0")
        projector.project(event(tx.categorized("Compras")), "2-0")

        row = fact_row(session, tx)
        assert (row.category_name, row.categorization_source) == ("Compras", "manual")

    def test_deleted_la_saca_de_todo_calculo(self, session, projector):
        tx = Transaction()
        projector.project(event(tx.added()), "1-0")
        projector.project(event(tx.deleted()), "2-0")
        assert fact_row(session, tx).deleted_at is not None

    def test_un_evento_repetido_no_se_aplica_dos_veces(self, session, projector):
        tx = Transaction()
        message = tx.added()
        assert projector.project(event(message), "1-0") == "applied"
        assert projector.project(event(message), "1-0") == "duplicate"
        assert count(session, ProcessedEvent) == 1

    def test_un_borrado_no_se_resucita(self, session, projector):
        tx = Transaction()
        added = tx.added(seconds=1)
        projector.project(event(tx.deleted(seconds=5)), "2-0")
        assert projector.project(event(added), "1-0") == "ignored"
        assert fact_row(session, tx).deleted_at is not None

    def test_un_evento_viejo_no_pisa_uno_nuevo(self, session, projector):
        tx = Transaction()
        old = tx.added(seconds=1)
        projector.project(event(tx.categorized("Compras", seconds=10)), "2-0")
        assert projector.project(event(old), "1-0") == "ignored"
        assert fact_row(session, tx).category_name == "Compras"

    def test_categorized_antes_que_added_crea_la_fila(self, session, projector):
        """El caso del backfill: el `added` llega despues, con la misma foto."""
        tx = Transaction()
        projector.project(event(tx.categorized("Compras")), "2-0")
        assert fact_row(session, tx).category_name == "Compras"

    def test_el_monto_viene_del_texto_decimal(self, session, projector):
        tx = Transaction(amount="0.10")
        projector.project(event(tx.added()), "1-0")
        assert fact_row(session, tx).amount == Decimal("0.10")


class TestConsumidor:
    def test_confirma_despues_de_aplicar(self, session):
        tx = Transaction()
        source = MemorySource([tx.added(), tx.categorized("Compras")])

        assert EventConsumer(source, EventProjector(session), from_stream_fields).poll() == 2
        assert source.acked == ["1-0", "2-0"] and source.pending == {}
        assert fact_row(session, tx).category_name == "Compras"

    def test_si_la_base_falla_no_confirma(self, session):
        class Broken(EventProjector):
            def project(self, event, stream_id):
                raise RuntimeError("base caida")

        source = MemorySource([Transaction().added()])
        with pytest.raises(RuntimeError):
            EventConsumer(source, Broken(session), from_stream_fields).poll()
        assert source.acked == [] and list(source.pending) == ["1-0"]

    def test_recupera_los_pendientes(self, session):
        tx = Transaction()
        source = MemorySource()
        source.pending = {"7-0": tx.added()}

        assert EventConsumer(source, EventProjector(session), from_stream_fields).recover() == 1
        assert source.acked == ["7-0"]
        assert fact_row(session, tx) is not None

    def test_un_mensaje_fuera_de_contrato_se_descarta_y_no_bloquea(self, session):
        good = Transaction()
        source = MemorySource([{"event_id": "x"}, good.added()])

        EventConsumer(source, EventProjector(session), from_stream_fields).poll()
        assert source.acked == ["1-0", "2-0"]
        assert fact_row(session, good) is not None

    def test_reprocesar_todo_no_duplica(self, session):
        tx = Transaction(amount="100.00")
        messages = [tx.added(), tx.categorized("Compras")]
        EventConsumer(MemorySource(messages), EventProjector(session), from_stream_fields).poll()
        EventConsumer(MemorySource(messages), EventProjector(session), from_stream_fields).poll()

        assert count(session, TransactionFactRecord) == 1
        assert count(session, ProcessedEvent) == 2
        assert fact_row(session, tx).amount == Decimal("100.00")


class TestComando:
    def test_once_procesa_y_termina(self, app, session):
        tx = Transaction()
        source = MemorySource([tx.added()])
        app.extensions[EVENT_SOURCE_FACTORY_KEY] = lambda: source

        result = app.test_cli_runner().invoke(args=["consume-events", "--once"])

        assert result.exit_code == 0
        assert "1 evento(s) procesados" in result.output
        assert fact_row(session, tx) is not None

    def test_con_redis_caido_no_termina_con_error(self, app):
        source = MemorySource()
        source.down = True
        app.extensions[EVENT_SOURCE_FACTORY_KEY] = lambda: source

        result = app.test_cli_runner().invoke(args=["consume-events", "--once"])

        assert result.exit_code == 0
        assert "reintento en" in result.output


class TestRedisEventSource:
    class Client:
        def __init__(self):
            self.calls = []

        def xgroup_create(self, *args, **kwargs):
            self.calls.append(("xgroup_create", args, kwargs))
            raise redis.exceptions.ResponseError("BUSYGROUP Consumer Group name already exists")

        def xautoclaim(self, *args, **kwargs):
            self.calls.append(("xautoclaim", args, kwargs))
            return ["0-0", [("5-0", {"a": "b"}), ("6-0", None)], []]

        def xreadgroup(self, *args, **kwargs):
            self.calls.append(("xreadgroup", args, kwargs))
            return [["finty.finance.events", [("7-0", {"c": "d"})]]]

        def xack(self, *args):
            self.calls.append(("xack", args, {}))

    def test_grupo_desde_el_inicio_y_ya_existente(self):
        client = self.Client()
        RedisEventSource(client, consumer="w1").ensure_group()
        name, args, kwargs = client.calls[0]
        assert args == ("finty.finance.events", "analytics") and kwargs == {"id": "0", "mkstream": True}

    def test_claim_ignora_entradas_borradas(self):
        assert RedisEventSource(self.Client(), consumer="w1").claim_pending() == [("5-0", {"a": "b"})]

    def test_read_new_lee_solo_nuevos(self):
        client = self.Client()
        assert RedisEventSource(client, consumer="w1").read_new() == [("7-0", {"c": "d"})]
        assert client.calls[-1][1][2] == {"finty.finance.events": ">"}

    def test_redis_inexistente_es_unavailable(self):
        with pytest.raises(EventSourceUnavailable):
            RedisEventSource.from_url("redis://127.0.0.1:9/0", consumer="w1").ensure_group()
