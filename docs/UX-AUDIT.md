# Finty — Auditoría de UI/UX (E2-M9a)

Auditoría del frontend de la Entrega 2 para el criterio **Resiliencia y UX** del enunciado. Tiene tres partes:

1. Una **revisión automatizada de accesibilidad** con Lighthouse y axe-core.
2. Una **evaluación heurística** con las 10 heurísticas de Nielsen.
3. Los **4 recorridos de tarea** principales.

Cada hallazgo grave tiene su corrección en un commit propio, y las puntuaciones se midieron antes y después de corregir.

Fecha: 2026-10-22. Stack: Docker Compose local (`http://localhost`), el mismo que se despliega en EC2 (ADR-16).

---

## 1. Metodología

### 1.1 Revisión automatizada

| | |
|---|---|
| Herramientas | **Lighthouse 13.5.0** (categorías *Accesibilidad* y *Buenas prácticas*) y **axe-core 4.14.0**, con **puppeteer-core 25.16.0** sobre el Chrome instalado. Son dependencias de desarrollo de `tools/ux-audit/package.json`; `tools/` y `node_modules/` están en `.dockerignore`, así que no entran en ninguna imagen |
| Páginas | Las 11: ingreso, registro, dashboard, movimientos, insights, inversiones, perfil de riesgo, planes, pago (checkout simulado), bienvenida y ajustes |
| Variantes | Dos idiomas (`es`, `en`) × dos anchos (1440 y 390 px). Las 9 páginas autenticadas, con una usuaria **Free** y una **Premium**; ingreso y registro, sin sesión. En total, **80 combinaciones** |
| Datos | El script crea las dos usuarias por la API. Cada una tiene dos cuentas (COP y USD) y cinco meses de movimientos, con gastos recurrentes y un pico de gasto que dispara un insight. La Premium además pagó el checkout simulado y tiene perfil de riesgo y un plan de inversión |
| Lighthouse | Navegación con emulación de escritorio o móvil según el ancho, sin limitar la red (`throttlingMethod: provided`) y conservando la sesión (`disableStorageReset`) |
| axe | Se inyecta después de que la página termina de cargar sus datos (sin esqueletos ni `aria-busy`) y reporta todas las reglas de WCAG 2.x A/AA |
| Criterio | Se corrige todo hallazgo **serio** o **crítico** de axe y todo lo que baje la accesibilidad de Lighthouse de 100. El objetivo del enunciado es 90 o más en todas las páginas |

Para repetirla:

```bash
cd tools/ux-audit
npm install
node audit.mjs despues            # escribe docs/ux-audit/despues.json y despues.md
UX_AUDIT_ONLY=pago,insights node audit.mjs prueba     # solo algunas páginas
```

Los resultados completos, una fila por combinación con cada violación de axe, están en [`ux-audit/antes.json`](ux-audit/antes.json) y [`ux-audit/despues.json`](ux-audit/despues.json). Hay un resumen tabular en los `.md` del mismo nombre.

### 1.2 Evaluación heurística

Se revisó cada pantalla en los dos anchos, sobre las capturas de la corrida automatizada, contra las **10 heurísticas de Nielsen**:

| | |
|---|---|
| H1 | Visibilidad del estado del sistema |
| H2 | Coincidencia entre el sistema y el mundo real |
| H3 | Control y libertad del usuario |
| H4 | Consistencia y estándares |
| H5 | Prevención de errores |
| H6 | Reconocer antes que recordar |
| H7 | Flexibilidad y eficiencia de uso |
| H8 | Diseño estético y minimalista |
| H9 | Ayudar a reconocer, diagnosticar y recuperarse de errores |
| H10 | Ayuda y documentación |

Escala de severidad de Nielsen:

| Severidad | Significado |
|---|---|
| 0 | No es un problema de usabilidad |
| 1 | Cosmético: se corrige si sobra tiempo |
| 2 | Menor: prioridad baja |
| 3 | Mayor: prioridad alta |
| 4 | Catástrofe: hay que corregirlo antes de entregar |

Se corrigen los de severidad 3 y 4; los menores quedan documentados.

