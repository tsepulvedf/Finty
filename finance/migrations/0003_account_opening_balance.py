"""Agrega el saldo de apertura a `Account` y despeja su valor en los datos existentes.

Corrige la formulacion de INV-07 (C-17): la invariante real es
`balance = opening_balance + suma de movimientos`, no `balance = suma de
movimientos`. Sin esta columna, `recompute_balance` recalculaba desde cero y una
cuenta abierta con saldo inicial lo perdia al repararse.

Se descarto modelar la apertura como una transaccion inicial: exigiria una
categoria de apertura que aplicara a ingresos y a gastos a la vez, y
`Category.applies_to` admite un solo valor; ademas habria que blindar esa fila
contra borrado y recategorizacion. La columna es explicita y no altera el modelo
de transacciones.
"""
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models

# Los tipos se escriben como literales y no se importan de
# `finance.domain.value_objects`. Una migracion es un artefacto historico: debe
# seguir aplicando igual dentro de un ano aunque el enum del dominio cambie de
# forma, de nombre o de ubicacion.
INCOME = "income"
EXPENSE = "expense"

SIGN_BY_TYPE = {INCOME: 1, EXPENSE: -1}


def backfill_opening_balance(apps, schema_editor):
    """Despeja el termino independiente de INV-07 en las cuentas existentes.

    `opening_balance = balance - suma(amount * signo del tipo)`.

    En una base recien creada no hace nada. En una con datos deja la invariante
    consistente, en vez de asumir que toda cuenta abrio en cero y desplazar el
    saldo de apertura al conjunto de movimientos.
    """
    Account = apps.get_model("finance", "Account")

    for account in Account.objects.all().iterator():
        movements_total = Decimal("0.00")
        for amount, transaction_type in account.transactions.values_list(
            "amount", "type"
        ):
            movements_total += amount * SIGN_BY_TYPE[transaction_type]

        opening = account.balance - movements_total
        if opening != account.opening_balance:
            Account.objects.filter(pk=account.pk).update(opening_balance=opening)


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0002_seed_categories"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="opening_balance",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=14
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.CheckConstraint(
                condition=models.Q(("type", "credit"), ("opening_balance__gte", 0), _connector="OR"),
                name="ck_account_opening_balance_sign",
            ),
        ),
        # La inversa es `noop`: al revertir se elimina la columna entera, asi que
        # no queda nada que deshacer.
        migrations.RunPython(backfill_opening_balance, migrations.RunPython.noop),
    ]
