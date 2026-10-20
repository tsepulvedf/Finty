"""Rutas internas de `identity`, montadas bajo `/internal/`.

No son parte del contrato `/api/v1/`: solo las consume el Gateway por la red
interna de Compose. Nginx responde 404 a cualquier `/internal/` que llegue de
fuera (ADR-09).
"""
from django.urls import path

from identity.api.views import GatewayAuthVerifyAPIView

urlpatterns = [
    path("auth/verify/", GatewayAuthVerifyAPIView.as_view(), name="gateway-auth-verify"),
]
