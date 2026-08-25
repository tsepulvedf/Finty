"""Persistencia del contexto `finance` (anillo externo).

Modelos anemicos por ADR-03: solo campos, `Meta`, constraints, indices,
relaciones y `__str__`. Ningun metodo de negocio, ningun `save()` sobreescrito,
ningun `clean()` con reglas, ninguna `@property` calculada y ningun signal. Las
reglas viven en `finance/domain/` y los casos de uso en `finance/services.py`.

Este modulo importa `finance.domain.value_objects` para construir sus `choices`.
La dependencia va de afuera hacia adentro, que es la direccion correcta segun
ADR-02; lo prohibido seria lo inverso.
"""
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models.functions import Length

from finance.domain.value_objects import (
    AccountType,
    CategorizationSource,
    TransactionType,
)

# Habilita el lookup `__length` en las constraints de longitud de moneda. Es la
# forma que documenta Django para usar `Length` dentro de un `CheckConstraint`.
models.CharField.register_lookup(Length)

# Los valores validos tienen una sola fuente de verdad: los enums del dominio.
# Aqui solo se les asocia una etiqueta legible, que es responsabilidad de la capa
# de presentacion. No se usa `TextChoices` de Django porque redeclararia el
# conjunto de valores y abriria la puerta a que dominio y persistencia se
# desincronicen sin que nada lo detecte.
ACCOUNT_TYPE_CHOICES = [
    (AccountType.CASH.value, "Efectivo"),
    (AccountType.BANK.value, "Banco"),
    (AccountType.CREDIT.value, "Credito"),
]

TRANSACTION_TYPE_CHOICES = [
    (TransactionType.INCOME.value, "Ingreso"),
    (TransactionType.EXPENSE.value, "Gasto"),
]

CATEGORIZATION_SOURCE_CHOICES = [
    (CategorizationSource.AI.value, "IA"),
    (CategorizationSource.RULE.value, "Regla"),
    (CategorizationSource.MANUAL.value, "Manual"),
    (CategorizationSource.MOCK.value, "Mock"),
]

CURRENCY_CODE_LENGTH = 3

ACCOUNT_TYPE_VALUES = [value for value, _ in ACCOUNT_TYPE_CHOICES]
TRANSACTION_TYPE_VALUES = [value for value, _ in TRANSACTION_TYPE_CHOICES]

CONFIDENCE_FLOOR = 0.0
CONFIDENCE_CEILING = 1.0


