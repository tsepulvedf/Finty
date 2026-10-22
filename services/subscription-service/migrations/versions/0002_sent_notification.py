"""Avisos enviados por correo (E2-M7).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sent_notification",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), sa.ForeignKey("subscription.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recipient", sa.String(254), nullable=True),
        sa.Column("language", sa.String(2), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('premium_welcome', 'subscription_expiring')", name="ck_notification_kind"),
        sa.UniqueConstraint("user_id", "kind", "period_end", name="uq_notification_once_per_period"),
    )


def downgrade():
    op.drop_table("sent_notification")