### 1.3 Recorridos de tarea

Los 4 journeys principales se recorrieron en Chrome real, en los dos idiomas y a 1440 y 390 px. Los scripts de los recorridos de E2-M8b y E2-M7 dejan la evidencia en el log y las capturas. De cada journey se cuentan los pasos (acciones del usuario que avanzan la tarea) y se anotan los puntos de fricción.

---

## 2. Resultados automatizados

### 2.1 Puntuaciones antes y después

| Página | Combinaciones | Accesibilidad antes (mín.) | Accesibilidad después (mín.) | Buenas prácticas antes / después (mín.) | axe antes (crít./serio/mod./menor) | axe después |
|---|---|---|---|---|---|---|
| ingreso | 4 | 98 | 100 | 100 / 100 | 0/0/8/4 | 0/0/0/0 |
| registro | 4 | 98 | 100 | 100 / 100 | 0/0/8/4 | 0/0/0/0 |
| dashboard | 8 | 100 | 100 | 100 / 100 | 0/0/0/8 | 0/0/0/0 |
| movimientos | 8 | 100 | 100 | 100 / 100 | 0/0/0/8 | 0/0/0/0 |
| insights | 8 | 100 | 100 | 100 / 100 | 0/2/0/8 | 0/0/0/0 |
| inversiones | 8 | 100 | 100 | 96 / 96 | 0/0/0/8 | 0/0/0/0 |
| perfil-de-riesgo | 8 | 100 | 100 | 96 / 96 | 0/0/0/8 | 0/0/0/0 |
| planes | 8 | 100 | 100 | 100 / 100 | 0/0/0/8 | 0/0/0/0 |
| pago | 8 | 100 | 100 | 100 / 100 | 0/0/12/8 | 0/0/0/0 |
| bienvenida | 8 | 100 | 100 | 100 / 100 | 0/0/0/0 | 0/0/0/0 |
| ajustes | 8 | 100 | 100 | 100 / 100 | 0/0/0/8 | 0/0/0/0 |

- **Antes:** accesibilidad de 98 a 100 (promedio 99,8); 102 violaciones de axe (2 serias, 28 moderadas y 72 menores).
- **Después:** **accesibilidad de 100 en las 80 combinaciones y ninguna violación de axe**. El objetivo era 90 o más.
- **Buenas prácticas de 96** en inversiones y perfil de riesgo de la usuaria Free, igual antes y después. No es un problema de accesibilidad: es el aviso "errores en la consola" por el `404 risk_profile_not_found` de `GET /recommendations/risk-profile/` de quien todavía no respondió el cuestionario. La pantalla lo trata como el estado vacío esperado ("Aún no has respondido el cuestionario"), pero Chrome registra toda respuesta 404 en la consola. Cambiarlo exigiría cambiar el contrato (§10.8 de `ARCHITECTURE.md`), así que se acepta y queda documentado (A-02 de §2.2).

### 2.2 Hallazgos automatizados

| # | Regla (impacto) | Páginas | Problema | Corrección |
|---|---|---|---|---|
| A-01 | `scrollable-region-focusable` (**serio**) | insights (390 px, Premium) | La tabla de gastos recurrentes se desplaza en horizontal, pero su contenedor no recibe el foco: con teclado no se llega a las columnas ocultas | La región de la tabla tiene nombre y `tabindex="0"`, y en móvil las filas se apilan sin desplazamiento (`b263dab`) |
| A-02 | Buenas prácticas: errores en la consola | inversiones y perfil de riesgo (Free sin perfil) | El 404 del perfil que todavía no existe queda en la consola | Aceptado: es el contrato de la API; la interfaz lo muestra como estado vacío |
| A-03 | `landmark-one-main` (moderado) | ingreso, registro | La página no tiene `<main>` | El panel del formulario es el `<main>` (`6a2eafd`) |
| A-04 | `region` (moderado) | ingreso, registro, pago | Contenido fuera de landmarks: la presentación de ingreso y registro, y el aviso de demostración del checkout | La presentación es un `<header>`, y el aviso va dentro del encabezado del checkout (`6a2eafd`) |
| A-05 | `page-has-heading-one` (moderado) | pago (Premium) | Quien ya es Premium veía el checkout sin ningún `h1`: el formulario se reemplazaba por un estado sin título | El mensaje "Ya tienes el plan Premium" es el `h1` (`6a2eafd`) |
| A-06 | `aria-allowed-role` (menor) | todas las de la cabecera | El selector de idioma era un `<form role="group">`, rol no permitido en un formulario | Sin el rol: con su `aria-label`, el formulario ya es un landmark con nombre ("Idioma") (`6a2eafd`) |

