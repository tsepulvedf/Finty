"""Siembra el catalogo inicial de categorias.

Equivalente de `finance/migrations/0002_seed_categories.py` del monolito: los
mismos quince nombres, con el mismo `applies_to` (D-16). Es la unica fila de
datos con la que nace `finty_finance`.

`SEEDED_CATEGORIES` es el contrato con `RuleBasedCategorizer`: solo puede devolver
nombres que existan aqui. Lo verifica `tests/persistence/test_catalog_contract.py`.

Idempotente: `ON CONFLICT (name) DO NOTHING` permite reaplicarla sin duplicar.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20
"""
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

FALLBACK_EXPENSE_CATEGORY = "Otros gastos"
FALLBACK_INCOME_CATEGORY = "Otros ingresos"

SEEDED_CATEGORIES = [
    ("Alimentación", "expense"),
    ("Transporte", "expense"),
    ("Vivienda", "expense"),
    ("Servicios públicos", "expense"),
    ("Salud", "expense"),
    ("Educación", "expense"),
    ("Entretenimiento", "expense"),
    ("Compras", "expense"),
    ("Deudas y créditos", "expense"),
    (FALLBACK_EXPENSE_CATEGORY, "expense"),
    ("Salario", "income"),
    ("Freelance", "income"),
    ("Inversiones", "income"),
    ("Reembolsos", "income"),
    (FALLBACK_INCOME_CATEGORY, "income"),
]

# Vista minima de las tablas, congelada en esta revision.
category = sa.table(
    "finance_category",
    sa.column("id", sa.Uuid()),
    sa.column("name", sa.String()),
    sa.column("applies_to", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
movement = sa.table(
    "finance_transaction",
    sa.column("category_id", sa.Uuid()),
)


def upgrade():
    now = datetime.now(timezone.utc)
    rows = [
        {"id": uuid4(), "name": name, "applies_to": applies_to, "created_at": now}
        for name, applies_to in SEEDED_CATEGORIES
    ]
    op.execute(insert(category).values(rows).on_conflict_do_nothing(index_elements=["name"]))


def downgrade():
    """Elimina las categorias sembradas y solo esas. Falla si alguna esta en uso."""
    seeded_names = [name for name, _ in SEEDED_CATEGORIES]
    connection = op.get_bind()
    in_use = connection.execute(
        sa.select(category.c.name)
        .distinct()
        .select_from(category.join(movement, movement.c.category_id == category.c.id))
        .where(category.c.name.in_(seeded_names))
        .order_by(category.c.name)
    ).scalars().all()
    if in_use:
        raise RuntimeError(
            "No se puede revertir la siembra del catalogo: las categorias "
            f"{', '.join(in_use)} tienen transacciones asociadas. Reasignalas o "
            "eliminalas antes de revertir esta migracion."
        )
    op.execute(category.delete().where(category.c.name.in_(seeded_names)))
