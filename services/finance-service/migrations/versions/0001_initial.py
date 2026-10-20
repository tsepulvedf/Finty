"""Esquema inicial de finty_finance.

Equivale al estado final de las migraciones 0001 a 0004 del monolito, con una
diferencia deliberada: `finance_account.user_id` es un UUID **sin FK** (ADR-10),
porque los usuarios viven en otra base.

Los valores de los `CHECK` se escriben como literales y no se importan del
dominio: una migracion es un artefacto historico y debe aplicar igual aunque los
enums cambien de forma o de lugar.

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
        "finance_category",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("applies_to", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "applies_to IN ('income', 'expense')", name="ck_category_applies_to_valid"
        ),
    )

    op.create_table(
        "finance_account",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("opening_balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uniq_account_name_per_user"),
        sa.CheckConstraint(
            "type IN ('cash', 'bank', 'credit')", name="ck_account_type_valid"
        ),
        sa.CheckConstraint(
            "char_length(currency) = 3", name="ck_account_currency_length"
        ),
        sa.CheckConstraint(
            "type = 'credit' OR opening_balance >= 0",
            name="ck_account_opening_balance_sign",
        ),
    )
    op.create_index("ix_account_user", "finance_account", ["user_id"])

    op.create_table(
        "finance_transaction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("finance_account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column(
            "category_id",
            sa.Uuid(),
            sa.ForeignKey("finance_category.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("categorization_source", sa.String(10), nullable=True),
        sa.Column("categorization_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount <> 0", name="ck_transaction_amount_not_zero"),
        sa.CheckConstraint(
            "type IN ('income', 'expense')", name="ck_transaction_type_valid"
        ),
        sa.CheckConstraint(
            "categorization_confidence IS NULL OR ("
            "categorization_confidence >= 0.0 AND categorization_confidence <= 1.0)",
            name="ck_transaction_confidence_range",
        ),
    )
    op.create_index(
        "ix_transaction_account_date",
        "finance_transaction",
        ["account_id", sa.text("occurred_on DESC")],
    )
    op.create_index(
        "ix_transaction_category", "finance_transaction", ["account_id", "category_id"]
    )


def downgrade():
    op.drop_table("finance_transaction")
    op.drop_table("finance_account")
    op.drop_table("finance_category")
