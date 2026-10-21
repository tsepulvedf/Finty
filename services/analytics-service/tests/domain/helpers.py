"""Constructores de hechos para los tests de dominio."""
from datetime import date
from uuid import uuid4

from domain.facts import TransactionFact
from domain.shared.value_objects import Money

ACCOUNT = uuid4()


def fact(amount, kind="expense", category="Alimentación", on=date(2026, 10, 10),
         currency="COP", description="", account=ACCOUNT):
    return TransactionFact(
        transaction_id=uuid4(),
        account_id=account,
        amount=Money(amount, currency),
        transaction_type=kind,
        category_name=category,
        description=description,
        occurred_on=on,
    )
