"""Enrutamiento raiz del proyecto — API Gateway de Etapa 1 (ADR-06).

El versionado `/api/v1/` es obligatorio desde el dia 1: permite enrutar una
futura `/api/v2/` a otro backend sin romper clientes (Strangler Pattern).
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.api.urls")),
]
