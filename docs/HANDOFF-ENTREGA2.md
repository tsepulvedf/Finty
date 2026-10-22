# Finty — Contexto de traspaso para la Entrega 2

> **Para Claude Code:** este documento resume las decisiones tomadas en la sesión de planeación de la Entrega 2. Léelo completo antes de proponer cualquier cambio. La jerarquía de fuentes es:
> 1. `RULES.md` (reglas de trabajo — equivale a `CLAUDE.md`)
> 2. `docs/ARCHITECTURE.md` (fuente única de verdad del diseño; en v3 desde el módulo E2-M0)
> 3. Este documento (contexto de traspaso; desde E2-M0, las decisiones D-E2-01 a D-E2-09 están incorporadas en `ARCHITECTURE.md` v3 como ADR-07 a ADR-16)
>
> Si encuentras una contradicción entre ellos, **detente y repórtala** en lugar de resolverla por tu cuenta.

---

## 1. Quién trabaja y cómo

- **Repositorio:** https://github.com/tsepulvedf/Finty (rama `main`).
- **Equipo:** Tomás Sepúlveda (`tsepulvedf`) y Juan Pablo Restrepo (`RestrepoJuanP`). Tomás hizo los commits de la Entrega 1; **en la Entrega 2 los commits los hace Juan Pablo desde su máquina, con su usuario de GitHub**. El enunciado del curso pone 0.0 a cualquier estudiante sin commits, así que la autoría importa.
- **Flujo de trabajo:** la planeación y los prompts se diseñan en una sesión de Claude (chat) y se ejecutan aquí, en Claude Code (VS Code), **un módulo a la vez**. Juan Pablo confirma que un módulo terminó —tests en verde y commits hechos— antes de pasar al siguiente. No adelantes trabajo de módulos futuros.
- **Entorno:** Windows, Git Bash, carpeta sincronizada con OneDrive. Problemas conocidos:
  - Pegar varias líneas en Git Bash puede anteponer `[200~` al primer comando (bracketed paste). Se desactiva con `printf '\e[?2004l'` o, de forma permanente, con `echo 'set enable-bracketed-paste off' >> ~/.inputrc`.
  - OneDrive bloquea carpetas durante `git checkout`. Hay que cerrar terminales y editores sobre esa carpeta antes de cambiar de rama, y no dejar `__pycache__` sin ignorar.
- **Commits:** convención semántica en español, uno por unidad lógica, **sin coautoría ni firmas generadas** (regla vigente de `RULES.md`, confirmada para esta entrega).

## 2. Qué existe hoy (Entrega 1, cerrada)

Monolito Django 5.2 + DRF 3.17 + PostgreSQL, arquitectura de tres anillos:

- `core/` — `Money`, jerarquía `DomainError`, handler global de excepciones, router `/api/v1/`, `HealthView`.
- `identity/` — `User` propio (`AbstractUser`, login por email), `UserProfile`, `ProfileService`; endpoints `auth/register/`, `auth/login/` (Token de DRF) y `profile/`.
- `finance/` — `Account` (aggregate root), `Transaction`, `Category`; `AccountBuilder`, `TransactionBuilder` (devuelven `AccountDraft` / `TransactionDraft`), `AccountSnapshot`, `BalanceCalculator`, `TransactionRules`; `Categorizer` (ABC) con `RuleBasedCategorizer`, `MockCategorizer` y `AICategorizer` (degradado) elegidos por `CategorizerFactory` según `CATEGORIZER_PROVIDER`; `AccountService` y `TransactionService`; comando `verify_invariants`.
- `frontend/app.html` — cliente de demostración estático de un solo archivo.
- Suite de pytest grande, incluida la verificación de reglas de arquitectura por AST (`core/tests/test_architecture.py`).

**Punto clave para la Entrega 2:** `core/domain/` y `finance/domain/` son Python puro (verificado: `grep -rn "django" core/domain/ finance/domain/` sale vacío). Eso significa que el dominio **se puede trasladar a Flask casi sin cambios**. Es la justificación arquitectónica de toda esta entrega: lo que se reescribe es el anillo externo (ORM, vistas, repositorios), no las reglas de negocio.

**Deuda detectada:** el commit `Reuploading files` no incluyó los archivos ocultos. Faltan en el repositorio **`.gitignore`** y **`.env.example`**, aunque el README menciona ambos. Sin `.gitignore`, `.env`, `venv/` y `__pycache__/` pueden terminar versionados. Se corrige en E2-M0, antes de cualquier otro commit.

