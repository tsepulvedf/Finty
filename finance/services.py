"""Casos de uso del contexto `finance` (anillo de Servicios).

`AccountService` y `TransactionService` orquestan el camino critico: verificar la
propiedad de la cuenta (INV-03), bloquear la fila, construir el agregado con el
Builder, recalcular el balance (INV-07) y persistir, todo dentro de una
transaccion atomica.

**Que hace esta capa y que no.** Orquesta y traduce; no decide reglas. Las reglas
viven en `finance/domain/` y esta capa las invoca. Las dos unicas verificaciones
que aqui se hacen y no en el dominio son las que el dominio no puede hacer solo:
INV-14 sobre el balance resultante, que necesita el saldo autoritativo bajo
bloqueo, y la resolucion de la categoria contra el catalogo persistido.

**Inversion de dependencias.** `TransactionService` recibe un `Categorizer` por
constructor y depende solo de la ABC. Este modulo no importa ninguna
implementacion concreta ni la fabrica: quien elige es la vista (M6), que pide una
al Factory Method y la inyecta. Hay un grep que lo verifica.

Los servicios no capturan excepciones de dominio para traducirlas: las dejan
subir y el handler global de `core/api/exception_handler.py` las convierte a HTTP.
Lo que si traducen son las excepciones del ORM, que no deben escapar de aqui.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import ProtectedError

from core.domain.value_objects import Money
from finance.domain.builders import AccountBuilder, TransactionBuilder
from finance.domain.exceptions import (
    AccountHasTransactionsError,
    AccountNotFoundError,
    CategoryNotFoundError,
    CategoryTypeMismatchError,
    DuplicateAccountNameError,
    TransactionNotFoundError,
)
from finance.domain.logic import BalanceCalculator, TransactionRules
from finance.domain.value_objects import (
    AccountSnapshot,
    CategorizationSource,
    TransactionType,
)
from finance.models import Account, Category, Transaction

MANUAL_CATEGORY_CONFIDENCE = 1.0

# Nombre de la constraint que materializa la unicidad de nombre por usuario. Se
# compara contra el mensaje del IntegrityError para no confundir esa violacion
# con cualquier otra.
UNIQUE_ACCOUNT_NAME_CONSTRAINT = "uniq_account_name_per_user"


class AccountService:
    """Casos de uso sobre cuentas.

    Sin argumentos de constructor: no tiene colaboradores que intercambiar, a
    diferencia de `TransactionService`. Misma forma que `ProfileService` (M1).
    """

    def create_account(
        self, user, name, account_type, initial_balance=None, currency=None
    ):
        """Crea una cuenta para el usuario y devuelve la fila persistida.

        Toda la validacion de negocio ocurre en `AccountBuilder.build()`: nombre
        no vacio, tipo valido, moneda valida e INV-14 sobre el saldo inicial. Este
        metodo solo traduce el draft a columnas.
        """
        builder = (
            AccountBuilder().for_user(user.pk).named(name).of_type(account_type)
        )
        if initial_balance is not None:
            builder.with_initial_balance(initial_balance)
        if currency is not None:
            builder.in_currency(currency)

        draft = builder.build()

        try:
            # Bloque atomico propio: un IntegrityError deja la transaccion de
            # PostgreSQL abortada, y sin este savepoint contaminaria cualquier
            # consulta posterior del llamante.
            with db_transaction.atomic():
                return Account.objects.create(
                    user=user,
                    name=draft.name,
                    type=draft.account_type.value,
                    balance=draft.initial_balance.amount,
                    currency=draft.initial_balance.currency,
                )
        except IntegrityError as exc:
            if UNIQUE_ACCOUNT_NAME_CONSTRAINT in str(exc):
                raise DuplicateAccountNameError(
                    f"Ya tienes una cuenta llamada '{draft.name}'."
                ) from exc
            raise

    def get_owned_account(self, user, account_id):
        """Devuelve una cuenta del usuario o lanza `AccountNotFoundError`.

        La consulta va filtrada por usuario, asi que una cuenta ajena y una
        inexistente son indistinguibles desde fuera. **Es deliberado**: responder
        403 cuando la cuenta existe pero es de otro revelaria que identificadores
        estan en uso en el sistema. Es la misma decision que el mensaje unico de
        credenciales invalidas en M1.

        `AccountNotOwnedError` se reserva para verificar propiedad sobre un objeto
        ya recuperado por otra via, donde el identificador no se filtra porque el
        llamante ya lo tenia.
        """
        return self._fetch_account(Account.objects.all(), user, account_id)

    def get_locked_account(self, user, account_id):
        """Igual que `get_owned_account` pero bloqueando la fila.

        **Solo puede llamarse dentro de un bloque atomico.** Fuera de uno, Django
        lanza `TransactionManagementError`: un bloqueo sin transaccion que lo
        sostenga no significa nada.

        El bloqueo es lo que sostiene INV-07 bajo concurrencia: dos escrituras
        simultaneas sobre la misma cuenta se serializan en lugar de leer las dos
        el mismo balance y pisarse.
        """
        return self._fetch_account(
            Account.objects.select_for_update(), user, account_id
        )

    def build_snapshot(self, account):
        """Traduce una fila de cuenta a su objeto de dominio.

        Es el **unico punto del sistema** donde una fila se convierte en
        `AccountSnapshot`. Que exista una sola funcion responsable de esa
        traduccion es lo que mantiene nitida la frontera entre persistencia y
        dominio: el balance vuelve a ser un `Money` con su moneda, y el tipo, un
        miembro del enum.
        """
        return AccountSnapshot(
            account_id=account.pk,
            currency=account.currency,
            account_type=account.type,
            is_archived=account.is_archived,
            balance=Money(account.balance, account.currency),
        )

    def list_accounts(self, user, include_archived=False):
        """Devuelve las cuentas del usuario."""
        accounts = Account.objects.filter(user=user)
        if not include_archived:
            accounts = accounts.filter(is_archived=False)
        return accounts

    def archive_account(self, user, account_id):
        """Archiva una cuenta. Idempotente.

        Archivar **si** esta permitido con transacciones presentes: una cuenta se
        archiva precisamente porque se dejo de usar, y su historial es lo que hay
        que conservar. Lo que INV-13 protege es *borrar*, no archivar.
        """
        account = self.get_owned_account(user, account_id)
        if not account.is_archived:
            account.is_archived = True
            account.save(update_fields=["is_archived", "updated_at"])
        return account

    def delete_account(self, user, account_id):
        """Elimina una cuenta sin transacciones (INV-13)."""
        account = self.get_owned_account(user, account_id)
        try:
            with db_transaction.atomic():
                account.delete()
        except ProtectedError as exc:
            raise AccountHasTransactionsError(
                f"La cuenta '{account.name}' tiene transacciones asociadas. "
                f"Archivala en lugar de eliminarla."
            ) from exc

    def recompute_balance(self, user, account_id):
        """Recalcula el balance desde las transacciones y lo persiste (INV-07).

        Es la operacion de reparacion y la referencia autoritativa de la
        invariante: el balance persistido debe coincidir siempre con lo que
        devuelve `BalanceCalculator.recompute` sobre todas las transacciones.
        Corre bajo bloqueo para que ninguna escritura se cuele a mitad del
        recuento.

        **Limitacion conocida:** recalcula partiendo de cero, porque el modelo no
        guarda el saldo de apertura en una columna aparte. En una cuenta creada
        con saldo inicial distinto de cero, ese saldo se pierde al reparar.
        Resolverlo exige una columna `opening_balance`, fuera del alcance de este
        modulo.
        """
        with db_transaction.atomic():
            account = self.get_locked_account(user, account_id)
            movements = [
                (
                    Money(row.amount, account.currency),
                    TransactionType.from_value(row.type),
                )
                for row in account.transactions.all().order_by("occurred_on", "created_at")
            ]
            recomputed = BalanceCalculator.recompute(
                Money.zero(account.currency), movements
            )
            account.balance = recomputed.amount
            account.save(update_fields=["balance", "updated_at"])
            return account

    @staticmethod
    def _fetch_account(queryset, user, account_id):
        """Recupera una cuenta del usuario o lanza `AccountNotFoundError`."""
        try:
            account = queryset.filter(user=user, pk=account_id).first()
        except (DjangoValidationError, ValueError, TypeError) as exc:
            # Un identificador con forma invalida es indistinguible de uno
            # inexistente: la misma respuesta, sin filtrar que el formato fallo.
            raise AccountNotFoundError() from exc

        if account is None:
            raise AccountNotFoundError()
        return account


class TransactionService:
    """Casos de uso sobre transacciones.

    Recibe el categorizador por constructor y depende unicamente de la ABC
    `Categorizer`. Nunca importa una implementacion concreta ni la fabrica: quien
    elige cual usar es la vista, que pide una al Factory Method y la inyecta. Esa
    es la inversion de dependencias del entregable (ARCHITECTURE.md 8, fila DIP).
    """

    def __init__(self, categorizer):
        self._categorizer = categorizer
        self._accounts = AccountService()

    def register_transaction(
        self,
        user,
        account_id,
        amount,
        transaction_type,
        occurred_on,
        description="",
        category_name=None,
    ):
        """Registra una transaccion y actualiza el balance de la cuenta.

        Es el flujo completo del entregable: propiedad, bloqueo, Builder,
        categorizacion, INV-14 y persistencia, todo dentro de una unica
        transaccion atomica. Cualquier fallo entre el bloqueo y el guardado
        revierte la operacion entera: no puede quedar una transaccion creada con
        el balance sin mover, ni al reves.

        `amount` acepta un `Money` o un valor suelto. Si llega suelto se envuelve
        con la moneda de la cuenta, para que la vista no tenga que consultar la
        cuenta antes de llamar. Si llega como `Money`, se respeta tal cual y el
        Builder verifica INV-11 contra la moneda de la cuenta.
        """
        with db_transaction.atomic():
            account = self._accounts.get_locked_account(user, account_id)
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
            # Aqui el saldo si es autoritativo porque la fila esta bloqueada.
            TransactionRules.ensure_balance_allowed(
                snapshot.account_type, new_balance
            )

            category = self._resolve_category(
                draft.category_name, draft.transaction_type
            )

            created = Transaction.objects.create(
                **self._draft_to_model_kwargs(draft, account, category)
            )

            account.balance = new_balance.amount
            # `updated_at` es auto_now, pero con update_fields solo se escribe si
            # se nombra explicitamente.
            account.save(update_fields=["balance", "updated_at"])

            return created

    def recategorize(self, user, transaction_id, category_name):
        """Reasigna manualmente la categoria de una transaccion.

        **No toca el balance.** Cambiar de categoria reclasifica un movimiento, no
        mueve dinero: el monto y el tipo siguen siendo los mismos, asi que el
        saldo de la cuenta no puede cambiar.
        """
        with db_transaction.atomic():
            movement = self.get_transaction(user, transaction_id)
            transaction_type = TransactionType.from_value(movement.type)

            TransactionRules.ensure_categorized(category_name)
            category = self._resolve_category(category_name, transaction_type)

            movement.category = category
            movement.categorization_source = CategorizationSource.MANUAL.value
            movement.categorization_confidence = MANUAL_CATEGORY_CONFIDENCE
            movement.save(
                update_fields=[
                    "category",
                    "categorization_source",
                    "categorization_confidence",
                    "updated_at",
                ]
            )
            return movement

    def delete_transaction(self, user, transaction_id):
        """Elimina una transaccion y deshace su efecto sobre el balance.

        **La operacion puede rechazarse, y es correcto aunque sorprenda.**
        Eliminar un ingreso resta ese dinero del saldo; si eso deja negativa una
        cuenta que no admite numeros rojos, se viola INV-14 y la eliminacion no
        procede. El estado resultante seria invalido, y borrar un registro no es
        excusa para dejar la cuenta en un estado imposible.
        """
        with db_transaction.atomic():
            movement = self.get_transaction(user, transaction_id)
            account = self._accounts.get_locked_account(user, movement.account_id)
            snapshot = self._accounts.build_snapshot(account)

            reverted = BalanceCalculator.revert(
                snapshot.balance,
                Money(movement.amount, account.currency),
                TransactionType.from_value(movement.type),
            )
            TransactionRules.ensure_balance_allowed(
                snapshot.account_type, reverted
            )

            movement.delete()

            account.balance = reverted.amount
            account.save(update_fields=["balance", "updated_at"])

    def list_transactions(
        self, user, account_id=None, category_id=None, date_from=None, date_to=None
    ):
        """Devuelve las transacciones del usuario, con filtros opcionales.

        Siempre acotada a las cuentas del usuario: no hay combinacion de filtros
        que alcance una transaccion ajena. `select_related` evita el N+1 que
        produciria el dashboard al leer cuenta y categoria de cada fila.
        """
        movements = Transaction.objects.filter(account__user=user).select_related(
            "account", "category"
        )
        if account_id is not None:
            movements = movements.filter(account_id=account_id)
        if category_id is not None:
            movements = movements.filter(category_id=category_id)
        if date_from is not None:
            movements = movements.filter(occurred_on__gte=date_from)
        if date_to is not None:
            movements = movements.filter(occurred_on__lte=date_to)
        return movements

    def get_transaction(self, user, transaction_id):
        """Devuelve una transaccion del usuario o lanza `TransactionNotFoundError`.

        Misma politica que `get_owned_account`: una transaccion ajena y una
        inexistente producen la misma respuesta.
        """
        try:
            movement = (
                Transaction.objects.select_related("account", "category")
                .filter(account__user=user, pk=transaction_id)
                .first()
            )
        except (DjangoValidationError, ValueError, TypeError) as exc:
            raise TransactionNotFoundError() from exc

        if movement is None:
            raise TransactionNotFoundError()
        return movement

    @staticmethod
    def _as_money(amount, currency):
        """Envuelve el monto en la moneda de la cuenta si no es ya un `Money`."""
        if isinstance(amount, Money):
            return amount
        return Money(amount, currency)

    @staticmethod
    def _resolve_category(category_name, transaction_type):
        """Resuelve el nombre de categoria contra el catalogo persistido.

        Es la segunda verificacion que el dominio no puede hacer solo: el catalogo
        vive en la base y el dominio no la consulta.
        """
        if category_name is None:
            return None

        category = Category.objects.filter(name=category_name).first()
        if category is None:
            raise CategoryNotFoundError(
                f"No existe la categoria '{category_name}'."
            )

        if category.applies_to != transaction_type.value:
            raise CategoryTypeMismatchError(
                f"La categoria '{category.name}' aplica a movimientos de tipo "
                f"'{category.applies_to}', no a '{transaction_type.value}'."
            )
        return category

    @staticmethod
    def _draft_to_model_kwargs(draft, account, category):
        """Traduce un `TransactionDraft` a columnas.

        Mapeo campo por campo, nunca una conversion automatica del dataclass:
        `amount` es un `Money` y la columna es un `DecimalField`, los enums se
        persisten por su `.value` y `account_id` se reemplaza por la instancia ya
        recuperada. Este metodo **es la frontera**; que sea explicito es
        precisamente la razon de que el dominio no necesite saber de columnas.
        """
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
