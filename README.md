# Finty

Plataforma web B2C de finanzas personales. Permite a una persona registrar sus cuentas y movimientos, clasificarlos automáticamente y consultar su balance consolidado. Está construida como un **monolito Django de grado empresarial** sobre una arquitectura por capas de tres anillos: un núcleo de dominio en Python puro que no conoce el framework, una capa de servicios que orquesta los casos de uso, y una capa externa con el ORM, la API REST y los adaptadores de infraestructura. Esa separación es el punto del proyecto: cambiar de framework debería tocar únicamente el anillo más externo.

---

## Stack

| Componente | Versión |
|---|---|
| Python | 3.11.3 |
| Django | 5.2.11 |
| Django REST Framework | 3.17.1 |
| PostgreSQL | 18.6 |
| psycopg2-binary | 2.9.10 |
| python-dotenv | 1.2.2 |
| pytest · pytest-django · pytest-cov | 8.4.2 · 4.11.1 · 7.0.0 |

Sin dependencias fuera de `requirements.txt`. Sin llamadas de red salientes.

## Requisitos previos

- Python 3.11 o superior
- PostgreSQL 14 o superior

## Puesta en marcha

```bash
# 1. Entorno virtual
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux o macOS

# 2. Dependencias
pip install -r requirements.txt

# 3. Configuración
copy .env.example .env           # cp .env.example .env  en Linux o macOS

# 4. Generar una SECRET_KEY propia y pegarla en .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 5. Rol y base de datos
psql -U postgres -c "CREATE ROLE finty LOGIN PASSWORD 'la-que-pusiste-en-.env' CREATEDB;"
psql -U postgres -c "CREATE DATABASE finty OWNER finty ENCODING 'UTF8';"

# 6. Esquema y catálogo inicial de categorías
python manage.py migrate

# 7. Usuario administrador
python manage.py createsuperuser

# 8. Arrancar
python manage.py runserver
```

La API queda en `http://127.0.0.1:8000/api/v1/` y el admin en `http://127.0.0.1:8000/admin/`.

Comprobación rápida de que todo está en pie:

```bash
curl http://127.0.0.1:8000/api/v1/health/
# {"status":"ok","version":"v1"}
```

> El privilegio `CREATEDB` del paso 5 no es opcional: `pytest-django` crea una base `test_finty` aparte para correr la suite.

## Variables de entorno

Todas se leen de `.env` (ver `.env.example`). **No hay valores por defecto para las obligatorias**: si falta una, el arranque falla con un `RuntimeError` que la nombra, en lugar de continuar con una configuración insegura.

| Variable | Obligatoria | Descripción |
|---|---|---|
| `SECRET_KEY` | **Sí** | Clave criptográfica de Django. Debe ser distinta en cada entorno. |
| `DEBUG` | **Sí** | `True` o `False`. Siempre `False` en producción. |
| `ALLOWED_HOSTS` | **Sí** | Hosts autorizados, separados por coma. |
| `DB_NAME` | **Sí** | Nombre de la base PostgreSQL. |
| `DB_USER` | **Sí** | Rol de conexión. |
| `DB_PASSWORD` | **Sí** | Contraseña del rol. |
| `DB_HOST` | **Sí** | Host de PostgreSQL. |
| `DB_PORT` | **Sí** | Puerto de PostgreSQL. |

`.env` está en `.gitignore` y nunca debe versionarse.

## Ejecutar con Docker

Levanta el monolito, `finance-service`, `categorization-service`, `analytics-service` y `recommendation-service` (Flask), PostgreSQL 18, Redis y Nginx como Gateway. Solo Nginx publica un puerto en el host (el 80); el resto solo es alcanzable desde la red interna de Compose. Desde E2-M2b, Nginx envía todo el bloque `accounts`, `transactions` y `categories` a `finance-service`, después de verificar el token contra Django (`auth_request`). `/api/v1/analytics/` va a `analytics-service` con la misma verificación, y `/api/v1/public/` también, pero sin token. `/api/v1/recommendations/`, `/api/v1/investment-plans/` y `/api/v1/exchange-rates/` van a `recommendation-service`, con token. Las rutas de `identity` y el frontend siguen en Django. Es independiente de la puesta en marcha local: `.env` y el PostgreSQL del host siguen funcionando igual.

Requisitos: Docker Engine con Compose v2 (Docker Desktop en Windows) y el puerto 80 libre.

