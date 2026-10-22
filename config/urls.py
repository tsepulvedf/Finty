"""Enrutamiento raiz del proyecto — API Gateway de Etapa 1 (ADR-06).

El versionado `/api/v1/` es obligatorio desde el dia 1: permite enrutar una
futura `/api/v2/` a otro backend sin romper clientes (Strangler Pattern).

**Frontend (ADR-11, E2-M8).** Las paginas son `TemplateView` sin contexto: la
plantilla aporta estructura y textos traducidos con gettext, y su JavaScript pide
los datos a `/api/v1/` desde el navegador, en el mismo origen y por el Gateway
(sin CORS). Las rutas viven aqui porque no son parte del contrato REST de ningun
contexto de negocio, sino configuracion del proyecto.
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from django.views.i18n import JavaScriptCatalog


def page(template):
    """Una pagina del frontend: la plantilla tal cual, sin datos de negocio.

    Los nombres de ruta llevan el prefijo `page-` porque identity ya usa `login`
    y `register` para su API: sin el prefijo, `{% url 'login' %}` resolveria a
    `/api/v1/auth/login/`.
    """
    return TemplateView.as_view(template_name=f"finty/{template}")


urlpatterns = [
    path("", page("login.html"), name="page-login"),
    path("registro/", page("register.html"), name="page-register"),
    path("dashboard/", page("dashboard.html"), name="page-dashboard"),
    path("movimientos/", page("transactions.html"), name="page-transactions"),
    path("insights/", page("insights.html"), name="page-insights"),
    path("planes/", page("plans.html"), name="page-plans"),
    path("pago/", page("checkout.html"), name="page-checkout"),
    path("bienvenida/", page("welcome.html"), name="page-welcome"),
    # Selector ES/EN: `set_language` guarda la eleccion en la cookie de idioma.
    path("i18n/", include("django.conf.urls.i18n")),
    # Textos de JavaScript (`gettext()` en el navegador), del dominio djangojs.
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.api.urls")),
    # Solo para el Gateway (ADR-09); Nginx bloquea `/internal/` desde fuera.
    path("internal/", include("identity.api.internal_urls")),
]
