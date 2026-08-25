"""Views del contrato REST de `finance` (anillo externo).

Cada view hace exactamente cuatro cosas: validar con el serializer, obtener sus
dependencias, llamar al servicio y traducir el resultado a HTTP. Ningun calculo,
ningun `if` sobre reglas de negocio y **ningun `try/except`**: las excepciones de
dominio las traduce el handler global de `core/api/exception_handler.py`
(RULES.md, regla 3).

**Por que conviven `ModelViewSet` y `APIView` (ADR-05).** El criterio es si la
operacion solo lee y escribe filas o si ejecuta reglas de negocio. `Category` es
un catalogo sin reglas y usa un `ReadOnlyModelViewSet` pelado. `Account` es CRUD
con una regla —la propiedad— y usa un `ModelViewSet` que delega cada escritura al
servicio. `Transaction` orquesta Factory, Builder, recalculo de balance y
transaccion atomica, y usa `APIView` porque ahi el control explicito vale mas que
la brevedad. Tener los tres tipos en el mismo proyecto es evidencia de criterio
arquitectonico, no de dogma.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from finance.api.serializers import (
    AccountInputSerializer,
    AccountOutputSerializer,
    AccountRenameSerializer,
    CategoryOutputSerializer,
    RecategorizeInputSerializer,
    TransactionFilterSerializer,
    TransactionInputSerializer,
    TransactionOutputSerializer,
)
from finance.infra.factories import CategorizerFactory
from finance.models import Category
from finance.services import AccountService, TransactionService

TRUTHY_QUERY_VALUES = {"1", "true", "yes", "on"}


def _flag(request, name):
    """Lee un parametro de consulta booleano. Formato, no negocio."""
    return request.query_params.get(name, "").strip().lower() in TRUTHY_QUERY_VALUES


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """`/api/v1/categories/` — catalogo global de solo lectura.

    **El unico recurso sin servicio detras, y es deliberado.** No hay ninguna
    regla que orquestar: es el caso "solo lee filas" del criterio de ADR-05.
    Interponer un `CategoryService` que se limitara a devolver
    `Category.objects.all()` seria ceremonia sin contenido.

    Su presencia junto a las `APIView` de transacciones es precisamente lo que
    demuestra que la eleccion entre un ViewSet y una APIView responde a un
    criterio y no a un dogma aplicado por igual a todo.

    Solo expone `GET`. En la Entrega 1 el catalogo lo gobierna la carga inicial de
    datos, asi que `POST`, `PUT` y `DELETE` devuelven 405.
    """

    queryset = Category.objects.all()
    serializer_class = CategoryOutputSerializer


class AccountViewSet(viewsets.ModelViewSet):
    """`/api/v1/accounts/` — cuentas del usuario autenticado.

    CRUD con una regla —la propiedad—, asi que usa un `ModelViewSet` pero **no
    escribe ni una fila por su cuenta**: cada operacion delega en
    `AccountService`. El `queryset` nunca es `Account.objects.all()`; sale del
    servicio ya filtrado por `request.user`, que es como se materializa INV-03 en
    esta capa.
    """

    serializer_class = AccountOutputSerializer

    def get_queryset(self):
        """Cuentas del usuario autenticado, filtradas por el servicio."""
        return AccountService().list_accounts(
            self.request.user,
            include_archived=_flag(self.request, "include_archived"),
        )

    def create(self, request, *args, **kwargs):
        """Crea una cuenta y devuelve 201."""
        serializer = AccountInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account = AccountService().create_account(
            user=request.user,
            name=serializer.validated_data["name"],
            account_type=serializer.validated_data["type"],
            initial_balance=serializer.validated_data.get("initial_balance"),
            currency=serializer.validated_data.get("currency"),
        )
        return Response(
            AccountOutputSerializer(account).data, status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        """Renombra la cuenta. Lo demas es inmutable tras la creacion."""
        serializer = AccountRenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account = AccountService().rename_account(
            request.user, kwargs["pk"], serializer.validated_data["name"]
        )
        return Response(AccountOutputSerializer(account).data)

    def partial_update(self, request, *args, **kwargs):
        """`PATCH` se comporta igual que `PUT`: solo el nombre es editable."""
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Elimina la cuenta y devuelve 204 (INV-13 la protege si tiene datos)."""
        AccountService().delete_account(request.user, kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """`POST /accounts/{id}/archive/` — archiva sin borrar."""
        account = AccountService().archive_account(request.user, pk)
        return Response(AccountOutputSerializer(account).data)


class TransactionsAPIView(APIView):
    """`/api/v1/transactions/` — listado y registro.

    `POST` es el flujo completo del diagrama de secuencia de ARCHITECTURE.md 9.2.
    """

    def build_service(self):
        """Construye el servicio inyectandole el categorizador de la fabrica.

        **Aqui se cierra la inversion de dependencias del entregable.** La vista
        es el unico punto del sistema que conoce `CategorizerFactory`;
        `TransactionService` solo conoce la ABC `Categorizer` y no puede nombrar
        una implementacion concreta ni la fabrica. Esa asimetria es lo que hace
        que cambiar `CATEGORIZER_PROVIDER` altere el comportamiento del sistema
        sin tocar una linea de la capa de servicios ni del dominio.
        """
        return TransactionService(CategorizerFactory.get_categorizer())

    def get(self, request):
        """Lista las transacciones del usuario, con filtros opcionales."""
        filters = TransactionFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)

        movements = self.build_service().list_transactions(
            request.user, **filters.validated_data
        )

        # Paginacion explicita en cuatro lineas, en vez de heredar de un generico:
        # la APIView da control, que es justo lo que ADR-05 busca en este endpoint.
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(movements, request, view=self)
        return paginator.get_paginated_response(
            TransactionOutputSerializer(page, many=True).data
        )

    def post(self, request):
        """Registra una transaccion y devuelve 201."""
        serializer = TransactionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        movement = self.build_service().register_transaction(
            user=request.user,
            account_id=serializer.validated_data["account_id"],
            amount=serializer.validated_data["amount"],
            transaction_type=serializer.validated_data["type"],
            occurred_on=serializer.validated_data["occurred_on"],
            description=serializer.validated_data["description"],
            category_name=serializer.validated_data.get("category_name"),
        )
        return Response(
            TransactionOutputSerializer(movement).data, status=status.HTTP_201_CREATED
        )


class TransactionDetailAPIView(APIView):
    """`/api/v1/transactions/{id}/` — consulta y eliminacion."""

    def build_service(self):
        """Construye el servicio con el categorizador de la fabrica."""
        return TransactionService(CategorizerFactory.get_categorizer())

    def get(self, request, pk):
        """Devuelve una transaccion del usuario."""
        movement = self.build_service().get_transaction(request.user, pk)
        return Response(TransactionOutputSerializer(movement).data)

    def delete(self, request, pk):
        """Elimina la transaccion y deshace su efecto sobre el balance."""
        self.build_service().delete_transaction(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransactionCategorizeAPIView(APIView):
    """`/api/v1/transactions/{id}/categorize/` — reclasificacion manual."""

    def build_service(self):
        """Construye el servicio con el categorizador de la fabrica."""
        return TransactionService(CategorizerFactory.get_categorizer())

    def post(self, request, pk):
        """Reasigna la categoria de la transaccion. No mueve el balance."""
        serializer = RecategorizeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        movement = self.build_service().recategorize(
            request.user, pk, serializer.validated_data["category_name"]
        )
        return Response(TransactionOutputSerializer(movement).data)
