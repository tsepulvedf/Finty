"""Rutas del contrato REST de `identity`, montadas bajo `/api/v1/`.

Los prefijos `auth/` y `profile/` los define este modulo, no el router raiz, que
incluye estas rutas en `path("")`. El resultado son `/api/v1/auth/register/`,
`/api/v1/auth/login/` y `/api/v1/profile/`, tal como manda el contrato de rutas
de ARCHITECTURE.md 10.2.
"""
from django.urls import path

from identity.api.views import LoginAPIView, ProfileAPIView, RegisterAPIView

urlpatterns = [
    path("auth/register/", RegisterAPIView.as_view(), name="register"),
    path("auth/login/", LoginAPIView.as_view(), name="login"),
    path("profile/", ProfileAPIView.as_view(), name="profile"),
]
