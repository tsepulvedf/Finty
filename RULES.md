# Finty — Reglas de trabajo

Aplicación B2C de finanzas personales. Desde la Entrega 2: monolito Django (`identity`, frontend, verificación de auth) más microservicios Flask, detrás de un Gateway Nginx y desplegados con Docker Compose en AWS EC2.
Entregable académico evaluado sobre arquitectura limpia, SOLID y patrones creacionales.

**Antes de escribir código de dominio, servicios o patrones: lee `docs/ARCHITECTURE.md`.**
Ese documento es la fuente única de verdad. Si algo aquí y allá se contradicen, manda `docs/ARCHITECTURE.md`.

---

## Reglas inviolables

Las reglas 1 a 6 aplican igual al monolito y a cada microservicio Flask. En Flask, los blueprints ocupan el lugar de las views, los modelos SQLAlchemy el de `models.py` y la validación de entrada el de los serializers.

### 1. `domain/` es Python puro
`core/domain/` **no importa Django**. Ni `models`, ni `settings`, ni `timezone`, ni nada.
Verificación: `grep -rn "django" core/domain/` debe devolver vacío.
En cada servicio Flask, `domain/` **no importa Flask, SQLAlchemy ni su propio `infra/`**. Se verifica por AST en la suite del servicio (A-16).

### 2. `models.py` solo persiste
Únicamente: campos, `Meta`, `constraints`, relaciones, `__str__`.
**Prohibido**: métodos de negocio, `save()` sobreescrito con lógica, `clean()` con reglas, `@property` que calcule algo del negocio, signals (`post_save`, `pre_save`).
En SQLAlchemy: columnas, `__table_args__`, constraints, relaciones y `__repr__`. Sin métodos de negocio, `@hybrid_property` de negocio ni listeners de eventos del ORM.
Un solo método de negocio en un modelo cuesta el 50% de la nota de esta sección.

### 3. Las views no piensan
Una view solo: valida con el serializer, obtiene dependencias de la factory, llama al service, traduce el resultado a HTTP.
**Prohibido en views** (y en blueprints): cálculos, `if` sobre reglas de negocio, queries con lógica, orquestación de varios pasos.

### 4. Los serializers validan sintaxis, no semántica
Formato, tipos, campos requeridos → serializer (o validación de entrada del blueprint).
Reglas de negocio ("el monto no puede ser cero", "la cuenta debe ser tuya") → service o dominio.
**Prohibido**: `validate_*()` que consulte la base de datos para aplicar una regla de negocio.

### 5. La lógica de negocio vive en `services.py` y `domain/`
Los services orquestan casos de uso. El dominio contiene las reglas.

### 6. Dependencias hacia adentro
`views` → `services` → `domain`. Nunca al revés.
`domain/interfaces.py` define ABCs; `infra/` las implementa. Los services dependen de la ABC, jamás de la implementación concreta.

### 7. Apps, servicios y fronteras
**Apps Django:** solo `core` e `identity`. `finance` dejó de ser una app de Django en E2-M3a: el contexto vive en `finance-service` (ADR-08). No se vuelve a crear en el monolito.
**Microservicios Flask:** `finance-service`, `categorization-service`, `analytics-service`, `recommendation-service` y `subscription-service`. `analytics`, `recommendation` y `subscription` existen **solo** como servicios Flask: **no crear** apps Django, modelos ni scaffolding de esos contextos en el monolito. Cada servicio se construye en su módulo y no antes.
**Fronteras entre servicios:**
- Ningún servicio consulta la base de datos de otro. Cada uno tiene su base lógica y solo conoce su URL (ADR-10).
- Los servicios se comunican **solo** por HTTP en la red interna de Docker o por eventos en Redis.
- Los servicios Flask **confían en `X-User-Id`** y no validan tokens. Esa cabecera la pone Nginx tras `auth_request` (ADR-09).
- Los servicios Flask **no exponen puertos al host**: solo se llega a ellos a través de Nginx.

### 8. No inventes alcance
No agregues features, endpoints, modelos ni campos que no estén en `docs/ARCHITECTURE.md` o en el prompt del módulo actual.
Si algo parece faltar, dilo en la respuesta en vez de improvisarlo. Lo marcado como abierto en `docs/ARCHITECTURE.md` §13 (por ejemplo, el contrato del equipo aliado) no se rellena con supuestos.

---

## Convenciones

**Nomenclatura**: identificadores en inglés, siguiendo el glosario de `docs/ARCHITECTURE.md` §12. Los sinónimos prohibidos ahí están prohibidos de verdad.
Colisión conocida: `from django.db import transaction as db_transaction`, porque `Transaction` es una entidad del dominio.

**Idioma**: código en inglés. Docstrings y comentarios en español. Los textos que ve el usuario pasan siempre por gettext (`es` y `en`); ninguno queda quemado.

**Value Objects**: `@dataclass(frozen=True)`. Inmutables de verdad. Las enumeraciones del dominio son `enum.StrEnum` (C-15).

**Dinero**: siempre `Decimal`, nunca `float`. `DecimalField(max_digits=14, decimal_places=2)`; en SQLAlchemy, `Numeric(14, 2)`.

**IDs**: `UUIDField(primary_key=True, default=uuid4, editable=False)`; en SQLAlchemy, UUID con `default=uuid4`. Las referencias a entidades de otro servicio (por ejemplo `user_id`) son UUID **sin FK**.

**Excepciones**: el dominio lanza subclases de `DomainError` (`core/domain/exceptions.py`), nunca excepciones de Django, DRF, Flask ni SQLAlchemy. El handler global de cada unidad las traduce a HTTP.

**Python**: 3.11 en todo el sistema; imágenes `python:3.11-slim`.

**Zona horaria de los servicios Flask**: cada `create_app()` fija la zona del proceso a `TIME_ZONE` (`America/Bogota` por defecto) con `os.environ["TZ"]` y `time.tzset()`, como hace Django con sus settings. Los contenedores corren en UTC, y cualquier "hoy" del dominio (por ejemplo, INV-12) usa la zona del proceso: sin esto, desde las 19:00 de Bogotá el servicio ya estaría en el día siguiente. Un test por servicio lo verifica.

**Tests**: `pytest` + `pytest-django` en el monolito; `pytest` en cada servicio Flask. Los tests de dominio no tocan la base de datos.

**Dependencias**: cada unidad tiene su propio `requirements.txt`. No instalar paquetes fuera de él sin decirlo explícitamente en la respuesta.

---

## Commits

Convención semántica, en español, uno por unidad lógica:

```
feat(finance): agregar TransactionBuilder con validación de invariantes
refactor(identity): extraer lógica de perfil a ProfileService
docs(arch): documentar decisión de balance persistido
test(finance): cubrir INV-07 balance consistente
chore(config): configurar DRF y manejo de excepciones
```

No agrupes cambios heterogéneos en un solo commit. No incluyas coautoría ni firmas generadas.

---

## Al terminar un módulo

Reporta en la respuesta:
1. Archivos creados o modificados.
2. Comandos para verificar que funciona (tests, `docker compose`, `curl`).
3. Cualquier decisión que tomaste y no estaba especificada.
4. Cualquier regla de este archivo que te haya obligado a resolver algo de forma no obvia.
5. Secuencia de commits sugerida para el módulo.
