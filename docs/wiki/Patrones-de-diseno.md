# Patrones de diseño

Cada patrón con el archivo y la línea donde vive. Los enlaces apuntan a la rama `main`; [`tools/check_wiki_links.py`](https://github.com/tsepulvedf/Finty/blob/main/tools/check_wiki_links.py) comprueba que cada línea citada siga existiendo.

## Factory Method

**Para qué:** elegir una implementación por configuración sin que el caso de uso la conozca. Un valor desconocido detiene el arranque o la petición con `ConfigurationError` en lugar de caer en silencio a otra opción.

| Dónde | Archivo |
|---|---|
| `CategorizerFactory`, elige `RULE`, `MOCK` o `AI` según `CATEGORIZER_PROVIDER` | [`services/categorization-service/infra/factories.py:72`](https://github.com/tsepulvedf/Finty/blob/main/services/categorization-service/infra/factories.py#L72) |
| `get_categorizer()`, el método de fábrica | [`services/categorization-service/infra/factories.py:81`](https://github.com/tsepulvedf/Finty/blob/main/services/categorization-service/infra/factories.py#L81) |
| El blueprint le pide el categorizador y se lo pasa al servicio | [`services/categorization-service/api/routes.py:37`](https://github.com/tsepulvedf/Finty/blob/main/services/categorization-service/api/routes.py#L37) |
| `PaymentGatewayFactory`, solo acepta `PAYMENT_GATEWAY=MOCK` | [`services/subscription-service/infra/factories.py:25`](https://github.com/tsepulvedf/Finty/blob/main/services/subscription-service/infra/factories.py#L25) |
| `get_gateway()`, llamado una vez en `create_app()` | [`services/subscription-service/infra/factories.py:31`](https://github.com/tsepulvedf/Finty/blob/main/services/subscription-service/infra/factories.py#L31), [`services/subscription-service/app.py:116`](https://github.com/tsepulvedf/Finty/blob/main/services/subscription-service/app.py#L116) |

## Builder

**Para qué:** armar una entidad paso a paso y validar **todas** sus invariantes en `build()`, antes de que exista. El builder devuelve un borrador (`TransactionDraft`, `AccountDraft`), no un modelo del ORM: el dominio no conoce la persistencia (A-09).

| Dónde | Archivo |
|---|---|
| `TransactionBuilder` | [`services/finance-service/domain/builders.py:40`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/domain/builders.py#L40) |
| `TransactionBuilder.build()`: monto distinto de cero y positivo, moneda de la cuenta, fecha no futura y cuenta activa | [`services/finance-service/domain/builders.py:185`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/domain/builders.py#L185) |
| `AccountBuilder` y su `build()` | [`services/finance-service/domain/builders.py:256`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/domain/builders.py#L256), [`:326`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/domain/builders.py#L326) |
| Uso en `TransactionService.register_transaction` | [`services/finance-service/services.py:633`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/services.py#L633) |

## Adapter

**Para qué:** traducir una API ajena (otro servicio, un tercero, un mecanismo de envío) a un puerto del dominio. El caso de uso depende de la ABC, y cada adaptador maneja la falla de su lado, ya sea con respaldo o con una excepción del dominio.

| Puerto (ABC) | Adaptador | Qué traduce |
|---|---|---|
| [`ExchangeRateProvider`](https://github.com/tsepulvedf/Finty/blob/main/services/recommendation-service/domain/interfaces.py#L24) | [`TrmExchangeRateProvider`](https://github.com/tsepulvedf/Finty/blob/main/services/recommendation-service/infra/exchange_rates.py#L43) y [`FixedExchangeRateProvider`](https://github.com/tsepulvedf/Finty/blob/main/services/recommendation-service/infra/exchange_rates.py#L85) | La TRM de datos.gov.co a `ExchangeRate`, y la tasa fija de respaldo |
| [`Categorizer`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/domain/interfaces.py#L13) | [`RemoteCategorizer`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/infra/categorization_client.py#L47), armado en [`api/routes.py:53`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/api/routes.py#L53) | `POST /v1/suggestions/` de `categorization-service`, con `RuleBasedCategorizer` local de respaldo |
| [`PaymentGateway`](https://github.com/tsepulvedf/Finty/blob/main/services/subscription-service/domain/interfaces.py#L27) | [`MockPaymentGateway`](https://github.com/tsepulvedf/Finty/blob/main/services/subscription-service/infra/gateways.py#L12) | La pasarela simulada (ADR-14) |
| `AnalyticsReader` | [`HttpAnalyticsReader`](https://github.com/tsepulvedf/Finty/blob/main/services/recommendation-service/infra/analytics_client.py#L44) | Los insights y patrones de `analytics-service`, con degradación si cae |
| `EntitlementsReader` | [`HttpEntitlementsReader`](https://github.com/tsepulvedf/Finty/blob/main/services/analytics-service/infra/entitlements.py#L45) (también en [`recommendation-service`](https://github.com/tsepulvedf/Finty/blob/main/services/recommendation-service/infra/entitlements.py#L45)) | Los derechos premium de `subscription-service`, con caché en Redis |
| `ContactDirectory` | [`HttpContactDirectory`](https://github.com/tsepulvedf/Finty/blob/main/services/subscription-service/infra/contacts.py#L19) | El contacto del usuario en `identity` |
| `ReportRenderer` | [`CsvReportRenderer`](https://github.com/tsepulvedf/Finty/blob/main/services/analytics-service/infra/report_csv.py#L77) | El reporte del dominio a CSV |
| `AllyServiceProvider` | — | **Pendiente de asignación del equipo aliado; no implementado** (ADR-13) |

## Service Layer

**Para qué:** que cada caso de uso tenga un solo lugar. Las vistas y los blueprints solo validan, piden dependencias, llaman al servicio y traducen a HTTP (A-02); las reglas están en el dominio.

| Servicio | Archivo |
|---|---|
| `ProfileService` (monolito) | [`identity/services.py:44`](https://github.com/tsepulvedf/Finty/blob/main/identity/services.py#L44) |
| `AccountService` | [`services/finance-service/services.py:248`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/services.py#L248) |
| `TransactionService` y `register_transaction` | [`services/finance-service/services.py:596`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/services.py#L596), [`:613`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/services.py#L613) |
| `ReportService` | [`services/analytics-service/services.py:269`](https://github.com/tsepulvedf/Finty/blob/main/services/analytics-service/services.py#L269) |
| `ExchangeRateService` (la cadena de degradación, en `_resolve`) | [`services/recommendation-service/services.py:57`](https://github.com/tsepulvedf/Finty/blob/main/services/recommendation-service/services.py#L57), [`:86`](https://github.com/tsepulvedf/Finty/blob/main/services/recommendation-service/services.py#L86) |
| `RecommendationService` | [`services/recommendation-service/services.py:163`](https://github.com/tsepulvedf/Finty/blob/main/services/recommendation-service/services.py#L163) |
| `SubscriptionService.checkout` | [`services/subscription-service/services.py:107`](https://github.com/tsepulvedf/Finty/blob/main/services/subscription-service/services.py#L107), [`:141`](https://github.com/tsepulvedf/Finty/blob/main/services/subscription-service/services.py#L141) |

## Outbox transaccional

**Para qué:** publicar un evento **si y solo si** el cambio de negocio se confirmó. Más detalle en [Eventos y tareas asíncronas](Eventos-y-tareas-asincronas).

| Pieza | Archivo |
|---|---|
| Puerto `EventOutbox` | [`services/finance-service/domain/interfaces.py:58`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/domain/interfaces.py#L58) |
| `SqlAlchemyOutbox`, escribe en la misma sesión | [`services/finance-service/infra/outbox.py:12`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/infra/outbox.py#L12) |
| Tabla `outbox_event` | [`services/finance-service/models.py:217`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/models.py#L217) |
| El evento se registra dentro de la transacción del movimiento | [`services/finance-service/services.py:665`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/services.py#L665) |
| `OutboxRelay`, publica en Redis Streams | [`services/finance-service/services.py:817`](https://github.com/tsepulvedf/Finty/blob/main/services/finance-service/services.py#L817) |
| `EventProjector` y `EventConsumer` del otro lado (idempotentes por `event_id`) | [`services/analytics-service/services.py:61`](https://github.com/tsepulvedf/Finty/blob/main/services/analytics-service/services.py#L61), [`:139`](https://github.com/tsepulvedf/Finty/blob/main/services/analytics-service/services.py#L139) |
