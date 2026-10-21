"""Persistencia de `recommendation-service` (anillo externo), en `finty_recommendation`.

Modelos anemicos (RULES.md, regla 2): columnas, constraints y `__repr__`.
`user_id` es un UUID sin FK: el usuario vive en `finty_identity` (ADR-10).
Las recomendaciones no se persisten: se calculan al leer (§6.6).
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Numeric, SmallInteger, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

PROFILE_TYPES = "'conservative', 'moderate', 'aggressive'"
INSTRUMENT_TYPES = "'cdt', 'liquidity_fund', 'collective_investment_fund', 'etf', 'stocks'"


def _utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarativa de los modelos del servicio."""


class RiskProfileRecord(Base):
    """Respuestas del cuestionario de un usuario. El tipo se deriva en el dominio."""

    __tablename__ = "risk_profile"
    __table_args__ = tuple(
        CheckConstraint(f"{column} BETWEEN 1 AND 3", name=f"ck_risk_profile_{column}")
        for column in ("investment_horizon", "loss_reaction", "experience", "income_stability", "goal")
    )

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    investment_horizon: Mapped[int] = mapped_column(SmallInteger)
    loss_reaction: Mapped[int] = mapped_column(SmallInteger)
    experience: Mapped[int] = mapped_column(SmallInteger)
    income_stability: Mapped[int] = mapped_column(SmallInteger)
    goal: Mapped[int] = mapped_column(SmallInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self):
        return f"<RiskProfileRecord user={self.user_id}>"


class InvestmentPlanRecord(Base):
    """Plan de inversion guardado por un usuario."""

    __tablename__ = "investment_plan"
    __table_args__ = (
        CheckConstraint("monthly_contribution > 0", name="ck_plan_contribution_positive"),
        CheckConstraint("horizon_months > 0", name="ck_plan_horizon_positive"),
        CheckConstraint(f"risk_profile_type IN ({PROFILE_TYPES})", name="ck_plan_profile_type"),
        CheckConstraint(f"instrument_type IN ({INSTRUMENT_TYPES})", name="ck_plan_instrument_type"),
        Index("ix_plan_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid)
    instrument_type: Mapped[str] = mapped_column(String(40))
    risk_profile_type: Mapped[str] = mapped_column(String(20))
    monthly_contribution: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    horizon_months: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self):
        return f"<InvestmentPlanRecord {self.id} {self.instrument_type}>"