---

## 3. Evaluación heurística

| # | Pantalla | Heurística | Sev. | Hallazgo | Evidencia | Corrección |
|---|---|---|---|---|---|---|
| H-01 | Movimientos (390 px) | H1, H8 | **3** | La tabla corta las columnas y el **monto**, el dato principal, queda fuera de la vista sin ninguna señal de que la tabla se desplaza | [antes](ux-audit/antes-movimientos-390.png) · [después](ux-audit/despues-movimientos-390.png) | **Corregido** (`b263dab`): en móvil cada fila es una tarjeta con la etiqueta de cada columna (`table--stack`) |
| H-02 | Movimientos (390 px) | H7 | **3** | El formulario "Registrar movimiento", que es la tarea principal de la pantalla, queda unos 2000 px por debajo de la lista de 20 movimientos | [antes](ux-audit/antes-movimientos-390.png) · [después](ux-audit/despues-movimientos-acceso-directo-390.png) | **Corregido** (`b263dab`): botón "Registrar movimiento" bajo el título, solo en móvil, que lleva al formulario |
| H-03 | Movimientos (390 px) | H1 | **3** | Al tocar un movimiento no cambia nada a la vista: el detalle (recategorizar, eliminar) se llena al final de la página | [antes](ux-audit/antes-movimientos-390.png) · [después](ux-audit/despues-movimientos-detalle-390.png) | **Corregido** (`b263dab`): el detalle se trae a la vista y su título recibe el foco, así también lo anuncia un lector de pantalla |
| H-04 | Insights (390 px) | H1, H8 | **3** | La tabla de gastos recurrentes oculta la última fecha y el monto promedio | [antes](ux-audit/antes-insights-390.png) · [después](ux-audit/despues-insights-390.png) | **Corregido** (`b263dab`): filas apiladas, igual que en Movimientos |
| H-05 | Bienvenida, sin Premium | H2 | 2 | Quien abre `/bienvenida/` sin haber pagado ve el sello de éxito junto a "Todavía no tienes Premium": la señal contradice el mensaje | [antes](ux-audit/antes-bienvenida-sin-premium-390.png) · [después](ux-audit/despues-bienvenida-sin-premium-390.png) | **Corregido** (`97797d2`): sin Premium, no hay sello. Se corrigió aunque es menor porque el cambio es de una línea |
| H-06 | Pago, ya Premium | H4 | 1 | La página perdía su título al reemplazar el formulario (además de A-05) | [antes](ux-audit/antes-pago-premium-1440.png) · [después](ux-audit/despues-pago-premium-1440.png) | **Corregido** junto con A-05 (`6a2eafd`) |
| H-07 | Movimientos (390 px) | H8 | 2 | Los seis filtros (búsqueda, tipo, cuenta, categoría, desde y hasta) ocupan unos 900 px antes de la lista | [después](ux-audit/despues-movimientos-acceso-directo-390.png) | Documentado. Propuesta: en móvil, dejar a la vista la búsqueda y plegar los demás filtros en un `<details>` "Más filtros" |
| H-08 | Inversiones (diálogo "Nuevo plan") | H5 | 2 | El horizonte no muestra su rango (1 a 600 meses): se descubre con el error de la API | — | Documentado. Propuesta: una ayuda bajo el campo con el rango, y `max="600"` en el `<input>` |
| H-09 | Formularios (en inglés) | H9 | 2 | Un 400 de validación de un servicio Flask llega en español aunque la interfaz esté en inglés. El frontend valida antes los campos obligatorios con textos traducidos, así que es raro verlo | — | Documentado como **D-31** de `ARCHITECTURE.md` §13 |
| H-10 | Insights e Inversiones | H4 | 1 | Los gastos recurrentes aparecen con su descripción normalizada en minúsculas («arriendo», «netflix»), distinta de como el usuario la escribió («Arriendo») | [Inversiones](ux-audit/inversiones-free-390.png) | Documentado: la normalización es la clave de agrupación de analytics (§6.5). Mostrar la descripción original exigiría que analytics guarde una forma de presentación |
| H-11 | Dashboard | H8 | 1 | La tasa de cambio y su fuente aparecen dos veces: en "Saldo total" y en la nota de "Tus cuentas" | [Dashboard](ux-audit/dashboard-free-390.png) | Documentado: cada tarjeta se entiende sola; se podría dejar la nota solo en "Tus cuentas" |
| H-12 | Ingreso y registro | H7 | 1 | No hay opción de mostrar la contraseña mientras se escribe | [Ingreso](ux-audit/ingreso-1440.png) | Documentado |
| H-13 | Bienvenida (390 px) | H8 | 1 | El botón "Ir al dashboard" parte su texto en dos líneas | [después](ux-audit/despues-bienvenida-sin-premium-390.png) | Documentado |
| H-14 | General | H10 | 1 | No hay una ayuda general. Cada regla se explica donde aparece: por qué se marcó un insight, cómo se agrupa un gasto recurrente, para qué sirve el perfil de riesgo y el aviso de que no es asesoría | [Perfil de riesgo](ux-audit/perfil-de-riesgo-390.png) | Documentado: la ayuda en contexto cubre las dudas de cada pantalla |

