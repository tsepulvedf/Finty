"""Contrato entre las reglas de categorizacion y el catalogo sembrado.

Port de `finance/tests/test_categorizer_catalog_contract.py`: la migracion
`0002_seed_categories` de Alembic debe sembrar exactamente los nombres que
`RuleBasedCategorizer` puede emitir, con su `applies_to` correcto (D-16).
"""
import pytest
from sqlalchemy import func, select

from domain.shared.value_objects import Money
from domain.value_objects import TransactionType
from infra.categorizers import (
    ALL_CATEGORY_NAMES,
    EXPENSE_KEYWORDS,
    FALLBACK_BY_TYPE,
    FALLBACK_EXPENSE_CATEGORY,
    FALLBACK_INCOME_CATEGORY,
    INCOME_KEYWORDS,
    KEYWORDS_BY_TYPE,
    AICategorizer,
    RuleBasedCategorizer,
)
from models import Category


def emitible_names():
    """Todos los nombres que `RuleBasedCategorizer` puede llegar a devolver."""
    return sorted(
        set(EXPENSE_KEYWORDS)
        | set(INCOME_KEYWORDS)
        | {FALLBACK_EXPENSE_CATEGORY, FALLBACK_INCOME_CATEGORY}
    )


def nombres_en_base(session):
    return set(session.execute(select(Category.name)).scalars())


def aplica_a(session, name):
    return session.execute(
        select(Category.applies_to).where(Category.name == name)
    ).scalar_one()


class TestNombresEmitiblesExistenEnBase:
    @pytest.mark.parametrize("name", emitible_names())
    def test_la_categoria_existe(self, session, name):
        assert name in nombres_en_base(session)

    def test_no_sobra_ninguna_categoria_en_base(self, session):
        assert nombres_en_base(session) == set(emitible_names())

    def test_tiene_quince_nombres(self, session):
        total = session.execute(select(func.count()).select_from(Category)).scalar_one()
        assert len(ALL_CATEGORY_NAMES) == total == 15


class TestCoherenciaDeTipo:
    @pytest.mark.parametrize("name", sorted(EXPENSE_KEYWORDS))
    def test_las_categorias_de_gasto_aplican_a_gasto(self, session, name):
        assert aplica_a(session, name) == TransactionType.EXPENSE.value

    @pytest.mark.parametrize("name", sorted(INCOME_KEYWORDS))
    def test_las_categorias_de_ingreso_aplican_a_ingreso(self, session, name):
        assert aplica_a(session, name) == TransactionType.INCOME.value

    def test_los_respaldos_aplican_a_su_tipo(self, session):
        assert aplica_a(session, FALLBACK_EXPENSE_CATEGORY) == "expense"
        assert aplica_a(session, FALLBACK_INCOME_CATEGORY) == "income"


class TestAllowedCategoriesCoincideConLaBase:
    def test_coincide_exactamente(self, session):
        assert AICategorizer().allowed_categories == nombres_en_base(session)

    def test_el_mapa_de_respaldo_cubre_los_dos_tipos(self):
        assert set(FALLBACK_BY_TYPE) == set(TransactionType)
        assert set(KEYWORDS_BY_TYPE) == set(TransactionType)


class TestSalidaRealDelCategorizador:
    DESCRIPCIONES = [
        ("almuerzo en el restaurante", TransactionType.EXPENSE),
        ("taxi al centro", TransactionType.EXPENSE),
        ("pago del arriendo", TransactionType.EXPENSE),
        ("algo sin regla que aplique", TransactionType.EXPENSE),
        ("pago de nomina", TransactionType.INCOME),
        ("algo sin regla que aplique", TransactionType.INCOME),
    ]

    @pytest.mark.parametrize("description,transaction_type", DESCRIPCIONES)
    def test_la_sugerencia_se_resuelve_contra_la_tabla(
        self, session, description, transaction_type
    ):
        suggestion = RuleBasedCategorizer().categorize(
            description, Money("1000", "COP"), transaction_type
        )
        assert aplica_a(session, suggestion.category_name) == transaction_type.value


class TestMigraciones:
    def test_la_siembra_es_idempotente(self, engine, database_url):
        """Reaplicar la 0002 no duplica el catalogo (`ON CONFLICT DO NOTHING`)."""
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine

        from tests.conftest import SERVICE_ROOT

        config = Config(str(SERVICE_ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            database_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        config.attributes["configure_logger"] = False

        command.downgrade(config, "0001")
        command.upgrade(config, "head")
        command.upgrade(config, "head")

        engine = create_engine(database_url)
        with engine.connect() as connection:
            total = connection.execute(
                select(func.count()).select_from(Category)
            ).scalar_one()
        engine.dispose()
        assert total == 15