## 3. Qué pide la Entrega 2 (resumen del enunciado)

| Criterio | Peso | Qué exige |
|---|---|---|
| Correcciones E1 | 10% | **Eliminatorio:** si no se corrige el 100%, la entrega no se revisa y la nota es 0.0. La corrección notificada es **un frontend intuitivo y agradable** |
| Arquitectura | 10% | Diagramas actualizados que incluyan AWS, Nginx, Flask y el broker |
| Servicios | 30% | Exponer un endpoint JSON; consumir el servicio del equipo aliado y mostrarlo en la app; consumir una API de terceros **mediante el patrón Adapter** |
| Infraestructura | 30% | Todo en Docker Compose (Django, Flask, Nginx, base de datos, broker), desplegado en una instancia **EC2 de AWS Academy**, con Nginx como API Gateway |
| Resiliencia y UX | 20% | Tareas asíncronas con Redis/Celery (reportes, notificaciones); auditoría de UI/UX; **i18n bilingüe completo con gettext, sin textos quemados** |

**Bono (objetivo del equipo):** migrar **más del 70%** de los servicios y la lógica de negocio a microservicios Flask independientes exime del Parcial 02.

**Entrega:** enlace al repo (rama `main`) e IP elástica de AWS. La instancia debe estar encendida durante la sustentación.

## 4. Decisiones tomadas

### D-E2-01 — Los contextos pendientes nacen directamente en Flask
`analytics`, `recommendation` y `subscription` **no se construyen en Django**. Se construyen como microservicios Flask desde el inicio, para no hacer el trabajo dos veces.

### D-E2-02 — Para el bono, `finance` también se extrae del monolito
Con solo los tres contextos nuevos más la categorización, la cobertura queda alrededor del 55–65% según cómo se mida, y eso no asegura el bono. Por eso **todo el contexto `finance` se migra a Flask** aplicando el Strangler Pattern: Nginx desvía las rutas `/api/v1/accounts`, `/transactions` y `/categories` al nuevo servicio, mientras el monolito sigue en pie hasta que la ruta nueva esté verificada.

Distribución resultante (contada sobre las 20 clases del diagrama de dominio de `ARCHITECTURE.md` §4.2):

| Unidad | Tecnología | Clases del dominio |
|---|---|---|
| Monolito `identity` + frontend + verificación de auth | Django | `User`, `UserProfile` (2) |
| `finance-service` | Flask | `Account`, `Transaction`, `Category`, `Money`, `AccountType`, `TransactionType`, `BalanceCalculator` (7) |
| `categorization-service` | Flask | `Categorizer`, `CategorySuggestion` (2) |
| `analytics-service` | Flask | `Insight`, `SpendingPattern`, `Dashboard` (3) |
| `recommendation-service` | Flask | `Recommendation`, `RiskProfile`, `InvestmentPlan` (3) |
| `subscription-service` | Flask | `Subscription`, `SubscriptionPlan`, `Payment` (3) |

**18 de 20 clases (90%) fuera del monolito.** Django conserva identidad, la verificación de autenticación y el servidor de plantillas del frontend. *Pendiente:* confirmar con el profesor si el 70% se mide por clases, por endpoints o por bounded contexts; con esta distribución se supera en las tres métricas.

### D-E2-03 — Autenticación centralizada en el Gateway
Nginx valida cada petición a un microservicio con `auth_request` contra un endpoint interno de Django (`/internal/auth/verify/`). Django valida el Token y responde con la cabecera `X-User-Id`, que Nginx reenvía al servicio. Los servicios Flask **no validan tokens**: confían en `X-User-Id` y solo aceptan tráfico de la red interna de Docker. Es la función de autenticación del Gateway que `ARCHITECTURE.md` §10.1 dejó como "realización futura".

### D-E2-04 — Una base de datos por servicio
Una sola instancia de PostgreSQL en Compose, pero **una base de datos lógica por servicio** (`finty_identity`, `finty_finance`, …). Ningún servicio consulta la base de otro; se comunican por HTTP a través de la red interna o por eventos en Redis.

### D-E2-05 — Frontend en plantillas Django con gettext
El cliente deja de ser un HTML estático. Django sirve plantillas con `{% translate %}` / `{% blocktranslate %}` y el `JavaScriptCatalog` para los textos que genere JavaScript. Las pantallas consumen `/api/v1/` desde el navegador, en el mismo origen y a través de Nginx. Idiomas: `es` y `en`, con selector visible. *Actualizado en E2-M8a:* los microservicios Flask **no** usan Flask-Babel; responden `code` estables y el frontend los traduce en un solo módulo JavaScript con gettext (`ARCHITECTURE.md` ADR-11).