**Lo que se revisó y cumple** (severidad 0):

- **H1:**
  - Todas las regiones tienen estado de carga (esqueletos), vacío (con la acción principal) y error (con "Reintentar").
  - El reporte mensual muestra su progreso.
  - El checkout se deshabilita mientras envía.
- **H3:**
  - Se puede cancelar en el checkout, en los diálogos (Escape) y en la cancelación de la suscripción.
  - Eliminar un movimiento pide confirmación.
- **H4:**
  - Hay un solo sistema visual.
  - Los montos van sin signo cuando son cero y con el signo tipográfico cuando no lo son.
  - El idioma, los números y las fechas son consistentes por idioma.
- **H5:**
  - El checkout valida el formato en el navegador y nunca envía datos de tarjeta.
  - El cuestionario no se guarda incompleto.
- **H6:**
  - La navegación tiene cuatro secciones siempre visibles, y la sección activa queda a la vista en móvil.
  - El indicador de plan dice qué plan se tiene y a dónde lleva.
- **H9:**
  - Los errores de dominio se traducen por `code`, con texto accionable.
  - Un 403 premium lleva a Planes.
  - Un 503 de derechos dice "intenta de nuevo" y no invita a pagar.

---

## 4. Recorridos de tarea

Los pasos cuentan las acciones del usuario. Las cifras son las del recorrido en Chrome a 390 px; a 1440 px es igual, salvo donde se indica.

### J1 — Registrarse y crear la primera cuenta · JN-TB-01 pasos 1–2, JN-TB-04 pasos 1–2

| # | Acción | Pantalla |
|---|---|---|
| 1 | "Crear una cuenta" desde el ingreso | Ingreso → Registro |
| 2 | Escribir nombre, correo y contraseña, y "Crear cuenta" | Registro → Dashboard (la sesión queda iniciada: no hay que volver a ingresar) |
| 3 | "Crea tu primera cuenta" en el estado vacío, o "+ Nueva cuenta" | Dashboard → diálogo |
| 4 | Nombre, tipo, moneda y saldo inicial, y "Crear cuenta" | Diálogo → Dashboard con la cuenta y el saldo total |

**4 pasos.** Fricción ya resuelta en E2-M8a:
- El registro deja la sesión iniciada.
- El estado vacío ofrece crear la cuenta en lugar de mostrar ceros.
- El saldo acepta el separador de miles de cada idioma (`500.000` o `500,000`).

Fricción pendiente: H-12 (mostrar la contraseña, severidad 1).