```bash
# 1. Configuración de Compose (independiente de .env)
cp .env.docker.example .env.docker
#    Edita .env.docker: SECRET_KEY propia y la misma contraseña en DB_PASSWORD y POSTGRES_PASSWORD.
cp services/finance-service/.env.docker.example services/finance-service/.env.docker
#    Edita DATABASE_URL con esa misma contraseña (escapada en formato URL si tiene símbolos).
cp services/analytics-service/.env.docker.example services/analytics-service/.env.docker
#    Igual: DATABASE_URL con la misma contraseña, hacia finty_analytics.
cp services/recommendation-service/.env.docker.example services/recommendation-service/.env.docker
#    Igual, hacia finty_recommendation.

# 2. Construir y arrancar. Las bases y las migraciones se crean solas antes de que
#    arranquen Django y los servicios Flask.
docker compose up -d --build

# 3. Comprobar
docker compose ps                                 # finance-service debe aparecer (healthy)
curl http://localhost/api/v1/health/
# {"status":"ok","version":"v1"}

# finance-service por la red interna (no publica puertos); cualquier UUID sirve de usuario
docker compose exec nginx wget -qO- --header "X-User-Id: 3f2b1c9e-0000-4000-8000-000000000001" http://finance-service:8000/api/v1/categories/

# 4. Usuario administrador (el admin queda en http://localhost/admin/)
docker compose exec django python manage.py createsuperuser
```

Otros comandos útiles:

```bash
docker compose logs -f django                                 # registros de un servicio
docker compose exec django python manage.py migrate           # migrar a mano (sin pendientes, no hace nada)
docker compose up -d --build                                  # reconstruir tras cambiar código o deploy/nginx/
docker compose down                                           # detener; los datos persisten en los volúmenes
docker compose down -v                                        # detener y BORRAR los datos de la base y de Redis
```

**Migraciones.** Las aplica el servicio de un solo uso `migrate`: corre `manage.py migrate`, termina, y `django` no arranca hasta que haya terminado con éxito. Así cada `up` deja el esquema al día, una migración fallida impide arrancar contra un esquema incompleto, y los workers de gunicorn nunca compiten por migrar.

`finance-migrate` hace lo mismo para `finance-service` con `alembic upgrade head`, incluida la siembra del catálogo de categorías; `analytics-migrate` y `recommendation-migrate` hacen lo mismo para sus servicios.

**Bases de datos.** `deploy/postgres/init/01-create-databases.sh` crea una base lógica por servicio (`finty_identity`, `finty_finance`, `finty_analytics`, `finty_recommendation`). Lo ejecuta PostgreSQL al inicializar un volumen vacío y, además, el paso de un solo uso `db-init` en cada `up`, así que una base nueva aparece también en un volumen que ya existe, sin pasos manuales. Para agregar la de un servicio nuevo, añádela a `FINTY_DATABASES` en ese script.

> En Git Bash para Windows, antepón `MSYS_NO_PATHCONV=1` a los comandos de `docker compose exec` que reciben rutas absolutas del contenedor; si no, Git Bash las reescribe como rutas de Windows.

**Estáticos.** `collectstatic` corre al construir la imagen de Django, y la etapa `gateway` del `Dockerfile` copia el resultado en la imagen de Nginx, que sirve `/static/` sin pasar por Django.

## Eventos de dominio

