"""Conexion a `finty_recommendation` (anillo externo).

Un `Engine` por proceso y una `Session` por peticion. El servicio solo conoce la
URL de **su** base (A-21): la recibe en `DATABASE_URL` y no sabe nada de las
demas.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def build_engine(database_url):
    """Crea el engine de SQLAlchemy.

    `pool_pre_ping` descarta conexiones muertas del pool, por ejemplo tras un
    reinicio del contenedor de PostgreSQL, en lugar de fallar la peticion.
    """
    return create_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine):
    """Crea la fabrica de sesiones.

    `expire_on_commit=False`: tras confirmar, el servicio devuelve la fila recien
    escrita y el blueprint la serializa; expirarla obligaria a releerla de la base
    solo para responder.
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


def ping(session):
    """Comprueba que la base responde. Lo usa la sonda de salud."""
    session.execute(text("SELECT 1"))
