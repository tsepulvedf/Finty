"""Reportes mensuales (E2-M7).

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
        "monthly_report",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("media_type", sa.String(60), nullable=True),
        sa.Column("filename", sa.String(80), nullable=True),
        sa.Column("failure", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('PENDING', 'READY', 'FAILED')", name="ck_report_status"),
        sa.CheckConstraint("language IN ('es', 'en')", name="ck_report_language"),
        sa.CheckConstraint("status <> 'READY' OR content IS NOT NULL", name="ck_report_ready_has_content"),
    )
    op.create_index("ix_report_user_created", "monthly_report", ["user_id", "created_at"])
    op.create_index("ix_report_status_created", "monthly_report", ["status", "created_at"])


def downgrade():
    op.drop_index("ix_report_status_created", table_name="monthly_report")
    op.drop_index("ix_report_user_created", table_name="monthly_report")
    op.drop_table("monthly_report")