### J2 — Registrar y recategorizar un movimiento · JN-TB-01 paso 3, JN-TB-02 paso 2

| # | Acción | Pantalla |
|---|---|---|
| 1 | "Movimientos" en la cabecera | Movimientos |
| 2 | (Solo en móvil) "Registrar movimiento", que lleva al formulario | Movimientos |
| 3 | Tipo, monto y descripción (la cuenta y la fecha de hoy vienen elegidas; la categoría es automática), y "Guardar movimiento" | Aviso "Guardado en Compras · por reglas" y la fila nueva en la lista |
| 4 | Elegir el movimiento en la lista | Detalle con su procedencia |
| 5 | "Cambiar categoría" y "Recategorizar" | La fila queda marcada como manual |

**4 pasos en escritorio y 5 en móvil.** Fricción resuelta en E2-M9a:
- H-02: en móvil, el formulario quedaba 2000 px más abajo de la lista.
- H-03: en móvil, el detalle cambiaba fuera de la vista.
- H-01: la tabla ocultaba el monto.

Fricción pendiente: H-07 (filtros largos en móvil, severidad 2).

### J3 — Pasar a Premium · JN-TB-01 pasos 4–5 (funciones premium, INV-06)

| # | Acción | Pantalla |
|---|---|---|
| 1 | Desde cualquier bloqueo: el indicador "Plan Free · Mejorar", la tarjeta Premium del dashboard, "Ver planes" en Insights, "Desbloquear" en Inversiones o un 403 | Planes |
| 2 | "Pasar a Premium" | Checkout simulado |
| 3 | Número, nombre, vencimiento y CVC (el número se agrupa de a 4 y el vencimiento lleva la barra solos), y "Continuar · $ 29.900" | Bienvenida con los beneficios desbloqueados |
| 4 | "Ver mis insights" | Insights |

**4 pasos.** Fricción resuelta:
- En E2-M8b: todos los bloqueos llevan a Planes; el formato de la tarjeta se valida antes de enviar y los errores quedan junto a cada campo; el aviso "Modo demostración" está visible antes de escribir.
- En E2-M9a: Pago sin título para quien ya es Premium (H-06), y Bienvenida sin Premium con un sello de éxito (H-05).

### J4 — Crear un perfil de riesgo y un plan de inversión · JN-TB-01 paso 5

| # | Acción | Pantalla |
|---|---|---|
| 1 | "Inversiones" en la cabecera | Inversiones |
| 2 | "Responder el cuestionario" (o "Actualizar perfil") | Perfil de riesgo |
| 3 | Elegir una opción en cada una de las 5 preguntas | Perfil de riesgo |
| 4 | "Guardar perfil" | Resultado: tipo de perfil, puntaje e instrumento sugerido |
| 5 | "Ver mis inversiones" | Inversiones con el instrumento sugerido |
| 6 | "+ Nuevo plan": el instrumento ya viene filtrado al perfil; aporte, moneda y horizonte, y "Guardar plan" | Tarjeta del plan con su proyección |

**6 pasos, con 5 respuestas en el paso 3.** Fricción resuelta:
- En E2-M8b: el resultado lo calcula la API, no el navegador; el diálogo del plan solo ofrece los instrumentos del perfil.
- Para un usuario Free, la parte de inversión muestra la invitación a Premium en lugar de un error.

Fricción pendiente: H-08 (rango del horizonte, severidad 2).

---

## 5. Correcciones

| Commit | Tipo de problema | Hallazgos |
|---|---|---|
| `6a2eafd` | Landmarks y roles (axe) | A-03, A-04, A-05, A-06, H-06 |
| `b263dab` | Tablas y detalle legibles en móvil | A-01, H-01, H-02, H-03, H-04 |
| `97797d2` | Señal contradictoria en la bienvenida | H-05 |

Las tres se verificaron con la corrida "después" y con un recorrido en Chrome a 390 px. Ese recorrido comprobó cuatro cosas:
- La tabla apilada no desborda.
- El botón lleva al formulario.
- Al elegir un movimiento, el foco pasa al detalle.
- En escritorio la tabla sigue igual.