class Category(models.Model):
    """Categoria de transaccion. Catalogo global de solo lectura.

    En la Entrega 1 las categorias son globales y las siembra una migracion de
    datos, no el admin ni los usuarios (ARCHITECTURE.md 5.2, decision D-01). La
    evolucion a categorias por usuario queda como deuda documentada.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=80, unique=True)
    applies_to = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["applies_to", "name"]
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(applies_to__in=TRANSACTION_TYPE_VALUES),
                name="ck_category_applies_to_valid",
            ),
        ]

    def __str__(self):
        return self.name


class Account(models.Model):
    """Cuenta financiera de un usuario. Raiz del agregado (ARCHITECTURE.md 5.1).

    `Transaction` es una entidad **dentro** de este agregado: no se modifica sin
    pasar por la raiz. Toda escritura de transacciones ocurre dentro de un bloque
    atomico con `select_for_update()` sobre esta fila, para que INV-07 se sostenga
    bajo concurrencia (lo implementa `TransactionService` en M5).

    `balance` es un valor **persistido y recalculado**, no derivado en cada
    lectura (decision D-02): el producto es dashboard-centrico y agregar todas las
    transacciones en cada carga degradaria el p95 exigido por SC-05. Quien lo
    recalcula es `BalanceCalculator`, en el dominio; este modelo solo lo almacena.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="accounts",
    )
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=ACCOUNT_TYPE_CHOICES)
    # Saldo con el que se abre la cuenta. **Inmutable tras la creacion**: ningun
    # servicio lo modifica despues, y los `update_fields` de las escrituras de
    # transacciones nombran solo `balance`. Es el termino independiente de INV-07
    # (`balance = opening_balance + suma de movimientos`, correccion C-17): sin
    # esta columna, recalcular desde cero devolveria solo la suma de movimientos
    # y la cuenta perderia su saldo inicial.
    opening_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    currency = models.CharField(max_length=CURRENCY_CODE_LENGTH, default="COP")
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "cuenta"
        verbose_name_plural = "cuentas"
        constraints = [
            # Integridad de datos, no invariante de negocio: impide dos cuentas
            # homonimas del mismo usuario porque serian indistinguibles en el
            # dashboard. No entra al catalogo INV de ARCHITECTURE.md 7.
            models.UniqueConstraint(
                fields=["user", "name"],
                name="uniq_account_name_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(type__in=ACCOUNT_TYPE_VALUES),
                name="ck_account_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__length=CURRENCY_CODE_LENGTH),
                name="ck_account_currency_length",
            ),
            # INV-14 aplicada al instante de creacion: solo una cuenta de credito
            # puede abrir en negativo. A diferencia del balance vivo, aqui si se
            # puede expresar en la base, porque el saldo de apertura no depende de
            # estado variable ni de funciones no inmutables.
            models.CheckConstraint(
                condition=models.Q(type=AccountType.CREDIT.value)
                | models.Q(opening_balance__gte=0),
                name="ck_account_opening_balance_sign",
            ),
        ]

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """Movimiento financiero. Entidad dentro del agregado `Account`.

    **`amount` se guarda siempre positivo.** El signo lo aporta `type` a traves de
    `TransactionType.sign()`, en el dominio. Una columna con signo duplicaria esa
    informacion y abriria la posibilidad de que monto y tipo se contradigan: un
    `amount = -50` con `type = "income"` seria un estado imposible de interpretar.
    Con una sola fuente de verdad ese estado no existe.

    **Defensa en profundidad.** INV-04 (monto distinto de cero) e INV-09 (tipo
    valido) estan implementadas dos veces: en el dominio y como `CheckConstraint`.
    Es deliberado y no es duplicacion accidental. La fuente autoritativa es el
    dominio; la constraint es la red de seguridad ante escrituras que evadan la
    capa de servicios: el shell de Django, migraciones de datos o procesos batch
    futuros. Si un dia alguien inserta por SQL directo, la base sigue defendiendo.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transactions",
    )
    description = models.CharField(max_length=255, blank=True, default="")
    occurred_on = models.DateField()
    categorization_source = models.CharField(
        max_length=10,
        choices=CATEGORIZATION_SOURCE_CHOICES,
        null=True,
        blank=True,
    )
    # No aparece en ARCHITECTURE.md 5.2; se agrega deliberadamente. Phase 0 exige
    # recomendaciones explicables con indicadores de confianza (mitigacion del
    # riesgo R-02) y `CategorySuggestion` ya transporta ese valor desde el
    # dominio. Persistirlo permite mostrarle al usuario que tan segura fue la
    # clasificacion y auditar el desempeno del categorizador a lo largo del
    # tiempo. Es `FloatField` y no `DecimalField` porque es una medida
    # estadistica, no dinero.
    categorization_confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-occurred_on", "-created_at"]
        verbose_name = "transaccion"
        verbose_name_plural = "transacciones"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(amount=0),
                name="ck_transaction_amount_not_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(type__in=TRANSACTION_TYPE_VALUES),
                name="ck_transaction_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(categorization_confidence__isnull=True)
                | models.Q(
                    categorization_confidence__gte=CONFIDENCE_FLOOR,
                    categorization_confidence__lte=CONFIDENCE_CEILING,
                ),
                name="ck_transaction_confidence_range",
            ),
        ]
        # INV-12 (fecha no futura) NO tiene constraint y no debe intentarse:
        # PostgreSQL rechaza funciones no inmutables como CURRENT_DATE dentro de
        # un CHECK, porque una fila valida hoy dejaria de serlo manana y la
        # constraint no podria revalidarse. Esa invariante vive solo en el
        # dominio, en `TransactionRules.ensure_date_not_future`.
        indexes = [
            # El dashboard consulta los movimientos recientes de una cuenta.
            models.Index(
                fields=["account", "-occurred_on"],
                name="ix_transaction_account_date",
            ),
            # Agregacion por categoria dentro de una cuenta.
            models.Index(
                fields=["account", "category"],
                name="ix_transaction_category",
            ),
        ]

    def __str__(self):
        return f"{self.type} {self.amount} {self.occurred_on}"
