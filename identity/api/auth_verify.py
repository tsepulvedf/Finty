"""Verificacion de token para el subrequest auth_request de Nginx."""
from rest_framework.response import Response
from rest_framework.views import APIView


class AuthVerifyAPIView(APIView):
    def get(self, request):
        return Response(status=204)
