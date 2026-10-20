"""Casos de uso de `finance-service` (anillo de Servicios).

Port de `finance/services.py` del monolito. Los casos de uso, su orden y las
reglas que invocan son los mismos; cambian tres cosas del anillo externo:

- **La identidad es un `user_id`** (UUID resuelto por el Gateway en `X-User-Id`,
  ADR-09), no un objeto `User` de Django. Toda consulta filtra por el (INV-03).
- **La persistencia es una sesion SQLAlchemy** inyectada por constructor, sobre
  los modelos de `models.py`. `atomic()` hace el papel de `transaction.atomic()`
  y `with_for_update()` el de `select_for_update()`.
- **Los listados devuelven un `Listing`**, el equivalente del `QuerySet` perezoso:
  el servicio decide que filas y en que orden; la capa HTTP decide la pagina.

Que hace esta capa y que no: orquesta y traduce; no decide reglas. Las dos
verificaciones que hace y no el dominio son las mismas del monolito: INV-14 sobre
el balance bajo bloqueo y la resolucion de la categoria contra el catalogo.

**Inversion de dependencias.** `TransactionService` recibe un `Categorizer` por
constructor y depende solo de la ABC. Este modulo no importa ninguna
implementacion concreta ni la fabrica: quien elige es el blueprint.

Las excepciones de dominio suben sin capturarse; las traduce `api/errors.py`. Lo
que si se traduce aqui son las del ORM, que no deben escapar de esta capa.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.exc import IntegrityError

import messages
from domain.builders import AccountBuilder, TransactionBuilder
from domain.exceptions import (
    AccountHasTransactionsError,
    AccountNotFoundError,
    CategoryNotFoundError,
    CategoryTypeMismatchError,
    DuplicateAccountNameError,
    TransactionNotFoundError,
)
from domain.logic import BalanceCalculator, TransactionRules
from domain.shared.value_objects import Money
from domain.value_objects import (
    AccountSnapshot,
    CategorizationSource,
    TransactionType,
)
from infra.listing import Listing
from models import DEFAULT_CURRENCY, Account, Category, Transaction

MANUAL_CATEGORY_CONFIDENCE = 1.0

# Motivos por los que una transaccion queda en un estado de categorizacion
# incoherente. Constantes para que el comando de auditoria no compare literales.
MISSING_CATEGORY = "procedencia sin categoria"
MISSING_SOURCE = "categoria sin procedencia"

# Nombre de la constraint de unicidad de nombre por usuario. Se compara contra la
# violacion para no confundirla con cualquier otra.
UNIQUE_ACCOUNT_NAME_CONSTRAINT = "uniq_account_name_per_user"

# SQLSTATE de PostgreSQL al borrar una fila referenciada por una FK: `23001`
# (restrict_violation) con `ON DELETE RESTRICT`, que es lo que declara
# `finance_transaction.account_id` (INV-13); `23503` (foreign_key_violation) si
# la FK fuera `NO ACTION`. Se aceptan ambos.
REFERENCED_ROW_SQLSTATES = {"23001", "23503"}


@contextmanager
def atomic(session):
    """Confirma al salir del bloque; revierte ante cualquier excepcion.

    Es el `transaction.atomic()` del monolito: todo lo que ocurre dentro del
    bloque se confirma junto o no se confirma.
    """
    try:
        yield
        # Dentro del `try`: un fallo al confirmar (por ejemplo, una constraint
        # que salta en el flush) tambien deja la sesion revertida y reutilizable.
        session.commit()
    except BaseException:
        session.rollback()
        raise


def _as_uuid(value):
    """Convierte un identificador a `UUID`; `None` si no tiene forma valida.

    Un identificador mal formado es indistinguible de uno inexistente: quien lo
    usa responde igual en ambos casos, sin revelar que fallo el formato.
    """
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _violated_constraint(exc):
    """Nombre de la constraint violada en un `IntegrityError` de psycopg2."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def _sqlstate(exc):
    """SQLSTATE de un error de base de datos de psycopg2."""
    return getattr(exc.orig, "pgcode", None)


@dataclass(frozen=True)
class BalanceAuditResult:
    """Resultado de auditar el balance de una cuenta (INV-07).

    Estructura de **reporte**, no concepto del dominio: vive aqui y no en
    `domain/`. Identifica al propietario por `owner_id` y no por email: el email
    vive en `finty_identity` y este servicio no consulta otra base (ADR-10).
    """

    account_id: object
    account_name: str
    owner_id: object
    persisted: Money
    calculated: Money

    def is_consistent(self):
        """Indica si el balance persistido coincide con el recalculado.

        Metodo y no `@property`, por la misma razon que en el monolito: no invitar
        a replicar propiedades calculadas en los modelos.
        """
        return self.persisted == self.calculated

    def difference(self):
        """Cuanto se desvio el balance persistido del real."""
        return self.persisted.subtract(self.calculated)


