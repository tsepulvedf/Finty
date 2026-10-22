"""Rutas internas de `identity`, montadas bajo `/internal/`.

No son parte del contrato `/api/v1/`: solo las consumen el Gateway y los
servicios por la red interna de Compose (`auth/verify/` el Gateway;
`users/<id>/contact/` subscription-service, E2-M7). Nginx responde 404 a cualquier `/internal/` que llegue de
fuera (ADR-09).
"""
from django.urls import path

from identity.api.views import GatewayAuthVerifyAPIView, InternalContactAPIView

urlpatterns = [
    path("auth/verify/", GatewayAuthVerifyAPIView.as_view(), name="gateway-auth-verify"),
    path("users/<uuid:user_id>/contact/", InternalContactAPIView.as_view(), name="internal-user-contact"),
]
