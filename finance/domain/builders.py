"""Builders del dominio `finance` (anillo de Dominio, Python puro).

`TransactionBuilder` y `AccountBuilder` construyen agregados paso a paso y validan
las invariantes de entidad en `build()` antes de devolver un objeto valido; nunca
se obtiene una instancia a medio construir.

Viven en `domain/` y no en `infra/` porque construir un agregado es logica de
dominio, no de infraestructura (ADR-04). Este modulo no importa nada de la capa
externa: ni el framework web, ni el ORM, ni el contexto de identidad, ni los
adaptadores. Solo la stdlib, `core.domain` y el resto de `domain/`.

**Los builders no reimplementan reglas.** Delegan en `TransactionRules`, que es la
fuente autoritativa. Si una invariante cambia, se toca en un solo sitio y los dos
builders heredan el cambio.
"""
from datetime import date

from core.domain.exceptions import ValidationError
from core.domain.value_objects import Money, validate_currency_code
from finance.domain.exceptions import (
    NegativeAmountError,
    NegativeBalanceNotAllowedError,
)
from finance.domain.interfaces import Categorizer
from finance.domain.logic import TransactionRules
from finance.domain.value_objects import (
    AccountDraft,
    AccountSnapshot,
    AccountType,
    CategorizationSource,
    TransactionDraft,
    TransactionType,
)

MANUAL_CATEGORY_CONFIDENCE = 1.0

MAX_ACCOUNT_NAME_LENGTH = 120


