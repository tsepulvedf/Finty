"""Consulta diferida para listados paginados (anillo externo).

Cumple el papel del `QuerySet` perezoso de Django en el monolito: el servicio
decide **que** filas (filtros, propiedad, orden) y devuelve un `Listing`; la capa
HTTP decide **cuantas** (pagina) sin escribir SQL ni conocer la sesion.
"""
from sqlalchemy import func, select


class Listing:
    """Sentencia `SELECT` ya filtrada y ordenada, pendiente de ejecutar."""

    def __init__(self, session, statement):
        self._session = session
        self._statement = statement

    def count(self):
        """Numero total de filas del listado."""
        counted = select(func.count()).select_from(
            self._statement.order_by(None).subquery()
        )
        return self._session.execute(counted).scalar_one()

    def fetch(self, offset, limit):
        """Filas de una ventana del listado, en el orden del servicio."""
        window = self._statement.offset(offset).limit(limit)
        return list(self._session.execute(window).unique().scalars())
