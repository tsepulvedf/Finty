"""Serializers del contrato REST de `finance` (anillo externo).

Responsabilidad exclusivamente sintactica: formato, tipos, longitudes y campos
requeridos. Ningun `validate_*()` consulta la base de datos. Que una categoria
exista, que la cuenta sea del usuario o que el balance quede negativo son
decisiones del servicio, no del serializer (RULES.md, regla 4).

**Entradas con `Serializer` plano, salidas con `ModelSerializer`.** No es
inconsistencia sino dos problemas distintos: el contrato de entrada no debe
quedar atado a la forma de la tabla, porque la API deberia poder aceptar
`account_id` aunque la columna se llamara de otro modo; la salida, en cambio,
**es** la forma de la fila, y declarar `Meta.fields` explicitamente hace que un
campo nuevo en el modelo no se filtre solo al contrato publico.

`DecimalField` de DRF entrega un `Decimal`, nunca un flotante binario. Es lo que
permite que el dinero llegue intacto desde el JSON hasta el dominio.
"""
from rest_framework import serializers

from finance.domain.value_objects import AccountType, TransactionType
from finance.models import Account, Category, Transaction

MAX_ACCOUNT_NAME_LENGTH = 120
MAX_CATEGORY_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 255
CURRENCY_CODE_LENGTH = 3

MONEY_MAX_DIGITS = 14
MONEY_DECIMAL_PLACES = 2

# Los valores validos salen de los enums del dominio, igual que los `choices` del
# modelo. Una sola fuente de verdad para los tres sitios.
ACCOUNT_TYPE_VALUES = [member.value for member in AccountType]
TRANSACTION_TYPE_VALUES = [member.value for member in TransactionType]


# --- Entradas ---------------------------------------------------------------


class AccountInputSerializer(serializers.Serializer):
    """Datos de entrada para crear una cuenta."""

    name = serializers.CharField(max_length=MAX_ACCOUNT_NAME_LENGTH)
    type = serializers.ChoiceField(choices=ACCOUNT_TYPE_VALUES)
    initial_balance = serializers.DecimalField(
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
        required=False,
    )
    currency = serializers.CharField(
        min_length=CURRENCY_CODE_LENGTH,
        max_length=CURRENCY_CODE_LENGTH,
        required=False,
    )


class AccountRenameSerializer(serializers.Serializer):
    """Datos de entrada para renombrar una cuenta.

    Solo el nombre: el tipo, la moneda y el saldo de apertura son inmutables tras
    la creacion, y el balance lo mueven las transacciones.
    """

    name = serializers.CharField(max_length=MAX_ACCOUNT_NAME_LENGTH)


class TransactionInputSerializer(serializers.Serializer):
    """Datos de entrada para registrar una transaccion.

    No valida que el monto sea distinto de cero, ni que la fecha no sea futura,
    ni que la categoria exista: eso es semantica y vive en el dominio y en el
    servicio. Aqui solo se comprueba que los tipos sean los correctos.
    """

    account_id = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES
    )
    type = serializers.ChoiceField(choices=TRANSACTION_TYPE_VALUES)
    occurred_on = serializers.DateField()
    description = serializers.CharField(
        max_length=MAX_DESCRIPTION_LENGTH,
        required=False,
        allow_blank=True,
        default="",
    )
    category_name = serializers.CharField(
        max_length=MAX_CATEGORY_NAME_LENGTH, required=False
    )


class RecategorizeInputSerializer(serializers.Serializer):
    """Datos de entrada para reclasificar manualmente una transaccion."""

    category_name = serializers.CharField(max_length=MAX_CATEGORY_NAME_LENGTH)


class TransactionFilterSerializer(serializers.Serializer):
    """Filtros de la consulta de transacciones.

    Existe para que la vista no haga parsing manual de `request.query_params`:
    una fecha mal formada se rechaza aqui con 400 en lugar de reventar dentro del
    servicio. Todos los filtros son opcionales.
    """

    account_id = serializers.UUIDField(required=False)
    category_id = serializers.UUIDField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)


# --- Salidas ----------------------------------------------------------------


class AccountOutputSerializer(serializers.ModelSerializer):
    """Representacion de salida de una cuenta.

    **`user` no se expone y no debe agregarse.** Quien consulta ya sabe quien es
    —el queryset viene filtrado por `request.user`— y publicar el identificador
    no aporta nada al cliente mientras si amplia la superficie del contrato.
    """

    class Meta:
        model = Account
        fields = [
            "id",
            "name",
            "type",
            "balance",
            "opening_balance",
            "currency",
            "is_archived",
            "created_at",
        ]


class CategoryOutputSerializer(serializers.ModelSerializer):
    """Representacion de salida de una categoria del catalogo."""

    class Meta:
        model = Category
        fields = ["id", "name", "applies_to"]


class TransactionOutputSerializer(serializers.ModelSerializer):
    """Representacion de salida de una transaccion.

    `account_name` y `category_name` aplanan las relaciones con `source`, para
    que el dashboard no tenga que resolver cada identificador con una peticion
    aparte. Es formateo de presentacion: ninguna regla de negocio vive aqui.
    """

    account_name = serializers.CharField(source="account.name", read_only=True)
    category_name = serializers.CharField(
        source="category.name", read_only=True, default=None
    )

    class Meta:
        model = Transaction
        fields = [
            "id",
            "account",
            "account_name",
            "amount",
            "type",
            "category",
            "category_name",
            "description",
            "occurred_on",
            "categorization_source",
            "categorization_confidence",
            "created_at",
        ]
