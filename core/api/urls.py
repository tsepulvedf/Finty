"""Router raiz de `/api/v1/` — API Gateway de Etapa 1 (ADR-06).

Punto de entrada unico del contrato REST. El cliente solo conoce `/api/v1/`; que
detras haya un monolito o varios servicios es invisible desde aqui.

**Las cuatro funciones criticas de un API Gateway y como se realiza cada una hoy**
(ARCHITECTURE.md 10.1). Un Gateway no es necesariamente una pieza de
infraestructura aparte: es un conjunto de responsabilidades, y en la Etapa 1 las
cumple este modulo junto con la configuracion de DRF.

1. **Autenticacion y autorizacion.** `DEFAULT_PERMISSION_CLASSES` de DRF fija
   `IsAuthenticated` para todo el proyecto, asi que una vista nueva nace
   protegida y hay que abrirla explicitamente para que no lo este. Eso
   materializa INV-01. Las dos unicas excepciones son deliberadas y estan
   marcadas con `AllowAny`: la sonda de salud de este modulo y los endpoints de
   registro y acceso de `identity`. En produccion esta funcion se movera al borde
   —validar el token una sola vez en la entrada del Gateway— pero la regla de
   negocio no cambia.

2. **Rate limiting.** `DEFAULT_THROTTLE_RATES` en `settings`, con cuotas
   separadas para trafico anonimo y autenticado. Es una defensa de aplicacion:
   protege la logica, no el ancho de banda. La contencion de trafico bruto es de
   Nginx en la Etapa 2.

3. **Abstraccion del enrutamiento.** Este archivo monta las rutas de `identity`
   bajo `/api/v1/`. Desde la Entrega 2 el enrutamiento entre servicios lo hace
   Nginx: `accounts`, `transactions` y `categories` las sirve `finance-service`
   desde la conmutacion de E2-M2b, y la app `finance` se retiro del monolito en
   E2-M3a (ADR-08). El cliente sigue pidiendo `/api/v1/...` sin saber quien
   responde.

4. **Agregacion de datos.** No aplica en un monolito: una peticion se resuelve
   contra una sola base y no hay nada que consolidar. Sera relevante cuando el
   dashboard tenga que componer datos de `finance` con los contextos de analitica
   y suscripcion de la Entrega 2, y esa composicion pertenece al Gateway y no al
   cliente.

**El versionado es parte del Gateway, no del cliente.** `/api/v1/` existe desde
el primer dia precisamente para que la Etapa 2 pueda enrutar `/api/v2/` a otro
backend mientras `/api/v1/` sigue apuntando aqui.
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
]
