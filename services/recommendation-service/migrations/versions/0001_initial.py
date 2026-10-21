"""Perfil de riesgo y planes de inversion de finty_recommendation (E2-M5).

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

ANSWERS = ("investment_horizon", "loss_reaction", "experience", "income_stability", "goal")


def upgrade():
    op.create_table(
        "risk_profile",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        *[sa.Column(name, sa.SmallInteger(), nullable=False) for name in ANSWERS],
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *[sa.CheckConstraint(f"{name} BETWEEN 1 AND 3", name=f"ck_risk_profile_{name}") for name in ANSWERS],
    )
    op.create_table(
        "investment_plan",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("instrument_type", sa.String(40), nullable=False),
        sa.Column("risk_profile_type", sa.String(20), nullable=False),
        sa.Column("monthly_contribution", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("monthly_contribution > 0", name="ck_plan_contribution_positive"),
        sa.CheckConstraint("horizon_months > 0", name="ck_plan_horizon_positive"),
        sa.CheckConstraint(
            "risk_profile_type IN ('conservative', 'moderate', 'aggressive')",
            name="ck_plan_profile_type",
        ),
        sa.CheckConstraint(
            "instrument_type IN ('cdt', 'liquidity_fund', 'collective_investment_fund', 'etf', 'stocks')",
            name="ck_plan_instrument_type",
        ),
    )
    op.create_index("ix_plan_user_created", "investment_plan", ["user_id", "created_at"])


def downgrade():
    op.drop_index("ix_plan_user_created", table_name="investment_plan")
    op.drop_table("investment_plan")
    op.drop_table("risk_profile")
