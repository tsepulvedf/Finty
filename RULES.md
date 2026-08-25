# Finty — Reglas de trabajo

Monolito Django de grado empresarial. Aplicación B2C de finanzas personales.
Entregable académico evaluado sobre arquitectura limpia, SOLID y patrones creacionales.

**Antes de escribir código de dominio, servicios o patrones: lee `docs/ARCHITECTURE.md`.**
Ese documento es la fuente única de verdad. Si algo aquí y allá se contradicen, manda `docs/ARCHITECTURE.md`.

---

## Reglas inviolables

### 1. `domain/` es Python puro
`core/domain/` y `finance/domain/` **no importan Django**. Ni `models`, ni `settings`, ni `timezone`, ni nada.
Verificación: `grep -rn "django" core/domain/ finance/domain/` debe devolver vacío.

### 2. `models.py` solo persiste
Únicamente: campos, `Meta`, `constraints`, relaciones, `__str__`.
**Prohibido**: métodos de negocio, `save()` sobreescrito con lógica, `clean()` con reglas, `@property` que calcule algo del negocio, signals (`post_save`, `pre_save`).
Un solo método de negocio en un modelo cuesta el 50% de la nota de esta sección.

### 3. Las views no piensan
Una view solo: valida con el serializer, obtiene dependencias de la factory, llama al service, traduce el resultado a HTTP.
**Prohibido en views**: cálculos, `if` sobre reglas de negocio, queries con lógica, orquestación de varios pasos.

### 4. Los serializers validan sintaxis, no semántica
Formato, tipos, campos requeridos → serializer.
Reglas de negocio ("el monto no puede ser cero", "la cuenta debe ser tuya") → service o dominio.
**Prohibido**: `validate_*()` que consulte la base de datos para aplicar una regla de negocio.

### 5. La lógica de negocio vive en `services.py` y `domain/`
Los services orquestan casos de uso. El dominio contiene las reglas.

### 6. Dependencias hacia adentro
`views` → `services` → `domain`. Nunca al revés.
`domain/interfaces.py` define ABCs; `infra/` las implementa. Los services dependen de la ABC, jamás de la implementación concreta.

### 7. Apps prohibidas en esta entrega
Solo existen tres apps: `core`, `identity`, `finance`.
**No crear** `analytics`, `recommendation` ni `subscription`, ni sus modelos, ni scaffolding "para después".
`docs/ARCHITECTURE.md` los describe porque documenta el sistema completo; están **fuera del alcance de esta entrega**. Si el documento menciona `Insight`, `Recommendation`, `RiskProfile`, `Subscription`, `Payment`, `SubscriptionPlan`, `InvestmentPlan`, `SpendingPattern` o `Dashboard`: ignóralos.

### 8. No inventes alcance
No agregues features, endpoints, modelos ni campos que no estén en `docs/ARCHITECTURE.md` o en el prompt del módulo actual.
Si algo parece faltar, dilo en la respuesta en vez de improvisarlo.

---

## Convenciones

**Nomenclatura**: identificadores en inglés, siguiendo el glosario de `docs/ARCHITECTURE.md` §12. Los sinónimos prohibidos ahí están prohibidos de verdad.
Colisión conocida: `from django.db import transaction as db_transaction`, porque `Transaction` es una entidad del dominio.

**Idioma**: código en inglés. Docstrings y comentarios en español.

**Value Objects**: `@dataclass(frozen=True)`. Inmutables de verdad.

**Dinero**: siempre `Decimal`, nunca `float`. `DecimalField(max_digits=14, decimal_places=2)`.

**IDs**: `UUIDField(primary_key=True, default=uuid4, editable=False)`.

**Excepciones**: el dominio lanza subclases de `DomainError` (`core/domain/exceptions.py`), nunca excepciones de Django ni de DRF. El handler global las traduce a HTTP.

**Tests**: `pytest` + `pytest-django`. Los tests de dominio no tocan la base de datos.

**Dependencias**: no instalar paquetes fuera de `requirements.txt` sin decirlo explícitamente en la respuesta.

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
2. Comandos para verificar que funciona.
3. Cualquier decisión que tomaste y no estaba especificada.
4. Cualquier regla de este archivo que te haya obligado a resolver algo de forma no obvia.
