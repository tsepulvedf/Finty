"""Persistencia de `finance-service` (anillo externo), en `finty_finance`.

Modelos anemicos (RULES.md, regla 2): columnas, `__table_args__`, constraints,
relaciones y `__repr__`. Ningun metodo de negocio, ninguna `@hybrid_property`,
ningun listener de eventos del ORM. Las reglas viven en `domain/` y los casos de
uso en `services.py`.

Las tablas conservan los nombres y las constraints del monolito
(`finance_account`, `uniq_account_name_per_user`, ...). Asi una migracion futura
de datos (D-16) es una copia fila a fila, sin renombrar nada.

**Diferencia deliberada con el monolito:** `Account.user_id` es un UUID **sin
FK**. La tabla de usuarios vive en `finty_identity`, otra base, y una FK no puede
cruzar bases (ADR-10). El valor sale de la cabecera `X-User-Id` que pone el
Gateway.

Este modulo importa los enums de `domain/` para construir las constraints; la
dependencia va de afuera hacia adentro, que es la direccion correcta (ADR-02).
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from domain.value_objects import AccountType, TransactionType

CURRENCY_CODE_LENGTH = 3
DEFAULT_CURRENCY = "COP"

CONFIDENCE_FLOOR = 0.0
CONFIDENCE_CEILING = 1.0


def _sql_in(values):
    """Lista SQL de literales para un `CHECK ... IN (...)`."""
    return ", ".join(f"'{value}'" for value in values)


ACCOUNT_TYPE_SQL = _sql_in(member.value for member in AccountType)
TRANSACTION_TYPE_SQL = _sql_in(member.value for member in TransactionType)


def _utcnow():
    """Instante actual en UTC. Equivale a `auto_now_add` / `auto_now` de Django."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarativa de los modelos del servicio."""


class Category(Base):
    """Categoria de transaccion. Catalogo global de solo lectura (D-01).

    La siembra la migracion `0002_seed_categories`, igual que en el monolito.
    """

    __tablename__ = "finance_category"
    __table_args__ = (
        CheckConstraint(
            f"applies_to IN ({TRANSACTION_TYPE_SQL})",
            name="ck_category_applies_to_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    applies_to: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    def __repr__(self):
        return f"<Category {self.name}>"


class Account(Base):
    """Cuenta financiera de un usuario. Raiz del agregado (ARCHITECTURE.md 5.1).

    Toda escritura de transacciones ocurre bajo `with_for_update()` sobre esta
    fila (INV-07). `balance` es persistido y recalculado (D-02); quien lo calcula
    es `BalanceCalculator`, en el dominio.

    No declara la coleccion `transactions` a proposito: sin ella, borrar una
    cuenta emite un `DELETE` directo y es la FK `RESTRICT` la que lo rechaza si
    tiene transacciones (INV-13), en lugar de que el ORM intente anular la FK de
    los hijos.
    """

    __tablename__ = "finance_account"
    __table_args__ = (
        # Integridad de datos, no invariante de negocio: dos cuentas homonimas
        # del mismo usuario serian indistinguibles en el dashboard.
        UniqueConstraint("user_id", "name", name="uniq_account_name_per_user"),
        CheckConstraint(
            f"type IN ({ACCOUNT_TYPE_SQL})", name="ck_account_type_valid"
        ),
        CheckConstraint(
            f"char_length(currency) = {CURRENCY_CODE_LENGTH}",
            name="ck_account_currency_length",
        ),
        # INV-14 en el instante de creacion: solo una cuenta de credito abre en
        # negativo.
        CheckConstraint(
            f"type = '{AccountType.CREDIT.value}' OR opening_balance >= 0",
            name="ck_account_opening_balance_sign",
        ),
        # ADR-10: toda consulta filtra por usuario.
        Index("ix_account_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # Sin FK: el usuario vive en otra base (ADR-10).
    user_id: Mapped[UUID] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(10))
    # Inmutable tras la creacion: termino independiente de INV-07 (C-17).
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00")
    )
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(
        String(CURRENCY_CODE_LENGTH), default=DEFAULT_CURRENCY
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self):
        return f"<Account {self.name}>"


class Transaction(Base):
    """Movimiento financiero. Entidad dentro del agregado `Account`.

    `amount` se guarda siempre positivo; el signo lo aporta `type` en el dominio.
    INV-04 e INV-09 estan dos veces, en el dominio y como `CHECK`: defensa en
    profundidad ante escrituras que evadan la capa de servicios. INV-12 (fecha no
    futura) no tiene constraint: PostgreSQL no admite `CURRENT_DATE` en un CHECK.
    """

    __tablename__ = "finance_transaction"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_transaction_amount_not_zero"),
        CheckConstraint(
            f"type IN ({TRANSACTION_TYPE_SQL})", name="ck_transaction_type_valid"
        ),
        CheckConstraint(
            "categorization_confidence IS NULL OR ("
            f"categorization_confidence >= {CONFIDENCE_FLOOR} AND "
            f"categorization_confidence <= {CONFIDENCE_CEILING})",
            name="ck_transaction_confidence_range",
        ),
        Index("ix_transaction_account_date", "account_id", text("occurred_on DESC")),
        Index("ix_transaction_category", "account_id", "category_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # INV-02 (pertenece a una cuenta existente) e INV-13 (no se borra una cuenta
    # con transacciones): FK obligatoria con RESTRICT.
    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("finance_account.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    type: Mapped[str] = mapped_column(String(10))
    category_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("finance_category.id", ondelete="RESTRICT"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(255), default="")
    occurred_on: Mapped[date] = mapped_column(Date)
    categorization_source: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    # Medida estadistica, no dinero: `Float` y no `Numeric` (igual que el monolito).
    categorization_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Muchos-a-uno, cargadas en la misma consulta: la salida aplana
    # `account_name` y `category_name` sin una consulta por fila.
    account: Mapped[Account] = relationship(lazy="joined", innerjoin=True)
    category: Mapped[Category | None] = relationship(lazy="joined")

    def __repr__(self):
        return f"<Transaction {self.type} {self.amount} {self.occurred_on}>"


class OutboxEvent(Base):
    """Evento de dominio pendiente de publicar: el outbox transaccional (ADR-15).

    Se inserta en la misma transaccion que el cambio de negocio. El relay
    (`flask relay-outbox`) los lee en orden de `id`, los publica en el stream de
    Redis y llena `published_at`. `message` guarda el mensaje ya serializado tal
    como viaja (`infra/event_serialization.py`), asi el relay no reinterpreta nada.
    """

    __tablename__ = "outbox_event"
    __table_args__ = (
        # El relay solo mira los pendientes.
        Index("ix_outbox_pending", "id", postgresql_where=text("published_at IS NULL")),
        Index("ix_outbox_aggregate", "aggregate_id"),
        # Un solo `TransactionManuallyAdded` por transaccion: es lo que hace
        # idempotente a `flask outbox-backfill` incluso si corre dos veces a la vez.
        Index(
            "uq_outbox_manually_added_once",
            "aggregate_id",
            unique=True,
            postgresql_where=text("event_type = 'TransactionManuallyAdded'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    # Id de la entidad a la que se refiere el evento: hoy, la transaccion.
    aggregate_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    message: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Id que asigno Redis al publicarlo (por ejemplo `1729470000000-0`).
    stream_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self):
        return f"<OutboxEvent {self.id} {self.event_type}>"
