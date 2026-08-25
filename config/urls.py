"""Enrutamiento raiz del proyecto — API Gateway de Etapa 1 (ADR-06).

El versionado `/api/v1/` es obligatorio desde el dia 1: permite enrutar una
futura `/api/v2/` a otro backend sin romper clientes (Strangler Pattern).

La raiz sirve el cliente de demostracion, que es una pagina estatica: pide sus
datos a `/api/v1/` como lo haria cualquier consumidor externo. Que el backend
siga siendo headless es precisamente lo que ese cliente demuestra.
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    # Cliente de demostracion. `TemplateView` sin `get_context_data`: sirve el
    # HTML tal cual, sin contexto. La ruta vive aqui y no en un `api/urls.py`
    # porque no es parte del contrato REST de ningun contexto de negocio, sino
    # configuracion del proyecto. Servirlo desde el mismo origen que la API es
    # ademas lo que evita necesitar CORS.
    path("", TemplateView.as_view(template_name="app.html"), name="client"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.api.urls")),
]
