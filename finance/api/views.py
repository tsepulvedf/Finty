"""Views del contrato REST de `finance` (anillo externo).

Cada view hace exactamente cuatro cosas: validar con el serializer, obtener sus
dependencias, llamar al servicio y traducir el resultado a HTTP. Ningun calculo,
ningun `if` sobre reglas de negocio y **ningun `try/except`**: las excepciones de
dominio las traduce el handler global de `core/api/exception_handler.py`
(CLAUDE.md, regla 3).

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
