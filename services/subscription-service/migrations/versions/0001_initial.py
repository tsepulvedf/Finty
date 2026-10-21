"""Suscripciones y pagos de finty_subscription (E2-M6a).

Revision ID: 0001
Revises:
Create Date: 2026-10-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "subscription",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("canceled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING_PAYMENT', 'ACTIVE', 'CANCELED', 'EXPIRED')", name="ck_subscription_status"
        ),
        sa.CheckConstraint("plan IN ('PREMIUM')", name="ck_subscription_plan_paid"),
        sa.CheckConstraint(
            "status = 'PENDING_PAYMENT' OR current_period_end > current_period_start",
            name="ck_subscription_period",
        ),
    )
    op.create_index("ix_subscription_user_id", "subscription", ["user_id"])
    # Una sola suscripcion vigente por usuario (invariante implicita de DDD Stage 1).
    op.create_index(
        "uq_subscription_one_current_per_user",
        "subscription",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING_PAYMENT', 'ACTIVE', 'CANCELED')"),
    )
    op.create_table(
        "payment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), sa.ForeignKey("subscription.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount_in_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reference", sa.String(64), nullable=False, unique=True),
        sa.Column("gateway", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'DECLINED', 'ERROR')", name="ck_payment_status"),
        sa.CheckConstraint("amount_in_cents > 0", name="ck_payment_amount_positive"),
    )
    op.create_index("ix_payment_subscription_created", "payment", ["subscription_id", "created_at"])


def downgrade():
    op.drop_index("ix_payment_subscription_created", table_name="payment")
    op.drop_table("payment")
    op.drop_index("uq_subscription_one_current_per_user", table_name="subscription")
    op.drop_index("ix_subscription_user_id", table_name="subscription")
    op.drop_table("subscription")
