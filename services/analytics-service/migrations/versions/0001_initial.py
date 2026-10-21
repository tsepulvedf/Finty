"""Modelo de lectura de finty_analytics (E2-M4b).

`transaction_fact` guarda el ultimo estado de cada transaccion segun los eventos
de finance-service; `processed_event`, los eventos ya aplicados.

Revision ID: 0001
Revises:
Create Date: 2026-10-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transaction_fact",
        sa.Column("transaction_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("transaction_type", sa.String(10), nullable=False),
        sa.Column("category_name", sa.String(80), nullable=True),
        sa.Column("categorization_source", sa.String(10), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("transaction_type IN ('income', 'expense')", name="ck_fact_type_valid"),
        sa.CheckConstraint("char_length(currency) = 3", name="ck_fact_currency_length"),
    )
    op.create_index("ix_fact_user_date", "transaction_fact", ["user_id", "occurred_on"])
    op.create_index("ix_fact_date", "transaction_fact", ["occurred_on"])

    op.create_table(
        "processed_event",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("stream_id", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("processed_event")
    op.drop_table("transaction_fact")
