"""La base defiende las invariantes aunque se evada la capa de servicios.

Defensa en profundidad (ARCHITECTURE.md 7): la fuente autoritativa es el dominio,
pero estas constraints son la red de seguridad ante escrituras directas. Cada
test inserta por SQL, sin pasar por `services.py`, y espera el rechazo de
PostgreSQL. Ademas verifica la diferencia deliberada con el monolito:
`user_id` sin FK e indexado (ADR-10).
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError

from models import Account, Category, Transaction


@pytest.fixture
def categoria(session):
    return session.execute(
        select(Category).where(Category.name == "Alimentación")
    ).scalar_one()


@pytest.fixture
def cuenta(session):
    account = Account(user_id=uuid4(), name="Banco", type="bank", currency="COP")
    session.add(account)
    session.flush()
    return account


def _rechaza(session, constraint, *rows):
    """Inserta las filas y exige que la base las rechace por `constraint`."""
    with pytest.raises(IntegrityError) as error:
        with session.begin_nested():
            session.add_all(rows)
            session.flush()
    assert constraint in str(error.value)


def _transaccion(cuenta, **campos):
    valores = {
        "account_id": cuenta.id,
        "amount": Decimal("10.00"),
        "type": "expense",
        "occurred_on": date(2026, 1, 1),
    }
    valores.update(campos)
    return Transaction(**valores)


class TestTransaccion:
    def test_inv_02_la_cuenta_debe_existir(self, session):
        huerfana = Transaction(
            account_id=uuid4(),
            amount=Decimal("10.00"),
            type="expense",
            occurred_on=date(2026, 1, 1),
        )
        _rechaza(session, "finance_transaction_account_id_fkey", huerfana)

    def test_inv_04_monto_cero(self, session, cuenta):
        _rechaza(
            session,
            "ck_transaction_amount_not_zero",
            _transaccion(cuenta, amount=Decimal("0.00")),
        )

    def test_inv_09_tipo_invalido(self, session, cuenta):
        _rechaza(
            session, "ck_transaction_type_valid", _transaccion(cuenta, type="transfer")
        )

    @pytest.mark.parametrize("confianza", [-0.1, 1.01])
    def test_confianza_fuera_de_rango(self, session, cuenta, confianza):
        _rechaza(
            session,
            "ck_transaction_confidence_range",
            _transaccion(cuenta, categorization_confidence=confianza),
        )

    def test_la_categoria_debe_existir(self, session, cuenta):
        _rechaza(
            session,
            "finance_transaction_category_id_fkey",
            _transaccion(cuenta, category_id=uuid4()),
        )


class TestCuenta:
    def test_inv_13_no_se_borra_una_cuenta_con_transacciones(self, session, cuenta):
        session.add(_transaccion(cuenta))
        session.flush()

        with pytest.raises(IntegrityError) as error:
            with session.begin_nested():
                session.execute(delete(Account).where(Account.id == cuenta.id))
        assert "finance_transaction_account_id_fkey" in str(error.value)

    def test_una_categoria_en_uso_tampoco_se_borra(self, session, cuenta, categoria):
        session.add(_transaccion(cuenta, category_id=categoria.id))
        session.flush()

        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(delete(Category).where(Category.id == categoria.id))

    def test_nombre_unico_por_usuario(self, session, cuenta):
        _rechaza(
            session,
            "uniq_account_name_per_user",
            Account(user_id=cuenta.user_id, name="Banco", type="cash"),
        )

    def test_el_mismo_nombre_para_otro_usuario_es_valido(self, session, cuenta):
        session.add(Account(user_id=uuid4(), name="Banco", type="cash"))
        session.flush()

    def test_tipo_invalido(self, session):
        _rechaza(
            session,
            "ck_account_type_valid",
            Account(user_id=uuid4(), name="Rara", type="crypto"),
        )

    def test_moneda_de_tres_letras(self, session):
        _rechaza(
            session,
            "ck_account_currency_length",
            Account(user_id=uuid4(), name="Rara", type="bank", currency="CO"),
        )

    def test_inv_14_solo_credito_abre_en_negativo(self, session):
        _rechaza(
            session,
            "ck_account_opening_balance_sign",
            Account(
                user_id=uuid4(),
                name="Efectivo",
                type="cash",
                opening_balance=Decimal("-1.00"),
            ),
        )

    def test_credito_si_abre_en_negativo(self, session):
        session.add(
            Account(
                user_id=uuid4(),
                name="Tarjeta",
                type="credit",
                opening_balance=Decimal("-1.00"),
                balance=Decimal("-1.00"),
            )
        )
        session.flush()


class TestUserIdSinFk:
    """ADR-10: el usuario vive en `finty_identity`; aqui solo hay un UUID."""

    def test_user_id_no_tiene_fk(self, session):
        fks = inspect(session.connection()).get_foreign_keys("finance_account")
        assert all("user_id" not in fk["constrained_columns"] for fk in fks)

    def test_user_id_esta_indexado(self, session):
        indices = inspect(session.connection()).get_indexes("finance_account")
        assert any(index["column_names"] == ["user_id"] for index in indices)

    def test_acepta_cualquier_uuid_de_usuario(self, session):
        """No hay tabla de usuarios que consultar: cualquier UUID es aceptado."""
        session.add(Account(user_id=uuid4(), name="Nueva", type="bank"))
        session.flush()