El diseño visual lo produce **Claude Design** a partir del inventario de pantallas de Phase 1 (SCR-001 a SCR-008) más las pantallas de los contextos nuevos; Claude Code lo implementa después sobre las plantillas.

### D-E2-06 — API de terceros: tasas de cambio (TRM)
Se consume una API pública de tasas de cambio detrás de un **Adapter** (`ExchangeRateProvider` ABC → adaptador concreto + adaptador de respaldo con tasa fija). Resuelve la deuda D-04 de `ARCHITECTURE.md` (multi-moneda) y no requiere pago.

### D-E2-07 — Servicio expuesto y servicio del equipo aliado
- **Expuesto:** un resumen financiero agregado en JSON (por ejemplo, gasto por categoría del período), servido por `analytics-service`. Ruta y contrato exactos: por definir con el equipo aliado.
- **Consumido:** el servicio del equipo aliado también va detrás de un Adapter (`AllyServiceProvider` ABC), con un `MockAllyAdapter` de respaldo si el aliado no responde (es resiliencia, que también se evalúa).
- **TAREA PENDIENTE (Tomás):** el equipo aliado **aún no está asignado**; Tomás lo consultará con el profesor. Hasta entonces se trabaja solo con `MockAllyAdapter`. **No inventes** el dominio, la URL ni el contrato del aliado: cuando lleguen, se escribe el adaptador concreto en un módulo aparte. Datos a obtener: proyecto del aliado, URL y método del endpoint, autenticación, ejemplo de respuesta, qué esperan consumir de Finty y fecha en que su endpoint estará en línea.

### D-E2-08 — Pagos: puerto, Factory y pago simulado (revisada en E2-M6b)
**Sin pasarela real.** Es un ejercicio académico: el pago del plan PREMIUM es una **simulación de interfaz**, y `MockPaymentGateway` es la única implementación de `PaymentGateway` (ABC) en `subscription-service`. `PaymentGatewayFactory` solo acepta `PAYMENT_GATEWAY=MOCK`, y otro valor impide arrancar el servicio.

Se conservan el puerto y la Factory para que una pasarela real se agregue como un adaptador más, sin tocar el dominio (OCP). Dos salvaguardas: el backend rechaza con 400 cualquier campo del checkout además de `{plan}`, así que nunca recibe datos de tarjeta, y el formulario del frontend es una simulación identificada como tal (§8).

*Decisión anterior, cancelada:* `WompiSandboxGateway` con confirmación por Celery. Se descartó porque la consulta por referencia que exigía no está documentada por Wompi, la redirección no debe usarse para validar y los webhooks requieren HTTPS. El análisis quedó en `ARCHITECTURE.md` ADR-14 y C-33. El requisito de API de terceros lo cumple la TRM (D-E2-06). *Estado: decidida al cancelar E2-M6b con Wompi.*

### D-E2-09 — Tareas asíncronas (Celery + Redis)
Candidatas: generación del reporte mensual (CSV o PDF), notificaciones (backend de email en consola o archivo), recategorización por lotes y, como primera tarea periódica de E2-M7, `expire_subscriptions` (pasar a EXPIRED las suscripciones cuyo período terminó). Sin pasarela real no hay consulta del estado de pagos (D-E2-08). Cada servicio publica eventos de dominio en Redis en lugar de llamar a otro servicio de forma síncrona cuando no necesita la respuesta. Esto resuelve la deuda D-03 (dependencia circular `Recommendation → FinancialData`) y D-05 (eventos de dominio).

## 5. Plan por módulos

