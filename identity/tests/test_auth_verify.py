"""Permisos de la sonda de autenticacion, sin persistencia."""
from types import SimpleNamespace
from uuid import uuid4

from rest_framework.test import APIRequestFactory, force_authenticate

from identity.api.auth_verify import AuthVerifyAPIView


def test_anonymous_is_rejected():
    request = APIRequestFactory().get("/api/v1/auth/verify/")
    assert AuthVerifyAPIView.as_view()(request).status_code == 401


def test_authenticated_is_allowed():
    request = APIRequestFactory().get("/api/v1/auth/verify/")
    force_authenticate(request, user=SimpleNamespace(pk=uuid4(), is_authenticated=True))
    assert AuthVerifyAPIView.as_view()(request).status_code == 204
