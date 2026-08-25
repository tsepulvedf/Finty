"""Siembra el catalogo inicial de categorias.

En la Entrega 1 las categorias son globales y de solo lectura: las gobierna esta
migracion, no el admin ni los usuarios (decision D-01 de ARCHITECTURE.md 13).

`SEEDED_CATEGORIES` es el **contrato con M4**: `RuleBasedCategorizer` solo puede
devolver nombres que existan en esta lista, porque `TransactionService` los
resolvera contra la tabla. Agregar una regla nueva en M4 sin agregar aqui su
categoria produciria un `CategoryNotFoundError` en tiempo de ejecucion.
"""
from django.db import migrations

# Categorias de respaldo que usara `RuleBasedCategorizer` (M4) cuando ninguna
# regla haga match. Deben existir siempre.
FALLBACK_EXPENSE_CATEGORY = "Otros gastos"
FALLBACK_INCOME_CATEGORY = "Otros ingresos"

# Los nombres van en espanol y con tildes: son datos que ve el usuario final, no
# identificadores de codigo.
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


def seed_categories(apps, schema_editor):
    """Crea las categorias del catalogo.

    Idempotente: `get_or_create` por `name` permite reaplicar la migracion sobre
    una base que ya las tenga sin duplicar nada.
    """
    Category = apps.get_model("finance", "Category")
    for name, applies_to in SEEDED_CATEGORIES:
        Category.objects.get_or_create(
            name=name, defaults={"applies_to": applies_to}
        )


def unseed_categories(apps, schema_editor):
    """Elimina las categorias sembradas y solo esas.

    Falla si alguna esta en uso. El `on_delete=PROTECT` de `Transaction.category`
    ya lo impediria, pero un `ProtectedError` crudo no explica que revertir esta
    migracion sobre datos reales es una perdida de informacion.
    """
    Category = apps.get_model("finance", "Category")
    seeded_names = [name for name, _ in SEEDED_CATEGORIES]

    in_use = (
        Category.objects.filter(name__in=seeded_names, transactions__isnull=False)
        .values_list("name", flat=True)
        .distinct()
    )
    in_use = sorted(in_use)
    if in_use:
        raise RuntimeError(
            "No se puede revertir la siembra del catalogo: las categorias "
            f"{', '.join(in_use)} tienen transacciones asociadas. Reasignalas o "
            "eliminalas antes de revertir esta migracion."
        )

    Category.objects.filter(name__in=seeded_names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