| Módulo | Contenido | Entregable verificable |
|---|---|---|
| **E2-M0** | `ARCHITECTURE.md` v3 con estas decisiones, diagramas nuevos y `RULES.md` actualizado (la regla §7 hoy **prohíbe** crear `analytics`, `recommendation` y `subscription`); restaurar `.gitignore` y `.env.example` | Documentos revisados por Tomás |
| **E2-M1** | Esqueleto en contenedores: Docker Compose con Django, PostgreSQL, Redis y Nginx; despliegue en EC2 con IP elástica | `curl http://<ip>/api/v1/health/` responde desde AWS |
| **E2-M2** | `finance-service` (Flask): dominio trasladado, repositorios con SQLAlchemy, ruteo Strangler en Nginx, `auth_request` | Mismo contrato `/api/v1/` servido por Flask; tests portados en verde |
| **E2-M3** | `categorization-service` extraído; `finance-service` lo consume por HTTP con respaldo determinista | Procedencia `rule` / `ai` / `mock` intacta |
| **E2-M4** | `analytics-service` + endpoint expuesto al equipo aliado | JSON público documentado |
| **E2-M5** | `recommendation-service` + Adapter de tasas de cambio | Recomendaciones explicables; TRM con respaldo |
| **E2-M6** | `subscription-service` + `PaymentGateway` + gating de funciones premium (INV-05, INV-06) | Flujo de pago simulado (sin pasarela real, D-E2-08) |
| **E2-M7** | Celery: `expire_subscriptions` (primera tarea periódica), reportes y notificaciones | Tareas visibles en el worker |
| **E2-M8** | Frontend: plantillas Django e i18n `es`/`en` según el diseño de Claude Design | Cero textos quemados (verificable por test) |
| **E2-M9** | Integración con el equipo aliado, diagramas finales, Wiki, ensayo de la sustentación en EC2 | Checklist del enunciado al 100% |

El diseño en Claude Design corre **en paralelo** desde E2-M1; solo se implementa en E2-M8.

## 6. Reglas que siguen vigentes y cómo se extienden

- El dominio de cada servicio es Python puro. La verificación por AST se replica en cada servicio Flask: `domain/` no importa Flask ni SQLAlchemy.
- Las vistas no piensan (Flask: los blueprints solo parsean, llaman al servicio y traducen a HTTP).
- La lógica de negocio vive en `services.py` y `domain/` de cada servicio.
- El dinero siempre es `Decimal`; los IDs son UUID; el glosario de `ARCHITECTURE.md` §12 sigue vigente, con sinónimos prohibidos.
- No se instalan dependencias fuera del `requirements.txt` de cada servicio sin decirlo explícitamente.
- No se inventa alcance: lo que no esté en `ARCHITECTURE.md` v3 o en el prompt del módulo, se pregunta.

## 7. Al terminar cada módulo, reporta

1. Archivos creados o modificados.
2. Comandos para verificarlo (tests, `docker compose`, `curl`).
3. Decisiones que tomaste y no estaban especificadas.
4. Reglas que te obligaron a resolver algo de forma no obvia.
5. Secuencia de commits sugerida para ese módulo.

## 8. Requisitos acumulados para el frontend (E2-M8)

Lo que los módulos anteriores dejaron decidido para las pantallas. E2-M8 los implementa sobre las plantillas Django con gettext (D-E2-05).

*Estado tras E2-M8a:* ya están la traducción de errores por `code` y de 401/429 por estado, y el manejo de 403 y 503 en `js/api.js`, con la moneda de presentación tomada de `preferred_currency`. Faltan para E2-M8b el checkout simulado, la bienvenida, la pantalla de planes (destino del 403) y las recomendaciones con `locked`.

- **Checkout simulado.** Al elegir PREMIUM se muestra un formulario de tarjeta (número, nombre, vencimiento y CVC):
  - La validación de formato ocurre solo en el navegador.
  - Muestra un aviso visible: "Modo demostración: no se realiza ningún cobro".
  - Lleva `autocomplete="off"`.
  - Ningún dato del formulario se envía, se guarda ni se registra. "Continuar" llama a `POST /api/v1/subscriptions/checkout/` solo con `{plan}`; el backend rechaza con 400 cualquier otro campo (ADR-14).
- **Bienvenida.** Si el checkout responde con el pago APPROVED, se muestra una pantalla de agradecimiento y bienvenida al plan premium. La lista de beneficios desbloqueados sale de `GET /api/v1/subscriptions/plans/` y se traduce por `code`.
- **Errores.** Las respuestas 401 y 429 se traducen por código de estado (D-21), y los errores de dominio por su `code`.
- **Gating premium (INV-06).**
  - Un 403 `premium_required` lleva al usuario a la pantalla de planes.
  - Un 503 `entitlements_unavailable` muestra "intenta de nuevo", no la invitación a pagar.
- **Recomendaciones bloqueadas.** Cuando `GET /api/v1/recommendations/` trae `locked`, se muestra la parte bloqueada con una invitación al plan premium.
- **Moneda de presentación.** Sale de `preferred_currency` (`GET /api/v1/profile/`) y se envía como `?display_currency=` (ADR-12).
