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
| `CATEGORIZER_PROVIDER` | No | Estrategia de clasificación. Por defecto `RULE`. Ver abajo. |

`.env` está en `.gitignore` y nunca debe versionarse.

## Conmutar el categorizador

`CATEGORIZER_PROVIDER` selecciona qué implementación de `Categorizer` inyecta la Factory. Es el Factory Method del proyecto y su efecto es observable desde fuera.

| Valor | Implementación | Qué hace |
|---|---|---|
| `RULE` | `RuleBasedCategorizer` | Determinista. Mapa de palabras clave separado por tipo de movimiento, insensible a tildes y mayúsculas. Sin red ni base de datos. Es el valor por defecto. |
| `MOCK` | `MockCategorizer` | Devuelve una categoría fija. Para desarrollo y pruebas, sin consumir cuota de inferencia. |
| `AI` | `AICategorizer` | Envuelve un proveedor externo inyectado. **En esta entrega no hay cliente concreto configurado**, así que opera en modo degradado y delega en el respaldo determinista. Nunca propaga excepciones. |
| cualquier otro | — | `ImproperlyConfigured` al arrancar. Falla ruidosamente: en una aplicación financiera, degradar en silencio a un clasificador distinto del configurado es peor que no arrancar. |

Una línea cambia el comportamiento del sistema sin tocar código:

```bash
CATEGORIZER_PROVIDER=MOCK python manage.py runserver
```

El mismo `POST /api/v1/transactions/` devolverá un `categorization_source` distinto —`rule` o `mock`— según el proveedor activo. El campo registra **el mecanismo que realmente clasificó**: cuando `AICategorizer` degrada a su respaldo, la procedencia grabada es `rule`, no `ai`.

## Tests

```bash
# Suite completa (requiere PostgreSQL)
pytest

# Solo el dominio: Python puro, sin base de datos
pytest core/tests/test_money.py \
       finance/tests/test_domain_value_objects.py \
       finance/tests/test_balance_calculator.py \
       finance/tests/test_transaction_rules.py \
       finance/tests/test_builders.py

# Reglas de arquitectura por análisis de AST
pytest core/tests/test_architecture.py -v

# Cobertura
pytest --cov=. --cov-report=term-missing
```

Los tests de dominio no llevan la marca `django_db`, que es como `pytest-django` bloquea cualquier acceso a la base. Si un día el dominio empezara a consultarla, fallarían solos.

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
├── finance/                    FinancialDataContext · contexto Core.
│   ├── domain/                 ANILLO INTERIOR · Python puro. Value objects, reglas, builders
│   │                           y la ABC Categorizer. Importa solo la stdlib y core.domain.
│   ├── infra/                  ANILLO EXTERNO · Categorizadores concretos y CategorizerFactory.
│   │                           Puede importar Django. El dominio nunca lo importa a él.
│   ├── models.py               Account, Transaction, Category. Campos, Meta y __str__.
│   ├── services.py             ANILLO MEDIO · AccountService y TransactionService.
│   │                           Depende de la ABC, jamás de una implementación concreta.
│   └── api/                    ANILLO EXTERNO · Serializers, views y rutas.
└── docs/                       ARCHITECTURE.md y VERIFICATION.md.
```

**Regla de dependencia:** las flechas apuntan hacia adentro. `api/` → `services.py` → `domain/`, nunca al revés. `domain/interfaces.py` define las abstracciones y `infra/` las implementa, de modo que la dirección de la dependencia se invierte respecto al flujo de control. `core/tests/test_architecture.py` lo verifica recorriendo el AST de cada módulo.

## Alcance de la Entrega 1

**Implementado:** `identity` (parcial: identidad y perfil) y `finance` (completo: cuentas, transacciones, categorías, balance y clasificación). Once de las veinte clases del diagrama, el 55%.

**Deliberadamente fuera:** analítica e insights, motor de recomendaciones y perfil de riesgo, suscripciones y pagos, e integraciones bancarias automáticas. Los contextos `analytics`, `recommendation` y `subscription` están documentados en la arquitectura pero no existen como código, y no deben crearse en esta entrega.

El detalle del corte y su justificación están en la §4 de [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Documentación

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — decisiones arquitectónicas, modelo de dominio, patrones creacionales, catálogo de invariantes, diagramas y glosario. Es la fuente única de verdad.
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md) — cada criterio de aceptación mapeado al test que lo demuestra y al comando que lo ejecuta.
- `CLAUDE.md` — reglas de trabajo sobre el código.

## Licencia y autoría

<!-- PENDIENTE: definir licencia. -->
<!-- PENDIENTE: autoría y URL del repositorio. -->

Sin definir. Proyecto académico.
