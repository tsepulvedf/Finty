# Arquitectura

Finty combina dos ideas: **arquitectura limpia en tres anillos dentro de cada unidad** y **microservicios por contexto acotado** entre unidades. La fuente única de verdad es [`docs/ARCHITECTURE.md`](https://github.com/tsepulvedf/Finty/blob/main/docs/ARCHITECTURE.md).

## Los tres anillos

Cada unidad (el monolito Django y cada servicio Flask) tiene la misma forma:

| Anillo | Qué contiene | Qué puede importar |
|---|---|---|
| **Dominio** (`domain/`) | Entidades, value objects, reglas e invariantes, y los puertos (ABC) | Solo la biblioteca estándar y su propio dominio: **ni Django, ni Flask, ni SQLAlchemy** |
| **Servicios** (`services.py`) | Los casos de uso: orquestan el dominio y la persistencia | El dominio y las ABC; nunca una implementación concreta de `infra/` |
| **Entrada y adaptadores** (`api/`, `infra/`, `models.py`, `tasks.py`) | Vistas o blueprints, validación de sintaxis, modelos anémicos, adaptadores externos y tareas de Celery | Todo lo anterior; las dependencias siempre apuntan hacia adentro |

Las reglas se verifican sobre el AST en cada suite (A-15 y A-16):

- `domain/` no importa frameworks.
- Los blueprints no tienen `try` ni aritmética.
- Los modelos solo declaran columnas.
- Las tareas de Celery solo llaman a un caso de uso.

```mermaid
flowchart TB
    subgraph EXT["Infraestructura + Presentación"]
        URLS["config/urls.py<br/>API Gateway"]
        VIEWS["api/views.py<br/>Skinny Views"]
        SER["api/serializers.py<br/>Adapter"]
        MOD["models.py<br/>ORM"]
        INFRA["infra/categorizers.py<br/>infra/factories.py"]
    end

    subgraph APP["Servicios (Casos de uso)"]
        SVC["services.py"]
    end

    subgraph DOM["Dominio (Python puro)"]
        INT["domain/interfaces.py"]
        VO["domain/value_objects.py"]
        LOG["domain/logic.py"]
        BLD["domain/builders.py"]
    end

    URLS --> VIEWS
    VIEWS --> SER
    VIEWS --> SVC
    VIEWS -.->|obtiene impl| INFRA
    SVC --> BLD
    SVC --> LOG
    SVC --> MOD
    SVC -->|depende de la ABC| INT
    INFRA -.->|implementa| INT
    BLD --> VO
    LOG --> VO

    style DOM fill:#0d3b4f,color:#fff
    style APP fill:#1a7fa0,color:#fff
    style EXT fill:#cfe6ef,color:#000
```

## Topología de microservicios

| Unidad | Tecnología | Responsabilidad | Base |
|---|---|---|---|
| `django` | Django 5.2 + DRF | Identidad (registro, ingreso, perfil), frontend con gettext y verificación del Token para el Gateway | `finty_identity` |
| `finance-service` | Flask | Cuentas, movimientos y categorías; publica eventos de dominio | `finty_finance` |
| `categorization-service` | Flask | Clasifica un movimiento por su descripción | ninguna |
| `analytics-service` | Flask + Celery | Dashboard, insights, gastos recurrentes, reporte mensual y resumen público | `finty_analytics` |
| `recommendation-service` | Flask | Perfil de riesgo, recomendaciones, planes de inversión y tasas de cambio | `finty_recommendation` |
| `subscription-service` | Flask + Celery | Planes, checkout simulado, derechos premium, correos y vencimiento | `finty_subscription` |
| `nginx` | Nginx 1.28 | API Gateway: rutas, autenticación, límites y estáticos | — |

**Cómo se comunican:**
- **Por HTTP en la red interna:** `finance → categorization`, `recommendation → analytics`, `analytics` y `recommendation → subscription` (derechos premium) y `subscription → identity` (contacto para los correos).
- **Por eventos en Redis Streams:** `finance → analytics`.
- **Ningún servicio consulta la base de otro** (ADR-10).

```mermaid
flowchart TB
    U["Navegador<br/>(y servicio aliado, por asignar)"]

    subgraph AWS["AWS Academy · Learner Lab · región us-east-1"]
        EIP(["IP elástica 3.95.100.48"])
        subgraph SG["Grupo de seguridad: entrada 22/tcp (SSH) y 80/tcp (HTTP)"]
            subgraph EC2["Instancia EC2 · Docker Engine + Compose v2"]
                subgraph NET["Red de Compose finty_default (bridge, DNS interno)"]
                    NGX["nginx · API Gateway<br/>único puerto publicado: 80<br/>auth_request · limit_req · estáticos con hash"]
                    DJ["django<br/>identity · frontend · /internal/"]
                    FIN["finance-service"]
                    REL["finance-outbox-relay"]
                    CAT["categorization-service"]
                    ANA["analytics-service"]
                    ANW["analytics-worker<br/>consume el stream"]
                    ACW["analytics-celery<br/>+ analytics-celery-beat"]
                    REC["recommendation-service"]
                    SUB["subscription-service"]
                    SCW["subscription-worker<br/>+ subscription-beat"]
                    RDS[("redis 7.4 · AOF<br/>base 0: stream finty.finance.events,<br/>cachés finty:entitlements:* y finty:fx:*<br/>base 1: broker de Celery<br/>(colas analytics y subscription)")]
                    PG[("postgres 18<br/>finty_identity · finty_finance<br/>finty_analytics · finty_recommendation<br/>finty_subscription")]
                    ONE["Pasos de un solo uso:<br/>db-init, migrate, finance-migrate,<br/>analytics-migrate, recommendation-migrate,<br/>subscription-migrate"]
                end
            end
        end
    end
    TRM["API de la TRM<br/>datos.gov.co"]

    U -->|"HTTP :80"| EIP --> NGX
    NGX -->|"/ , /api/v1/auth, /api/v1/profile, auth_request"| DJ
    NGX -->|"accounts · transactions · categories"| FIN
    NGX -->|"analytics · public"| ANA
    NGX -->|"recommendations · investment-plans · exchange-rates"| REC
    NGX -->|subscriptions| SUB
    FIN -->|"POST /v1/suggestions/"| CAT
    FIN --> PG
    REL -->|"lee outbox_event"| PG
    REL -->|XADD| RDS
    RDS -->|XREADGROUP| ANW
    ANW --> PG
    ANA -->|"encola reportes"| RDS
    RDS --> ACW
    ACW --> PG
    ANA --> PG
    ANA -->|"/internal/entitlements"| SUB
    REC -->|"/internal/entitlements"| SUB
    REC -->|"HTTP + X-User-Id"| ANA
    REC --> PG
    REC -->|"TrmExchangeRateProvider"| TRM
    SUB -->|"encola la bienvenida"| RDS
    RDS --> SCW
    SCW -->|"/internal/users/id/contact/"| DJ
    SCW --> PG
    SUB --> PG
    DJ --> PG
    ONE --> PG
```

## Mapa de contextos

```mermaid
flowchart LR
    ID["UserIdentityContext<br/>Django · identity"]
    GW{{"Gateway Nginx<br/>identidad en X-User-Id"}}
    FD["FinancialDataContext<br/>finance-service"]
    CT["Categorización<br/>categorization-service"]
    AN["AnalyticsInsightsContext<br/>analytics-service"]
    RC["RecommendationContext<br/>recommendation-service"]
    SB["SubscriptionBillingContext<br/>subscription-service"]
    BUS[("Redis Streams<br/>finty.finance.events")]
    TRM["TRM datos.gov.co"]
    ALLY["Equipo aliado<br/>(por asignar)"]

    ID -->|"Customer-Supplier<br/>verifica el Token"| GW
    GW -->|X-User-Id| FD
    GW -->|X-User-Id| AN
    GW -->|X-User-Id| RC
    GW -->|X-User-Id| SB
    FD -->|"HTTP síncrono<br/>+ respaldo local (ACL)"| CT
    FD -.->|"publica (outbox)"| BUS
    BUS -.->|"Conformist: consume"| AN
    RC -->|"Customer: HTTP con degradación"| AN
    AN -->|"Customer: derechos INV-06"| SB
    RC -->|"Customer: derechos INV-06"| SB
    SB -->|"contacto para los correos"| ID
    RC -->|"Adapter + respaldo"| TRM
    ALLY -.->|"Open Host Service<br/>/api/v1/public/"| AN
```

## Decisiones principales (ADR)

| ADR | Decisión |
|---|---|
| ADR-07 | Microservicios Flask para los contextos nuevos y para `finance` |
| ADR-08 | Strangler por conmutación de ruta en Nginx: ver [Migración Strangler y bono del 70%](Migracion-Strangler-y-bono) |
| ADR-09 | Autenticación centralizada en el Gateway con `auth_request`: ver [API Gateway con Nginx](API-Gateway) |
| ADR-10 | Una base de datos lógica por servicio |
| ADR-11 | Frontend en plantillas Django con gettext: ver [Frontend, UX e i18n](Frontend-UX-e-i18n) |
| ADR-12 | Tasas de cambio por Adapter: ver [Integraciones](Integraciones) |
| ADR-14 | `PaymentGateway` con un pago simulado |
| ADR-15 | Eventos de dominio y tareas asíncronas: ver [Eventos y tareas asíncronas](Eventos-y-tareas-asincronas) |
| ADR-16 | Despliegue en Docker Compose sobre EC2: ver [Despliegue en EC2](Despliegue-en-EC2) |