@dataclass(frozen=True)
class CategorizationAuditResult:
    """Transaccion cuyo estado de categorizacion es incoherente (INV-08)."""

    transaction_id: object
    account_name: str
    owner_id: object
    reason: str
    category_name: str | None
    categorization_source: str | None


class CategoryService:
    """Lectura del catalogo global de categorias.

    En el monolito el `CategoryViewSet` leia `Category.objects.all()` sin servicio
    porque no hay reglas que orquestar. Aqui existe un servicio minimo para que
    ningun blueprint toque la sesion ni escriba consultas (RULES.md, regla 3).
    """

    def __init__(self, session):
        self._session = session

    def list_categories(self):
        """Catalogo completo, en el orden del monolito (`applies_to`, `name`)."""
        return Listing(
            self._session,
            select(Category).order_by(Category.applies_to, Category.name),
        )

    def find_category(self, category_id):
        """Una categoria por id, o `None` si no existe o el id no tiene forma."""
        pk = _as_uuid(category_id)
        if pk is None:
            return None
        return self._session.get(Category, pk)


class AccountService:
    """Casos de uso sobre cuentas."""

    def __init__(self, session):
        self._session = session

    def create_account(
        self, user_id, name, account_type, initial_balance=None, currency=None
    ):
        """Crea una cuenta para el usuario y devuelve la fila persistida.

        Toda la validacion de negocio ocurre en `AccountBuilder.build()`; este
        metodo solo traduce el draft a columnas. `initial_balance` acepta un
        `Money` o un valor suelto que se envuelve en la moneda de la cuenta.
        """
        account_currency = self._resolve_currency(currency, initial_balance)

        builder = (
            AccountBuilder()
            .for_user(user_id)
            .named(name)
            .of_type(account_type)
            .in_currency(account_currency)
        )
        if initial_balance is not None:
            builder.with_initial_balance(
                self._as_money(initial_balance, account_currency)
            )

        draft = builder.build()

        account = Account(
            user_id=user_id,
            name=draft.name,
            type=draft.account_type.value,
            # Saldo de apertura y saldo vivo arrancan iguales y solo coinciden en
            # este instante.
            opening_balance=draft.initial_balance.amount,
            balance=draft.initial_balance.amount,
            currency=draft.initial_balance.currency,
        )
        try:
            with atomic(self._session):
                self._session.add(account)
        except IntegrityError as exc:
            if _violated_constraint(exc) == UNIQUE_ACCOUNT_NAME_CONSTRAINT:
                raise DuplicateAccountNameError(
                    messages.DUPLICATE_ACCOUNT_NAME.format(name=draft.name)
                ) from exc
            raise
        return account

    def get_owned_account(self, user_id, account_id):
        """Devuelve una cuenta del usuario o lanza `AccountNotFoundError`.

        La consulta va filtrada por usuario: una cuenta ajena y una inexistente
        son indistinguibles desde fuera (D-08).
        """
        return self._fetch_account(user_id, account_id, lock=False)

    def get_locked_account(self, user_id, account_id):
        """Igual que `get_owned_account` pero bloqueando la fila (`FOR UPDATE`).

        Debe llamarse dentro de un bloque `atomic()`: el bloqueo dura lo que dura
        la transaccion. Es lo que sostiene INV-07 bajo concurrencia.
        """
        return self._fetch_account(user_id, account_id, lock=True)

    def build_snapshot(self, account):
        """Traduce una fila de cuenta a su objeto de dominio.

        Unico punto del servicio donde una fila se convierte en `AccountSnapshot`.
        """
        return AccountSnapshot(
            account_id=account.id,
            currency=account.currency,
            account_type=account.type,
            is_archived=account.is_archived,
            balance=Money(account.balance, account.currency),
        )

    def list_accounts(self, user_id, include_archived=False):
        """Cuentas del usuario, ordenadas por nombre."""
        statement = select(Account).where(Account.user_id == user_id)
        if not include_archived:
            statement = statement.where(Account.is_archived.is_(False))
        return Listing(self._session, statement.order_by(Account.name))

    def find_listed_account(self, user_id, account_id, include_archived=False):
        """Una cuenta dentro del listado del usuario, o `None`.

        Reproduce el detalle `GET /accounts/{id}/` del monolito, que buscaba la
        cuenta dentro del mismo queryset del listado: una cuenta archivada solo
        aparece si se pide `include_archived`.
        """
        pk = _as_uuid(account_id)
        if pk is None:
            return None
        statement = select(Account).where(
            Account.user_id == user_id, Account.id == pk
        )
        if not include_archived:
            statement = statement.where(Account.is_archived.is_(False))
        return self._session.execute(statement).scalar_one_or_none()

    def rename_account(self, user_id, account_id, name):
        """Renombra una cuenta del usuario; lo demas es inmutable.

        La regla del nombre se reutiliza del Builder para que crear y renombrar
        no puedan divergir. La constraint de unicidad es la autoridad final.
        """
        account = self.get_owned_account(user_id, account_id)
        cleaned_name = self._validate_account_name(name, account)

        try:
            with atomic(self._session):
                account.name = cleaned_name
        except IntegrityError as exc:
            if _violated_constraint(exc) == UNIQUE_ACCOUNT_NAME_CONSTRAINT:
                raise DuplicateAccountNameError(
                    messages.DUPLICATE_ACCOUNT_NAME.format(name=cleaned_name)
                ) from exc
            raise
        return account

    def archive_account(self, user_id, account_id):
        """Archiva una cuenta. Idempotente.

        Archivar si esta permitido con transacciones: lo que INV-13 protege es
        borrar, no archivar.
        """
        account = self.get_owned_account(user_id, account_id)
        if not account.is_archived:
            with atomic(self._session):
                account.is_archived = True
        return account

    def delete_account(self, user_id, account_id):
        """Elimina una cuenta sin transacciones (INV-13).

        El `DELETE` va directo a la base y es la FK `RESTRICT` de
        `finance_transaction.account_id` la que lo rechaza si hay transacciones.
        """
        account = self.get_owned_account(user_id, account_id)
        try:
            with atomic(self._session):
                self._session.execute(delete(Account).where(Account.id == account.id))
        except IntegrityError as exc:
            if _sqlstate(exc) in REFERENCED_ROW_SQLSTATES:
                raise AccountHasTransactionsError(
                    messages.ACCOUNT_HAS_TRANSACTIONS.format(name=account.name)
                ) from exc
            raise

    def recompute_balance(self, user_id, account_id):
        """Recalcula el balance desde las transacciones y lo persiste (INV-07).

        `balance = opening_balance + suma de movimientos` (C-17), bajo bloqueo.
        Operacion de reparacion; no toca `opening_balance`.
        """
        with atomic(self._session):
            account = self.get_locked_account(user_id, account_id)
            rows = self._session.execute(
                select(Transaction.amount, Transaction.type)
                .where(Transaction.account_id == account.id)
                .order_by(Transaction.occurred_on, Transaction.created_at)
            ).all()
            movements = [
                (Money(amount, account.currency), TransactionType.from_value(kind))
                for amount, kind in rows
            ]
            recomputed = BalanceCalculator.recompute(
                Money(account.opening_balance, account.currency), movements
            )
            account.balance = recomputed.amount
        return account

    def audit_balances(self, user_id=None):
        """Audita INV-07 sobre las cuentas y devuelve un resultado por cuenta.

        Vive en `AccountService` porque `Account` es la raiz del agregado. Sin
        `user_id` recorre todas las cuentas; con el, solo las suyas.

        **No reimplementa la aritmetica:** el calculo lo hace
        `BalanceCalculator.recompute`, el mismo de `recompute_balance`. Una
        auditoria que duplicara la formula podria compartir el defecto del
        auditado. Solo lee.
        """
        # Consultas por columnas y no por entidades: una auditoria lee lo que hay
        # en la base, nunca una copia vieja del mapa de identidad de la sesion.
        statement = select(
            Account.id,
            Account.name,
            Account.user_id,
            Account.currency,
            Account.balance,
            Account.opening_balance,
        ).order_by(Account.user_id, Account.name)
        if user_id is not None:
            statement = statement.where(Account.user_id == user_id)
        accounts = self._session.execute(statement).all()

        movements = {account.id: [] for account in accounts}
        rows = self._session.execute(
            select(Transaction.account_id, Transaction.amount, Transaction.type).where(
                Transaction.account_id.in_(movements)
            )
        ).all()
        for account_id, amount, kind in rows:
            movements[account_id].append((amount, kind))

        return [
            BalanceAuditResult(
                account_id=account.id,
                account_name=account.name,
                owner_id=account.user_id,
                persisted=Money(account.balance, account.currency),
                calculated=BalanceCalculator.recompute(
                    Money(account.opening_balance, account.currency),
                    [
                        (Money(amount, account.currency), TransactionType.from_value(kind))
                        for amount, kind in movements[account.id]
                    ],
                ),
            )
            for account in accounts
        ]

    def audit_categorization(self, user_id=None):
        """Audita el estado de categorizacion de las transacciones (INV-08).

        Detecta dos incoherencias:

        - **Procedencia sin categoria:** algo clasifico la transaccion pero no
          quedo categoria. INV-08 violada.
        - **Categoria sin procedencia:** ninguna ruta de los servicios produce ese
          estado, asi que delata una escritura que evadio esta capa.

        Solo lee. `--fix` tampoco corrige esto.
        """
        # Por columnas, igual que `audit_balances`: lo que hay en la base, no lo
        # que recuerda el mapa de identidad de la sesion.
        statement = (
            select(
                Transaction.id,
                Account.name.label("account_name"),
                Account.user_id,
                Transaction.category_id,
                Category.name.label("category_name"),
                Transaction.categorization_source,
            )
            .select_from(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                or_(
                    and_(
                        Transaction.categorization_source.is_not(None),
                        Transaction.category_id.is_(None),
                    ),
                    and_(
                        Transaction.categorization_source.is_(None),
                        Transaction.category_id.is_not(None),
                    ),
                )
            )
            .order_by(Account.name, Transaction.occurred_on)
        )
        if user_id is not None:
            statement = statement.where(Account.user_id == user_id)

        return [
            CategorizationAuditResult(
                transaction_id=row.id,
                account_name=row.account_name,
                owner_id=row.user_id,
                reason=MISSING_CATEGORY if row.category_id is None else MISSING_SOURCE,
                category_name=row.category_name,
                categorization_source=row.categorization_source,
            )
            for row in self._session.execute(statement)
        ]

    def _fetch_account(self, user_id, account_id, lock):
        """Recupera una cuenta del usuario o lanza `AccountNotFoundError`."""
        pk = _as_uuid(account_id)
        if pk is None:
            raise AccountNotFoundError()

        statement = select(Account).where(
            Account.user_id == user_id, Account.id == pk
        )
        if lock:
            statement = statement.with_for_update()

        account = self._session.execute(statement).scalar_one_or_none()
        if account is None:
            raise AccountNotFoundError()
        return account

    @staticmethod
    def _resolve_currency(currency, initial_balance):
        """La moneda declarada manda; luego la del saldo inicial; luego el default."""
        if currency is not None:
            return currency
        if isinstance(initial_balance, Money):
            return initial_balance.currency
        return DEFAULT_CURRENCY

    @staticmethod
    def _as_money(amount, currency):
        """Envuelve el saldo inicial en la moneda de la cuenta si no lo esta ya."""
        if isinstance(amount, Money):
            return amount
        return Money(amount, currency)

    @staticmethod
    def _validate_account_name(name, account):
        """Valida un nombre de cuenta con la misma regla que la creacion."""
        draft = (
            AccountBuilder()
            .for_user(account.user_id)
            .named(name)
            .of_type(account.type)
            .in_currency(account.currency)
            .build()
        )
        return draft.name


