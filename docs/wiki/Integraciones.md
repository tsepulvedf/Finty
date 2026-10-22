# Integraciones

Toda dependencia externa entra por un **puerto** (una ABC en el `domain/` del servicio) y se implementa en un **adaptador** de su `infra/`. Cada puerto tiene un respaldo que no depende de la red: si el tercero cae, el resultado se degrada, pero el caso de uso no falla.

## API de terceros: TRM por Adapter (`recommendation-service`)

| | |
|---|---|
| Tercero | TRM oficial de datos.gov.co (`https://www.datos.gov.co/resource/32sa-8pi3.json`) |
| Puerto | `ExchangeRateProvider` |
| Adaptador | `TrmExchangeRateProvider`: timeout de 3 s; traduce la respuesta al value object `ExchangeRate` de Finty |
| Respaldo | `FixedExchangeRateProvider`: 3200 COP por dólar (la TRM del 2026-10-21, 3163,76, redondeada), configurable con `EXCHANGE_RATE_FALLBACK_USD_COP` |
| Caché | Redis, base 0: `finty:fx:USD-COP:day:<fecha>` (hasta la medianoche) y `finty:fx:USD-COP:last` (la última conocida) |
| Ruta | `GET /api/v1/exchange-rates/?base=USD&target=COP` |

`ExchangeRateService` recorre la cadena caché del día → API → última conocida → tasa fija. Cada respuesta dice su procedencia: `live`, `cached` o `fallback`. La pantalla muestra esa fuente y nunca convierte un monto guardado: la conversión es solo de presentación (INV-11).

```bash
EXCHANGE_RATE_API_URL=http://127.0.0.1:9 docker compose up -d recommendation-service   # API inalcanzable
curl -H "Authorization: Token $TOKEN" "http://localhost/api/v1/exchange-rates/?base=USD&target=COP"
# {"rate": "3163.76", "source": "cached", ...}  y sin caché: {"rate": "3200", "source": "fallback", ...}
```

Evidencia: [`runs/2026-10-21-recomendaciones-y-tasas.txt`](https://github.com/tsepulvedf/Finty/blob/main/tests/contract/runs/2026-10-21-recomendaciones-y-tasas.txt).

## Endpoint expuesto: resumen público con k-anonimato (`analytics-service`)

`GET /api/v1/public/spending-summary/?period=AAAA-MM`, **sin autenticación**, publica el gasto agregado por categoría y moneda de todos los usuarios: número de usuarios, total y promedio por usuario.

- **Privacidad:** una categoría solo aparece si la tienen **al menos k = 3 usuarios distintos** (`ANALYTICS_PUBLIC_MIN_USERS`). Tampoco se publica un total general del período: restándole las categorías visibles revelaría la suma de las ocultas.
- **Gateway:** sin `auth_request` y con su propia zona estricta, `finty_public` (30 por minuto). Nunca reenvía un `X-User-Id`.
- **Contrato provisional:** se ajusta cuando se asigne el equipo aliado (D-10).

```bash
curl "http://3.95.100.48/api/v1/public/spending-summary/?period=2026-10"
```

## Servicio del equipo aliado

**Pendiente de asignación del equipo aliado; no implementado.** El diseño previsto es un puerto `AllyServiceProvider` con un `MockAllyAdapter` de respaldo. Ni el puerto ni el mock existen en el código, y ninguna pantalla consume un servicio aliado. El adaptador concreto se escribirá cuando lleguen el dominio, la URL y el contrato del aliado (ADR-13, D-10).

## Pagos simulados (`subscription-service`)

Es un ejercicio académico: **no hay pasarela real**. El puerto `PaymentGateway` tiene una sola implementación, `MockPaymentGateway`, que aprueba al instante. `PaymentGatewayFactory` la elige con `PAYMENT_GATEWAY=MOCK`, y cualquier otro valor impide arrancar el servicio. Una pasarela real se agregaría como otro adaptador sin tocar el dominio (OCP). Wompi se evaluó y se descartó (ADR-14).

**Salvaguardas para que nunca viaje un dato de tarjeta:**

1. **Backend:** `POST /api/v1/subscriptions/checkout/` acepta **solo `{plan}`**. Su esquema (`extra="forbid"`) responde 400 a cualquier otro campo, sin repetir el valor recibido y sin encadenar la excepción que lo guarda, para que no termine en un log.
2. **Formulario:**
   - Los campos de la tarjeta no tienen `name` y llevan `autocomplete="off"`.
   - Su formato se valida solo en el navegador.
   - El aviso "Modo demostración: no se realiza ningún cobro" está visible antes de escribir.
3. **Tests:**
   - Uno inspecciona el JavaScript del checkout y falla si arma un cuerpo con algo más que `plan`, o si usa `fetch`, `FormData`, el almacenamiento o la consola.
   - El recorrido en Chrome confirmó en la pestaña Network que la petición solo lleva `{"plan": "PREMIUM"}`.

La suscripción solo pasa a ACTIVE con el pago aprobado (INV-05), y confirmar dos veces el mismo pago no regala otro mes.
