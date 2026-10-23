# Finty — Guion de la sustentación (Entrega 2)

Guía para presentar la Entrega 2 en unos **15 minutos**, en el orden de los criterios del enunciado y con su peso. Se alterna el navegador con el código; cada parada cita archivo y línea, y dice qué contar. La evidencia de respaldo está en [`VERIFICATION.md`](VERIFICATION.md) y en la [Wiki](wiki/Home.md).

| | |
|---|---|
| Aplicación | `http://3.95.100.48` (EC2 del AWS Academy Learner Lab, `us-east-1`: Ubuntu Server 24.04 LTS, `t3.medium`, 30 GB `gp3`, grupo de seguridad `finty-sg` con 22 y 80) |
| Repositorio | `https://github.com/tsepulvedf/Finty`, rama `main` |
| Usuario Free | `demo-free@finty.co`: Laura Gómez, 2 meses de datos |
| Usuario Premium | `demo-premium@finty.co`: Andrés Restrepo, 6 meses de datos, perfil de riesgo moderado y un plan de inversión |
| Contraseña de ambos | `Finty-Demo-2026` (o el valor de `DEMO_PASSWORD` con que se sembraron) |

---

## 1. Antes de empezar (30 minutos antes)

1. **Learner Lab:**
   - Entra a AWS Academy, pulsa **Start Lab** y espera el indicador verde.
   - En EC2 → Instances, la instancia debe estar **Running**. Si estaba detenida, enciéndela: la IP elástica no cambia.
2. **Contenedores:**

   Entra con **EC2 Instance Connect**: instancia → Connect → EC2 Instance Connect, usuario `ubuntu`.

   ```bash
   cd Finty && git pull && docker compose up -d --build   # solo si hubo cambios desde el último despliegue
   docker compose ps                                       # todos Up; los servicios Flask (healthy)
   ```

3. **Desde tu portátil, no desde la instancia:**

   ```bash
   curl http://3.95.100.48/api/v1/health/                 # {"status":"ok","version":"v1"}
   ```

4. **Datos de demostración:** se siembran por la API y el comando es idempotente. Si los usuarios ya existen, solo completa lo que falte, sin duplicar.

   ```bash
   python3 tools/seed_demo.py --base-url http://3.95.100.48
   # Una segunda corrida debe reportar 0 movimientos creados.
   ```

   Lo que deja:
   - **Laura (Free):** dos cuentas y 2 meses de movimientos.
   - **Andrés (Premium):**
     - tres cuentas, una en USD, y 6 meses de movimientos;
     - un pico de Compras en el mes actual, para que aparezca el insight `category_spike`;
     - el checkout PREMIUM ya hecho;
     - el perfil de riesgo moderado y un plan de inversión.
5. **Pestañas abiertas:**
   - el navegador en `http://3.95.100.48/` (una ventana normal para Andrés y una de incógnito para Laura);
   - el editor con el repositorio;
   - una terminal de EC2 Instance Connect en la instancia, para las demos de resiliencia;
   - esta guía.
6. **Comprobar el idioma:** el selector ES/EN debe estar visible y debe cambiar la pantalla completa.

---

## 2. Guion (unos 15 minutos)

### 2.1 Correcciones de la Entrega 1: frontend intuitivo (10%, eliminatorio), unos 3 minutos

| Navegador | Código | Qué decir |
|---|---|---|
| Ingresa como Andrés. El Dashboard muestra comparaciones con el mes anterior, saldo por moneda con su equivalente, tendencia y tasa de ahorro | [`frontend/templates/finty/`](../frontend/templates/finty/) | "La corrección notificada fue el frontend. El HTML estático de la E1 pasó a 11 pantallas en plantillas Django, diseñadas en Claude Design ([`docs/design/`](design/))." |
| Movimientos: busca "Uber", filtra por tipo y recategoriza uno | [`frontend/static/finty/js/api.js`](../frontend/static/finty/js/api.js) | "El JavaScript solo pinta. Los cálculos los hace la API: el frontend no tiene reglas de negocio." |
| Abre Movimientos en un ancho de móvil (DevTools, 390 px) | [`docs/UX-AUDIT.md`](UX-AUDIT.md) | "Auditamos con Lighthouse y axe: accesibilidad en 100 en las 80 combinaciones, cero violaciones, y los 4 hallazgos de severidad 3 corregidos." |

### 2.2 Arquitectura (10%), unos 2 minutos