class TransactionService:
    """Casos de uso sobre transacciones.

    Recibe el categorizador por constructor y depende solo de la ABC
    `Categorizer` (ARCHITECTURE.md 8, fila DIP).
    """

    def __init__(self, session, categorizer):
        self._session = session
        self._categorizer = categorizer
        self._accounts = AccountService(session)

    def register_transaction(
        self,
        user_id,
        account_id,
        amount,
        transaction_type,
        occurred_on,
        description="",
        category_name=None,
    ):
        """Registra una transaccion y actualiza el balance de la cuenta.

        Propiedad, bloqueo, Builder, categorizacion, INV-14 y persistencia, todo
        en una unica transaccion: cualquier fallo revierte la operacion entera.
        """
        with atomic(self._session):
            account = self._accounts.get_locked_account(user_id, account_id)
            snapshot = self._accounts.build_snapshot(account)

            builder = (
                TransactionBuilder()
                .for_account(snapshot)
                .with_amount(self._as_money(amount, snapshot.currency))
                .of_type(transaction_type)
                .occurred_on(occurred_on)
                .described_as(description)
            )
            if category_name is not None:
                builder.with_manual_category(category_name)
            else:
                builder.categorized_by(self._categorizer)

            draft = builder.build()

            new_balance = BalanceCalculator.apply(
                snapshot.balance, draft.amount, draft.transaction_type
            )
            # INV-14: la verificacion que el Builder deja pendiente a proposito.
            # Aqui el saldo es autoritativo porque la fila esta bloqueada.
            TransactionRules.ensure_balance_allowed(snapshot.account_type, new_balance)

            category = self._resolve_category(
                draft.category_name, draft.transaction_type
            )

            created = Transaction(**self._draft_to_columns(draft, account, category))
            self._session.add(created)

            account.balance = new_balance.amount

        return created

    def recategorize(self, user_id, transaction_id, category_name):
        """Reasigna manualmente la categoria. No toca el balance."""
        with atomic(self._session):
            movement = self.get_transaction(user_id, transaction_id)
            transaction_type = TransactionType.from_value(movement.type)

            TransactionRules.ensure_categorized(category_name)
            category = self._resolve_category(category_name, transaction_type)

            movement.category = category
            movement.categorization_source = CategorizationSource.MANUAL.value
            movement.categorization_confidence = MANUAL_CATEGORY_CONFIDENCE
        return movement

    def delete_transaction(self, user_id, transaction_id):
        """Elimina una transaccion y deshace su efecto sobre el balance.

        Puede rechazarse: si revertir un ingreso deja negativa una cuenta que no
        admite numeros rojos, se viola INV-14.
        """
        with atomic(self._session):
            movement = self.get_transaction(user_id, transaction_id)
            account = self._accounts.get_locked_account(user_id, movement.account_id)
            snapshot = self._accounts.build_snapshot(account)

            reverted = BalanceCalculator.revert(
                snapshot.balance,
                Money(movement.amount, account.currency),
                TransactionType.from_value(movement.type),
            )
            TransactionRules.ensure_balance_allowed(snapshot.account_type, reverted)

            self._session.delete(movement)
            account.balance = reverted.amount

    def list_transactions(
        self, user_id, account_id=None, category_id=None, date_from=None, date_to=None
    ):
        """Transacciones del usuario, con filtros opcionales.

        Siempre acotada a las cuentas del usuario: ninguna combinacion de filtros
        alcanza una transaccion ajena. Orden del monolito: mas recientes primero.
        """
        statement = (
            select(Transaction)
            .join(Transaction.account)
            .where(Account.user_id == user_id)
        )
        if account_id is not None:
            statement = statement.where(Transaction.account_id == account_id)
        if category_id is not None:
            statement = statement.where(Transaction.category_id == category_id)
        if date_from is not None:
            statement = statement.where(Transaction.occurred_on >= date_from)
        if date_to is not None:
            statement = statement.where(Transaction.occurred_on <= date_to)
        return Listing(
            self._session,
            statement.order_by(
                Transaction.occurred_on.desc(), Transaction.created_at.desc()
            ),
        )

    def get_transaction(self, user_id, transaction_id):
        """Una transaccion del usuario o `TransactionNotFoundError` (D-08)."""
        pk = _as_uuid(transaction_id)
        if pk is None:
            raise TransactionNotFoundError()

        movement = self._session.execute(
            select(Transaction)
            .join(Transaction.account)
            .where(Account.user_id == user_id, Transaction.id == pk)
        ).scalar_one_or_none()
        if movement is None:
            raise TransactionNotFoundError()
        return movement

    @staticmethod
    def _as_money(amount, currency):
        """Envuelve el monto en la moneda de la cuenta si no es ya un `Money`."""
        if isinstance(amount, Money):
            return amount
        return Money(amount, currency)

    def _resolve_category(self, category_name, transaction_type):
        """Resuelve el nombre de categoria contra el catalogo persistido."""
        if category_name is None:
            return None

        category = self._session.execute(
            select(Category).where(Category.name == category_name)
        ).scalar_one_or_none()
        if category is None:
            raise CategoryNotFoundError(
                messages.CATEGORY_NOT_FOUND.format(name=category_name)
            )

        if category.applies_to != transaction_type.value:
            raise CategoryTypeMismatchError(
                messages.CATEGORY_TYPE_MISMATCH.format(
                    category=category.name,
                    applies_to=category.applies_to,
                    transaction_type=transaction_type.value,
                )
            )
        return category

    @staticmethod
    def _draft_to_columns(draft, account, category):
        """Traduce un `TransactionDraft` a columnas. Es la frontera explicita."""
        source = draft.categorization_source
        return {
            "account": account,
            "amount": draft.amount.amount,
            "type": draft.transaction_type.value,
            "category": category,
            "description": draft.description,
            "occurred_on": draft.occurred_on,
            "categorization_source": source.value if source is not None else None,
            "categorization_confidence": draft.confidence,
        }
