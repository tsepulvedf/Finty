"""Worker de eventos: `flask consume-events` (contenedor analytics-worker).

Lee `finty.finance.events` con el grupo `analytics` y aplica cada evento al
modelo de lectura (ADR-15):

1. Al arrancar crea el grupo si no existe, desde el inicio del stream, para
   recibir la historia completa.
2. Recupera los pendientes sin confirmar (`XAUTOCLAIM`) que dejo un worker
   anterior.
3. Lee mensajes nuevos (`XREADGROUP`), los aplica y hace `XACK` solo despues del
   commit en la base.

Si Redis o la base no responden, espera de 1 a 30 s y reintenta; no termina con
error. Los mensajes no confirmados no se pierden: siguen pendientes en el grupo.
"""
import time

import click
from flask import current_app
from flask.cli import with_appcontext

from api.context import db_session
from infra.backoff import Backoff
from infra.event_deserialization import from_stream_fields
from infra.redis_source import RedisEventSource
from services import EventConsumer, EventProjector

# Los tests reemplazan el origen de Redis por uno en memoria con esta clave.
EVENT_SOURCE_FACTORY_KEY = "finty.event_source_factory"


def _event_source():
    factory = current_app.extensions.get(EVENT_SOURCE_FACTORY_KEY)
    if factory is not None:
        return factory()
    return RedisEventSource.from_url(current_app.config["REDIS_URL"])


@click.command("consume-events")
@click.option("--once", is_flag=True, help="Recupera pendientes, lee una vez y termina (tests).")
@with_appcontext
def consume_events(once):
    """Aplica los eventos de finance-service al modelo de lectura de analytics."""
    source = _event_source()
    consumer = EventConsumer(source, EventProjector(db_session()), from_stream_fields)
    backoff = Backoff()
    recovered = False
    while True:
        try:
            if not recovered:
                source.ensure_group()
                count = consumer.recover()
                recovered = True
                click.echo(f"consume-events: {count} pendiente(s) recuperados")
            count = consumer.poll()
        except Exception as exc:  # noqa: BLE001 — el worker no debe morir por un fallo transitorio
            db_session().rollback()
            delay = backoff.next_delay()
            click.echo(
                f"consume-events: fallo ({type(exc).__name__}: {exc}); reintento en {delay:.0f} s",
                err=True,
            )
            if once:
                return
            time.sleep(delay)
            # Tras un fallo puede haber mensajes leidos y no confirmados.
            recovered = False
            continue

        backoff.reset()
        if count:
            click.echo(f"consume-events: {count} evento(s) procesados")
        if once:
            return
