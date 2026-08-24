"""Rutas del contrato REST de `finance`, montadas bajo `/api/v1/`.

Este modulo se incluye en `path("")` dentro de `core/api/urls.py`, asi que los
prefijos completos se definen aqui. El resultado coincide con el contrato de
rutas de ARCHITECTURE.md 10.2.

`categories` y `accounts` van por `DefaultRouter` porque son recursos CRUD con
forma estandar. Las de transacciones se declaran explicitamente: no son un
recurso REST plano sino tres operaciones con comportamiento propio, y el router
las envolveria en un `ViewSet` que no aporta nada aqui.

El convertidor `<uuid:pk>` hace que una ruta con forma invalida devuelva 404 sin
llegar siquiera a la vista.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from finance.api.views import (
    AccountViewSet,
    CategoryViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("accounts", AccountViewSet, basename="account")

urlpatterns = [
    path("", include(router.urls)),
]