| Navegador o Wiki | Código | Qué decir |
|---|---|---|
| La Wiki, página Arquitectura: diagrama de despliegue (AWS, el grupo de seguridad, EC2, Compose, Redis y PostgreSQL) | [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §9.4 | "Un solo contenedor publica puerto, Nginx en el 80. El resto vive en la red interna." |
| Página Migración Strangler y bono | §9.16 y la tabla 18/20 | "Movimos 18 de las 20 clases del dominio fuera del monolito: 90% por clases, 80% por contextos, y la mayoría de los endpoints." |
| — | [`services/finance-service/domain/builders.py:185`](../services/finance-service/domain/builders.py#L185) | "El dominio se trasladó casi sin cambios porque ya era Python puro. Un test por AST lo verifica en cada servicio (A-16)." |

### 2.3 Servicios (30%), unos 4 minutos

| Navegador | Código | Qué decir |
|---|---|---|
| Inversiones: equivalente USD/COP con su fuente (`live`, `cached` o `fallback`) | [`services/recommendation-service/infra/exchange_rates.py:43`](../services/recommendation-service/infra/exchange_rates.py#L43) y [`services/recommendation-service/services.py:86`](../services/recommendation-service/services.py#L86) | "La API de terceros es la TRM de datos.gov.co, detrás de un **Adapter**: `ExchangeRateProvider` es el puerto y `TrmExchangeRateProvider` lo traduce. Si cae, sirve la última tasa conocida y, sin ella, la fija de 3200." |
| `curl "http://3.95.100.48/api/v1/public/spending-summary/?period=2026-10"` | [`services/analytics-service/domain/summary.py:43`](../services/analytics-service/domain/summary.py#L43) | "Este es el endpoint JSON que exponemos, sin autenticación. Tiene k-anonimato: una categoría solo aparece si la tienen al menos 3 usuarios." |
| Movimientos: registra "Uber al aeropuerto" y aparece en Transporte con procedencia `rule` | [`services/categorization-service/infra/factories.py:81`](../services/categorization-service/infra/factories.py#L81) | "La categorización es un microservicio; su **Factory Method** elige el categorizador según `CATEGORIZER_PROVIDER`." |
| — | — | **Servicio del equipo aliado:** "Todavía no tenemos equipo aliado asignado. El puerto `AllyServiceProvider` está diseñado (ADR-13), pero no está implementado: no inventamos el contrato." Decirlo así, sin rodeos. |

### 2.4 Infraestructura (30%), unos 3 minutos

| Terminal o navegador | Código | Qué decir |
|---|---|---|
| `docker compose ps` en la instancia | [`docker-compose.yml:369`](../docker-compose.yml#L369) | "Todo corre en Docker Compose en EC2: Django, cinco servicios Flask, sus workers, PostgreSQL, Redis y Nginx. Solo Nginx tiene `ports`." |
| `curl -i http://3.95.100.48/api/v1/accounts/` → 401 con `X-Finty-Route: finance` | [`deploy/nginx/snippets/gateway-auth.conf:15`](../deploy/nginx/snippets/gateway-auth.conf#L15) | "Nginx es el API Gateway: con `auth_request` le pregunta a Django por el token una sola vez. Los servicios Flask confían en `X-User-Id` y nunca ven el token." |
| — | [`identity/services.py:209`](../identity/services.py#L209) | "Así verifica Django el token para el Gateway." |
| — | [`deploy/nginx/snippets/proxy.conf:20`](../deploy/nginx/snippets/proxy.conf#L20) | "El `X-User-Id` que mande el cliente se pisa siempre (A-18)." |
| `curl -i http://3.95.100.48/internal/auth/verify/` → 404 | [`deploy/nginx/conf.d/finty.conf:102`](../deploy/nginx/conf.d/finty.conf#L102) | "Lo interno no existe desde fuera." |
| — | [`deploy/nginx/conf.d/finty.conf:22`](../deploy/nginx/conf.d/finty.conf#L22) | "Tres zonas de `limit_req`: login y registro, API y endpoint público." |

### 2.5 Resiliencia y UX (20%), unos 3 minutos

| Navegador o terminal | Código | Qué decir |
|---|---|---|
| Dashboard → **Descargar reporte**: queda PENDING y luego descarga el CSV | [`services/analytics-service/tasks.py:32`](../services/analytics-service/tasks.py#L32) | "El reporte es una tarea de Celery sobre Redis. La tarea solo llama al caso de uso." |
| Una demo de resiliencia de §3 (la de `categorization-service` es la más rápida) | [`services/finance-service/infra/categorization_client.py:73`](../services/finance-service/infra/categorization_client.py#L73) | "Si un servicio cae, el usuario no lo nota o ve un estado claro, nunca un 500." |
| `curl -i` a una ruta con el servicio detenido (§3.5) | [`deploy/nginx/conf.d/finty.conf`](../deploy/nginx/conf.d/finty.conf), `location @gateway_unavailable` | "Si un servicio no responde, el Gateway contesta 503 en JSON con `code: service_unavailable` en 2 s, y se recupera solo cuando el servicio vuelve: resuelve los nombres en tiempo de ejecución." |
| — | [`services/finance-service/services.py:665`](../services/finance-service/services.py#L665) | "Los eventos van al **outbox** en la misma transacción que el movimiento. Un relay los publica en Redis Streams, y analytics los consume de forma idempotente." |
| Cambia a EN con el selector: toda la pantalla cambia, también los errores | [`frontend/static/finty/js/codes.js`](../frontend/static/finty/js/codes.js) | "i18n completo con gettext. Los servicios responden un `code` y el frontend lo traduce." |
| — | [`core/tests/test_frontend.py:398`](../core/tests/test_frontend.py#L398) | "Un test falla si queda un texto quemado (A-23)." |
| Como Laura (Free): Insights → invitación a Premium → checkout simulado → bienvenida | [`services/subscription-service/api/schemas.py:33`](../services/subscription-service/api/schemas.py#L33) y [`frontend/static/finty/js/pages/checkout.js:111`](../frontend/static/finty/js/pages/checkout.js#L111) | "El pago es simulado. El formulario nunca envía la tarjeta: solo `{plan}`. El backend rechaza con 400 cualquier otro campo." |

**Ojo:** el checkout deja a Laura en Premium por un mes, y `seed_demo.py` no la devuelve a Free. Para ensayar sin gastar la demo, usa un usuario nuevo creado en la pantalla de registro, y deja a Laura para la sustentación.

---

## 3. Demos de resiliencia en vivo

Se corren en la terminal de la instancia, dentro de `Finty/`. Cada demo **termina levantando lo que se detuvo**.

Se ensayaron en el stack local el 2026-10-22, con los resultados que se describen. Los tiempos medidos están en [`tests/contract/runs/2026-10-22-resiliencia-e2-m9c.txt`](../tests/contract/runs/2026-10-22-resiliencia-e2-m9c.txt).

### 3.1 `categorization-service` detenido

```bash
docker compose stop categorization-service
# Navegador: registra un gasto "Uber al aeropuerto".
docker compose logs --tail 5 finance-service
docker compose start categorization-service
```

**Qué debe verse:**
- El movimiento se crea igual (201) y cae en **Transporte** con procedencia `rule`.
- En el log de `finance-service`: `categorization-service no utilizable (...); clasifica el respaldo local`.
- `RemoteCategorizer` nunca propaga la falla ([`categorization_client.py:73`](../services/finance-service/infra/categorization_client.py#L73)).

### 3.2 Redis detenido

```bash
docker compose stop redis
# Navegador: registra un movimiento, abre el Dashboard, Insights e Inversiones, y pide un reporte.
docker compose start redis
docker compose logs --tail 5 finance-outbox-relay analytics-worker
```

**Mientras Redis está abajo:**
- El movimiento se guarda (201) y su evento queda en el **outbox**, en PostgreSQL.
- Dashboard, Insights y recomendaciones responden 200, con los datos que analytics ya tenía. Tardan **unos 8 a 9 s**: cada intento de usar la caché de Redis espera 4 s a que el DNS de Docker diga que `redis` no existe. Avísalo antes de abrir la pantalla.
- La caché de derechos premium y la de tasas se saltan: se consulta directo a `subscription-service` y a la TRM.
- Pedir un reporte responde 202 y queda **PENDING**: el broker está caído y no hay quien lo tome.

**Al volver Redis:**
- El relay publica lo pendiente y analytics se pone al día: el movimiento aparece en el Dashboard.
- El reporte PENDING lo retoma `analytics.requeue_pending_reports`. Corre cada minuto y toma los que llevan más de un minuto pendientes (`REPORT_REQUEUE_EVERY_SECONDS` y `REPORT_STALE_AFTER_SECONDS`), así que tarda **a lo sumo unos 2 minutos**. En el ensayo tardó 106 s.

### 3.3 `analytics-celery` detenido

```bash
docker compose stop analytics-celery
# Navegador: Dashboard → Descargar reporte. La pantalla indica que el reporte se está preparando.
docker compose exec redis redis-cli -n 1 LLEN analytics    # 1: el mensaje espera en la cola
docker compose start analytics-celery
```

**Qué debe verse:**
- El reporte queda **PENDING** mientras no hay worker; la API y la pantalla siguen respondiendo.
- Al arrancar el worker toma el mensaje (`acks_late`), y el reporte pasa a **READY** en segundos y se descarga.

### 3.4 `subscription-service` detenido

```bash
docker compose stop subscription-service
# Espera 30 s: los derechos premium en caché vencen (ENTITLEMENTS_CACHE_SECONDS).
# Navegador, como Andrés (Premium): Dashboard, Insights e Inversiones.
docker compose start subscription-service
```

**Qué debe verse:**

| Función | Respuesta |
|---|---|
| Dashboard (gratuito) | Sigue funcionando |
| Insights y planes de inversión (premium) | 503 `entitlements_unavailable`: la pantalla dice **"intenta de nuevo"**, nunca invita a pagar a quien ya pagó (fail-closed, INV-06) |
| Recomendaciones | 200: las de optimización se muestran, y la parte de inversión llega en `locked` con `entitlements_unavailable` |
| Planes y Ajustes (las rutas propias de `subscription-service`) | 503 del Gateway en JSON, `code: service_unavailable`: la región muestra "El servicio no está disponible en este momento. Intenta de nuevo en unos minutos." |

En los primeros 30 s, la caché aún dice "Premium" y todo funciona: esa es la caché corta que protege de caídas breves.

### 3.5 Django (identity) detenido, sin reiniciar Nginx

```bash
docker compose stop django
curl -i -H "Authorization: Token cualquiera" http://3.95.100.48/api/v1/accounts/
curl -i http://3.95.100.48/api/v1/health/
curl "http://3.95.100.48/api/v1/public/spending-summary/?period=2026-10"
docker compose start django
curl -i http://3.95.100.48/api/v1/health/       # 200 en un par de segundos, sin tocar Nginx
```

**Qué debe verse:**

| Petición | Respuesta |
|---|---|
| Lo autenticado (`/accounts/`) | En unos 2 s, **503** `{"detail": "El servicio no está disponible…", "code": "service_unavailable"}` con `X-Finty-Route: finance`. Nadie puede verificar el token, así que la petición no pasa: fail-closed |
| Las rutas de Django (`/api/v1/health/`, `/`) | El mismo 503, con `X-Finty-Route: monolith` |
| El endpoint público | Sigue en 200: no depende de Django |
| Al volver Django | En el ensayo, `/accounts/` respondió 200 un segundo después, sin reiniciar Nginx. Resuelve los nombres en tiempo de ejecución, con 10 s de validez |

El navegador no puede cargar pantallas mientras Django está abajo: las plantillas las sirve él. Por eso esta demo se hace con `curl`.

---

## 4. Plan B: el stack local

Si la instancia o la red del salón fallan, se presenta con el mismo stack en el portátil (Docker Desktop):

```bash
docker compose up -d --build
docker compose ps
curl http://localhost/api/v1/health/
python tools/seed_demo.py --base-url http://localhost
# Navegador: http://localhost/
```

Es la misma imagen y la misma configuración de Nginx, con otra URL. Para mostrar que la instancia **sí** estuvo en línea:
- `tests/contract/runs/` tiene las corridas de evidencia;
- la verificación de A-24 (2026-10-22) comparó los estáticos con hash de EC2 y del stack local.

---

## 5. Preguntas probables

**¿Por qué el patrón Strangler?**
Permitió migrar `finance` sin apagar nada. Nginx desvió `accounts`, `transactions` y `categories` al servicio Flask como un solo bloque, y la misma suite de contrato pasó antes y después de conmutar y tras retirar `finance` del monolito (`tests/contract/runs/2026-10-20-*`). Si algo fallaba, volver atrás era una línea del Gateway.

**¿Por qué un outbox y no publicar directo a Redis?**
Publicar desde la petición deja una ventana: la base confirma y Redis no recibe, o al revés. Con el outbox, el evento se escribe en la **misma transacción** que el movimiento, así que existen los dos o ninguno. Un relay aparte lo publica después, aunque Redis haya estado caído.

**¿Por qué `auth_request` en Nginx?**
El token se valida **una sola vez**, en el borde, contra Django, que es el dueño de la identidad. Los servicios Flask no duplican lógica de autenticación ni ven el token: confían en `X-User-Id`. Pueden hacerlo porque Nginx borra el que mande el cliente y porque ningún servicio publica puertos.

**¿Por qué una base de datos por servicio?**
Para que cada servicio sea dueño de sus datos y se pueda cambiar o desplegar sin romper a otro. Hay una sola instancia de PostgreSQL, pero cinco bases lógicas, y ningún servicio conoce la URL de otra. Los datos de otros contextos llegan por HTTP o por eventos.

**¿Por qué no hay pasarela de pago real?**
Es un ejercicio académico y no debe recibir datos de tarjeta reales. Evaluamos Wompi en sandbox y lo descartamos (ADR-14): la consulta que necesitábamos no está documentada, la redirección no sirve para validar y los webhooks exigen HTTPS. Quedaron el puerto `PaymentGateway` y su Factory, así que una pasarela real sería otro adaptador.

**¿Qué ve el usuario si un servicio no responde?**
Nunca una página de error de Nginx. El Gateway contesta 503 en JSON con `code: service_unavailable` y `X-Finty-Route` del bloque que falló, y el frontend lo traduce por `code`. Como resuelve los nombres en tiempo de ejecución con timeouts de 2 s, una caída no deja peticiones colgadas, y cuando el servicio vuelve Nginx lo encuentra solo.

**¿Cómo se mide el 70% del bono?**
De tres formas, y en las tres se supera:
- **Clases del dominio:** 18 de 20 fuera del monolito (90%).
- **Bounded contexts:** 4 de 5 (80%).
- **Endpoints de negocio:** la mayoría, porque Django solo conserva registro, ingreso, perfil y la verificación interna.

Detalle en la página Migración Strangler y bono de la Wiki.

**¿Cómo garantizan que nunca reciben datos de tarjeta?**
Con tres capas:
1. **Formulario:** los campos no tienen `name`, llevan `autocomplete="off"` y se validan solo en el navegador. "Continuar" envía solo `{plan}`.
2. **Backend:** `CheckoutInput` tiene `extra="forbid"`, así que cualquier otro campo da 400 sin repetir su valor y sin crear filas.
3. **Tests:** uno revisa que el JavaScript no arme otro cuerpo, y otro que ningún valor de tarjeta aparezca en la respuesta ni en el log.

**¿Qué pasa si falla cada servicio?**

| Si cae… | Lo que pasa |
|---|---|
| `categorization-service` | `finance-service` clasifica con su respaldo local (`rule`); el usuario no lo nota |
| `analytics-service` o su worker | Los movimientos se siguen registrando; el dashboard no carga o queda atrasado, y se pone al día al volver. Las recomendaciones salen con `degraded: true` (A-28) |
| `recommendation-service` | Inversiones y Perfil de riesgo muestran error, y el Dashboard se queda sin el equivalente en otra moneda; lo demás funciona |
| `subscription-service` | Lo gratuito funciona; lo premium dice "intenta de nuevo" (503 `entitlements_unavailable`), nunca "paga". Planes y Ajustes reciben el 503 `service_unavailable` del Gateway |
| La TRM | Se usa la última tasa conocida o la fija de 3200, marcada `cached` o `fallback` |
| Redis | Los movimientos se guardan en el outbox; los reportes quedan PENDING; las cachés se saltan, aunque cada lectura espera 4 s al DNS. Todo se recupera al volver, y el reporte se completa en a lo sumo unos 2 minutos |
| `analytics-celery` | El reporte espera PENDING en la cola y se completa al volver el worker |
| Django (identity) | Es el punto único de autenticación: sin él no hay páginas ni validación de tokens. El Gateway responde 503 `service_unavailable` en 2 s a todo lo que depende de Django y nunca deja pasar una petición sin verificar (fail-closed). Al volver, se recupera sin reiniciar Nginx (§3.5). Los correos pendientes se reintentan con espera creciente |
| PostgreSQL | El servicio afectado responde error; Compose lo reinicia y los pasos de migración no dejan arrancar contra un esquema incompleto |

**¿Y el servicio del equipo aliado?**
No tenemos equipo aliado asignado. El diseño está en ADR-13: un puerto `AllyServiceProvider` con un `MockAllyAdapter` de respaldo. No está implementado porque no inventamos un contrato que no conocemos. El endpoint que **exponemos** sí está en línea.
