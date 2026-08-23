"""Router raiz de `/api/v1/` — API Gateway de Etapa 1 (ADR-06).

Punto de entrada unico del contrato REST. El cliente solo conoce `/api/v1/`;
que detras haya un monolito o varios servicios es invisible desde aqui.
"""
from django.urls import include, path
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

API_VERSION = "v1"


class HealthView(APIView):
    """Sonda de disponibilidad. Publica: no exige autenticacion."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        """Reporta que la API responde y con que version del contrato."""
        return Response({"status": "ok", "version": API_VERSION})


urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("", include("identity.api.urls")),
    path("", include("finance.api.urls")),
]
