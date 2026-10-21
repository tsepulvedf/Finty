"""Outbox transaccional de eventos de dominio (ADR-15, E2-M4a).

`outbox_event` guarda cada evento en la misma transaccion que el cambio de
negocio; el relay lo publica despues en el stream de Redis.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outbox_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stream_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_outbox_pending", "outbox_event", ["id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index("ix_outbox_aggregate", "outbox_event", ["aggregate_id"])
    op.create_index(
        "uq_outbox_manually_added_once", "outbox_event", ["aggregate_id"], unique=True,
        postgresql_where=sa.text("event_type = 'TransactionManuallyAdded'"),
    )


def downgrade():
    op.drop_table("outbox_event")