`finance-service` publica `TransactionManuallyAdded`, `TransactionCategorized` y `TransactionDeleted` en el Redis Stream `finty.finance.events`, con un outbox transaccional: el evento se escribe en la misma transacción que el cambio, y el contenedor `finance-outbox-relay` lo publica después. El contrato está en la §10.5 de [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```bash
docker compose exec redis redis-cli XRANGE finty.finance.events - +     # eventos publicados
docker compose logs -f finance-outbox-relay                             # el relay
docker compose exec finance-service flask outbox-backfill               # eventos de transacciones previas (idempotente)
```

Si Redis se detiene, las transacciones se siguen registrando y sus eventos quedan pendientes en `outbox_event`. Al volver Redis, el relay los publica. `finance-migrate` corre el backfill en cada `up`.

## Analytics y el endpoint público

`analytics-worker` consume `finty.finance.events` con el grupo de consumidores `analytics` y guarda una fila por transacción en `finty_analytics`. Nunca consulta `finty_finance`. `analytics-service` calcula al leer el dashboard, los insights y los gastos recurrentes; las reglas y sus umbrales están en la §6.5 de [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```bash
TOKEN=<token de /api/v1/auth/login/>
curl -H "Authorization: Token $TOKEN" "http://localhost/api/v1/analytics/dashboard/?period=2026-10"
curl -H "Authorization: Token $TOKEN" "http://localhost/api/v1/analytics/insights/?period=2026-10"
curl -H "Authorization: Token $TOKEN" "http://localhost/api/v1/analytics/spending-patterns/"

# Endpoint expuesto al equipo aliado: sin token, con k-anonimato (k = 3)
curl "http://localhost/api/v1/public/spending-summary/?period=2026-10"

docker compose logs -f analytics-worker                                       # el consumidor
docker compose exec redis redis-cli XINFO GROUPS finty.finance.events          # pendientes y lag del grupo
```

**Consistencia eventual.** Una transacción aparece en el dashboard unos instantes después de registrarla (en local, alrededor de un segundo). Si `analytics-worker` se detiene, `finance-service` sigue funcionando, y al volver el worker se pone al día. Reprocesar el stream completo no duplica nada: el worker descarta los `event_id` ya aplicados.

```bash
# Reprocesar toda la historia (idempotente)
docker compose stop analytics-worker
docker compose exec redis redis-cli XGROUP SETID finty.finance.events analytics 0
docker compose start analytics-worker
```

Los umbrales se cambian con variables `ANALYTICS_*` en `services/analytics-service/.env.docker`, por ejemplo `ANALYTICS_PUBLIC_MIN_USERS=5`.

## Recomendaciones y tasas de cambio

`recommendation-service` guarda el perfil de riesgo y los planes de inversión de cada usuario y calcula las recomendaciones al leer. Las de optimización salen de los insights y patrones de `analytics-service`, que lee por HTTP en la red interna; las de inversión, del excedente mensual y del perfil. Las tasas USD↔COP salen de la TRM oficial de datos.gov.co, detrás de un Adapter. Reglas, preguntas y umbrales: §6.6 y ADR-12 de [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```bash
curl -X PUT -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"investment_horizon":2,"loss_reaction":2,"experience":2,"income_stability":2,"goal":2}' \
  http://localhost/api/v1/recommendations/risk-profile/
curl -H "Authorization: Token $TOKEN" "http://localhost/api/v1/recommendations/?display_currency=USD"
curl -H "Authorization: Token $TOKEN" "http://localhost/api/v1/exchange-rates/?base=USD&target=COP"
```

Cada tasa dice de dónde salió: `live` (la API respondió en esa consulta), `cached` (salió de Redis: la del día o la última conocida) o `fallback` (la tasa fija `EXCHANGE_RATE_FALLBACK_USD_COP`, 3200: la TRM del 2026-10-21 redondeada). Si `analytics-service` no responde, `/recommendations/` contesta 200 con `degraded: true`.

```bash
# Simular la API de la TRM caída, sin editar archivos
EXCHANGE_RATE_API_URL=http://127.0.0.1:9 docker compose up -d recommendation-service
docker compose exec redis redis-cli KEYS 'finty:fx:*'      # caché del día y última conocida
docker compose up -d recommendation-service                 # volver a la API oficial
```

## Conmutar el categorizador

`CATEGORIZER_PROVIDER` selecciona qué implementación de `Categorizer` usa `categorization-service`. Es el Factory Method del proyecto y su efecto es observable desde fuera. `finance-service` le pide la categoría por HTTP y, si no responde, clasifica con sus reglas locales.

| Valor | Implementación | Qué hace |
|---|---|---|
| `RULE` | `RuleBasedCategorizer` | Determinista. Mapa de palabras clave separado por tipo de movimiento, insensible a tildes y mayúsculas. Sin red ni base de datos. Es el valor por defecto. |
| `MOCK` | `MockCategorizer` | Devuelve una categoría fija. Para desarrollo y pruebas, sin consumir cuota de inferencia. |
| `AI` | `AICategorizer` | Envuelve un proveedor externo inyectado. **En esta entrega no hay cliente concreto configurado**, así que opera en modo degradado y delega en el respaldo determinista. Nunca propaga excepciones. |
| cualquier otro | — | `ConfigurationError` al clasificar. Falla ruidosamente: en una aplicación financiera, degradar en silencio a un clasificador distinto del configurado es peor que no arrancar. |

Una línea cambia el comportamiento del sistema sin tocar código:

```bash
CATEGORIZER_PROVIDER=MOCK docker compose up -d categorization-service   # y RULE para volver
```

Sin la variable, el proveedor es `RULE`. Si `categorization-service` se detiene (`docker compose stop categorization-service`), las transacciones se siguen registrando con procedencia `rule`.

El mismo `POST /api/v1/transactions/` devolverá un `categorization_source` distinto —`rule` o `mock`— según el proveedor activo. El campo registra **el mecanismo que realmente clasificó**: cuando `AICategorizer` degrada a su respaldo, la procedencia grabada es `rule`, no `ai`.

## Tests

```bash
# Suite completa (requiere PostgreSQL)
pytest

# Solo el dominio: Python puro, sin base de datos
pytest core/tests/test_money.py

# Reglas de arquitectura por análisis de AST
pytest core/tests/test_architecture.py -v

# Cobertura
pytest --cov=. --cov-report=term-missing
```

Los tests de dominio no llevan la marca `django_db`, que es como `pytest-django` bloquea cualquier acceso a la base. Si un día el dominio empezara a consultarla, fallarían solos. Los tests de cuentas, transacciones y categorización viven desde E2-M3a en la suite de `finance-service` (abajo).

### Suite de contrato (caja negra)

`tests/contract/` prueba el contrato `/api/v1/` de los bloques finance y analytics a través del Gateway, sin saber quién responde detrás: es la evidencia de la conmutación (A-20). Los tests de analytics esperan la consistencia eventual sondeando con un límite de 15 s. Crea sus propios usuarios y no importa código de Finty.

```bash
# Con el stack de Docker arriba
cd tests/contract
CONTRACT_BASE_URL=http://localhost ../../venv/Scripts/python -m pytest -v

# Los tests de 429 agotan las cuotas de limit_req; van aparte
CONTRACT_BASE_URL=http://localhost CONTRACT_THROTTLE=1 ../../venv/Scripts/python -m pytest -m throttle
```

Las corridas de antes y después de la conmutación están en `tests/contract/runs/`. Cada corrida registra cuatro usuarios, que cuentan contra la cuota anónima de DRF (60 por hora y por IP) y contra la ráfaga de 10 de la zona `finty_auth` de Nginx. Si una corrida repetida recibe 429 en el registro, espera un minuto; la cuota de DRF vive en la memoria de `django` y se reinicia con `docker compose restart django`.

### Contratos estáticos entre servicios

`tests/services/` comprueba, leyendo el código fuente por AST, que toda categoría que puede emitir `categorization-service` esté sembrada en `finty_finance` con el mismo tipo (A-12), y que todo campo del evento que lee `analytics-service` lo escriba `finance-service` (A-25).

```bash
cd tests/services && ../../venv/Scripts/python -m pytest -v
```

### Tests de categorization-service

Sin base de datos. Mismo procedimiento que `finance-service`, sin `FINANCE_TEST_DATABASE_URL`:

```bash
cd services/categorization-service
py -3.11 -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest
```

### Tests de analytics-service

Mismo procedimiento que `finance-service`, con su propia base de pruebas:

```bash
cd services/analytics-service
py -3.11 -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest tests/domain tests/test_architecture.py     # sin base de datos
export ANALYTICS_TEST_DATABASE_URL="postgresql+psycopg2://finty:<clave>@localhost:5432/finty_analytics_test"
.venv/Scripts/python -m pytest
```

### Tests de recommendation-service

```bash
cd services/recommendation-service
py -3.11 -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest tests/domain tests/test_adapters.py tests/test_exchange_rate_service.py tests/test_architecture.py   # sin base
export RECOMMENDATION_TEST_DATABASE_URL="postgresql+psycopg2://finty:<clave>@localhost:5432/finty_recommendation_test"
.venv/Scripts/python -m pytest
```

Los adaptadores de la TRM y de analytics se prueban contra un servidor HTTP local con la forma real de cada respuesta: la suite no sale a internet.

### Tests de finance-service

`pytest` en la raíz corre solo el monolito (`testpaths` en `pytest.ini`). El servicio Flask tiene su propio entorno virtual y su propia suite:

```bash
cd services/finance-service
py -3.11 -m venv .venv                      # python3.11 -m venv .venv en Linux o macOS
.venv/Scripts/python -m pip install -r requirements.txt

# Dominio, categorización y arquitectura: sin base de datos
.venv/Scripts/python -m pytest tests/domain tests/categorization tests/test_architecture.py

# Suite completa: necesita una base de pruebas cuyo nombre termine en _test.
# La suite la borra, la recrea y la migra con Alembic al iniciar.
export FINANCE_TEST_DATABASE_URL="postgresql+psycopg2://finty:<clave>@localhost:5432/finty_finance_test"
.venv/Scripts/python -m pytest
```

## Estructura del proyecto

```
finty/
├── config/                     Proyecto Django. Settings, WSGI, ASGI y enrutamiento raíz.
├── core/                       Transversal a los contextos.
│   ├── domain/                 ANILLO INTERIOR · Python puro. Money, jerarquía de excepciones.
│   │                           Importa solo la stdlib. No conoce Django.
│   └── api/                    Handler global de excepciones y router de /api/v1/ (API Gateway).
├── identity/                   UserIdentityContext · contexto Generic.
│   ├── models.py               User (email como identificador) y UserProfile. Solo persistencia.
│   ├── exceptions.py           Módulo plano: no necesita un anillo de dominio completo.
│   ├── services.py             ProfileService. Registro, autenticación y perfil.
│   └── api/                    Serializers, views y rutas.
├── services/
│   ├── finance-service/        FinancialDataContext · contexto Core, en Flask (E2-M2a).
│       ├── domain/             ANILLO INTERIOR · Python puro. Value objects, reglas, builders,
│       │                       la ABC Categorizer y su copia de Money (domain/shared/).
│       ├── infra/              ANILLO EXTERNO · Cliente de categorization-service, respaldo local, sesión.
│       ├── models.py           Account, Transaction, Category en SQLAlchemy. Solo persistencia.
│       ├── services.py         ANILLO MEDIO · AccountService y TransactionService.
│       ├── commands.py         flask verify-invariants (auditoría de INV-07 e INV-08).
│       └── api/                ANILLO EXTERNO · Blueprints, esquemas y traducción de errores.
│   ├── categorization-service/ Categorización, en Flask y sin base de datos (E2-M3b).
│   │                           Categorizer, los tres categorizadores y CategorizerFactory.
│   ├── analytics-service/      AnalyticsInsightsContext, en Flask (E2-M4b). Dashboard, Insight,
│   │                           SpendingPattern, el worker de eventos y el resumen público.
│   └── recommendation-service/ RecommendationContext, en Flask (E2-M5). RiskProfile,
│                               Recommendation, InvestmentPlan y el Adapter de tasas (TRM).
├── deploy/                     Nginx (API Gateway) y la creación de bases de PostgreSQL.
├── tests/contract/             Suite de contrato de caja negra contra el Gateway.
└── docs/                       ARCHITECTURE.md y VERIFICATION.md.
```

**Regla de dependencia:** las flechas apuntan hacia adentro. `api/` → `services.py` → `domain/`, nunca al revés. `domain/interfaces.py` define las abstracciones y `infra/` las implementa, de modo que la dirección de la dependencia se invierte respecto al flujo de control. `core/tests/test_architecture.py` lo verifica recorriendo el AST de cada módulo.

## Alcance de la Entrega 1

**Implementado:** `identity` (parcial: identidad y perfil) y `finance` (completo: cuentas, transacciones, categorías, balance y clasificación). Once de las veinte clases del diagrama, el 55%. En la Entrega 2, `finance` se migró a `finance-service` y se retiró del monolito (ADR-08).

**Deliberadamente fuera:** analítica e insights, motor de recomendaciones y perfil de riesgo, suscripciones y pagos, e integraciones bancarias automáticas. Los contextos `analytics`, `recommendation` y `subscription` están documentados en la arquitectura pero no existen como código, y no deben crearse en esta entrega.

El detalle del corte y su justificación están en la §4 de [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Documentación

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — decisiones arquitectónicas, modelo de dominio, patrones creacionales, catálogo de invariantes, diagramas y glosario. Es la fuente única de verdad.
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md) — cada criterio de aceptación mapeado al test que lo demuestra y al comando que lo ejecuta.
- `RULES.md` — reglas de trabajo sobre el código.

## Licencia y autoría

<!-- PENDIENTE: definir licencia. -->
<!-- PENDIENTE: autoría y URL del repositorio. -->

Sin definir. Proyecto académico.