class TransactionBuilder:
    """Construye un `TransactionDraft` valido mediante una interfaz fluida.

    Resuelve el antipatron del constructor posicional de siete argumentos: crear
    una transaccion valida exige coordinar cuenta, monto, tipo, fecha, descripcion
    y el origen de la categoria. Con el builder, el orden de los pasos deja de
    importar y el objeto solo existe cuando esta completo.

    Cada metodo fluido valida su propio argumento de inmediato, en vez de acumular
    basura hasta `build()`. Quien pasa un tipo invalido se entera en la linea
    donde lo pasa, no doce lineas despues.

        draft = (
            TransactionBuilder()
            .for_account(snapshot)
            .with_amount(Money("50000", "COP"))
            .of_type(TransactionType.EXPENSE)
            .occurred_on(date(2026, 8, 23))
            .described_as("Almuerzo")
            .categorized_by(categorizer)
            .build()
        )

    **Lectura de INV-08.** Si no se pide categorizacion, el draft sale con
    `category_name`, `categorization_source` y `confidence` en `None`, y eso es un
    estado legitimo: la columna admite nulo e INV-08 exige categoria **despues**
    del procesamiento de categorizacion, no antes. Lo que la invariante prohibe es
    invocar al categorizador y quedarse sin categoria; eso si se verifica.

    **`build()` no comprueba INV-14.** El saldo resultante depende del balance
    autoritativo leido bajo bloqueo, y el builder no puede conocerlo sin arrastrar
    persistencia hacia el dominio: el `AccountSnapshot` que recibe es una foto que
    pudo quedar obsoleta. Esa verificacion pertenece al Service (M5), dentro del
    bloque atomico. No la agregues aqui.

    **De un solo uso.** Una segunda llamada a `build()` lanza `ValidationError`,
    porque el categorizador se invoca durante `build()` y permitir
    reconstrucciones dispararia llamadas repetidas a un colaborador externo. Un
    builder es una linea de ensamblaje, no una plantilla reutilizable.
    """

    def __init__(self):
        self._snapshot = None
        self._amount = None
        self._transaction_type = None
        self._occurred_on = None
        self._description = ""
        self._categorizer = None
        self._manual_category = None
        self._today = None
        self._consumed = False

    def for_account(self, snapshot):
        """Fija la cuenta destino a partir de su snapshot."""
        if not isinstance(snapshot, AccountSnapshot):
            raise ValidationError(
                f"Se esperaba un AccountSnapshot, no {type(snapshot).__name__}."
            )
        self._snapshot = snapshot
        return self

    def with_amount(self, amount):
        """Fija el monto. Debe ser un `Money`, nunca un numero suelto."""
        if not isinstance(amount, Money):
            raise ValidationError(
                f"El monto debe ser un Money, no {type(amount).__name__}. "
                f"Un numero sin moneda no es una cantidad de dinero."
            )
        self._amount = amount
        return self

    def of_type(self, transaction_type):
        """Fija el tipo de movimiento, normalizandolo (INV-09)."""
        self._transaction_type = TransactionType.from_value(transaction_type)
        return self

    def occurred_on(self, day):
        """Fija la fecha en que ocurrio el movimiento."""
        if not isinstance(day, date):
            raise ValidationError(
                f"La fecha debe ser un date, no {type(day).__name__}."
            )
        self._occurred_on = day
        return self

    def described_as(self, description):
        """Fija la descripcion libre del movimiento."""
        if description is None:
            self._description = ""
            return self
        if not isinstance(description, str):
            raise ValidationError(
                f"La descripcion debe ser texto, no {type(description).__name__}."
            )
        self._description = description.strip()
        return self

    def categorized_by(self, categorizer):
        """Pide que la categoria la resuelva un `Categorizer`.

        El categorizador **no** se invoca aqui: se guarda y se llama dentro de
        `build()`, cuando el resto de invariantes ya paso. Llamarlo en este metodo
        gastaria una invocacion a un colaborador externo por una transaccion que
        quiza ni siquiera sea valida.
        """
        if not isinstance(categorizer, Categorizer):
            raise ValidationError(
                f"Se esperaba un Categorizer, no {type(categorizer).__name__}."
            )
        if self._manual_category is not None:
            raise ValidationError(
                "No se puede combinar categorizacion automatica y manual: "
                "elige una de las dos."
            )
        self._categorizer = categorizer
        return self

    def with_manual_category(self, name):
        """Asigna una categoria elegida por el usuario."""
        if not isinstance(name, str) or not name.strip():
            raise ValidationError(
                "El nombre de la categoria manual no puede estar vacio."
            )
        if self._categorizer is not None:
            raise ValidationError(
                "No se puede combinar categorizacion automatica y manual: "
                "elige una de las dos."
            )
        self._manual_category = name.strip()
        return self

    def as_of(self, today):
        """Inyecta la fecha de referencia para verificar INV-12.

        Existe para que las reglas no dependan del reloj del sistema y para que el
        dominio no necesite la utilidad de zona horaria del framework.
        """
        if not isinstance(today, date):
            raise ValidationError(
                f"La fecha de referencia debe ser un date, no "
                f"{type(today).__name__}."
            )
        self._today = today
        return self

    def build(self):
        """Valida todas las invariantes y devuelve el `TransactionDraft`."""
        if self._consumed:
            raise ValidationError(
                "Este builder ya se uso. Construye uno nuevo: un builder es una "
                "linea de ensamblaje, no una plantilla reutilizable."
            )
        self._consumed = True

        self._require_mandatory_fields()

        TransactionRules.ensure_amount_not_zero(self._amount)
        if self._amount.is_negative():
            raise NegativeAmountError(
                f"El monto llego como {self._amount}. Los montos se guardan en "
                f"positivo y el signo lo aporta el tipo de transaccion."
            )
        TransactionRules.ensure_currency_matches(
            self._snapshot.currency, self._amount
        )
        TransactionRules.ensure_date_not_future(self._occurred_on, self._today)
        TransactionRules.ensure_account_is_active(self._snapshot.is_archived)

        category_name, source, confidence = self._resolve_category()

        return TransactionDraft(
            account_id=self._snapshot.account_id,
            amount=self._amount,
            transaction_type=self._transaction_type,
            occurred_on=self._occurred_on,
            description=self._description,
            category_name=category_name,
            categorization_source=source,
            confidence=confidence,
        )

    def _require_mandatory_fields(self):
        """Exige los cuatro campos sin los cuales no hay transaccion."""
        faltantes = {
            "cuenta": self._snapshot,
            "monto": self._amount,
            "tipo": self._transaction_type,
            "fecha": self._occurred_on,
        }
        for nombre, valor in faltantes.items():
            if valor is None:
                raise ValidationError(
                    f"Falta la {nombre} de la transaccion."
                )

    def _resolve_category(self):
        """Devuelve `(nombre, fuente, confianza)` segun el modo elegido."""
        if self._categorizer is not None:
            suggestion = self._categorizer.categorize(
                self._description, self._amount, self._transaction_type
            )
            # INV-08: se invoco la categorizacion, asi que debe quedar categoria.
            TransactionRules.ensure_categorized(suggestion.category_name)
            return suggestion.category_name, suggestion.source, suggestion.confidence

        if self._manual_category is not None:
            TransactionRules.ensure_categorized(self._manual_category)
            return (
                self._manual_category,
                CategorizationSource.MANUAL,
                MANUAL_CATEGORY_CONFIDENCE,
            )

        return None, None, None
