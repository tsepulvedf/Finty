# Frontend, UX e i18n

## Plantillas Django y JavaScript por pantalla

El cliente de la Entrega 1 era un HTML estático. En la Entrega 2 lo reemplazan **plantillas Django** servidas por el monolito, que son `TemplateView` sin contexto: la plantilla aporta estructura y textos traducidos, y el JavaScript de cada pantalla pide los datos a `/api/v1/` en el mismo origen, a través del Gateway. El frontend **no tiene reglas de negocio**:

- El puntaje del perfil de riesgo y la tasa de ahorro los calcula la API.
- Las comparaciones entre meses y el saldo por moneda también.

Las 11 pantallas del diseño de Claude Design (`docs/design/`):

| Grupo | Pantallas |
|---|---|
| Acceso | Ingreso y registro |
| Gratuitas | Dashboard (comparaciones, saldo por moneda con su equivalente, tendencia y reporte descargable) y Movimientos (búsqueda, filtros y recategorización) |
| Premium | Insights e Inversiones (recomendaciones, instrumento sugerido y planes) |
| Perfil y plan | Perfil de riesgo, Planes, Checkout simulado, Bienvenida y Ajustes (perfil, idioma, moneda, suscripción y cierre de sesión) |

Cada región tiene estado de carga, vacío y error.

## i18n con gettext

| | |
|---|---|
| Idiomas | Español e inglés, con selector ES/EN visible y el idioma guardado en el perfil |
| Plantillas | `{% translate %}` y `{% blocktranslate %}` |
| JavaScript | `gettext()` y `ngettext()` del `JavaScriptCatalog` de Django (`/jsi18n/`) |
| Errores de la API | Los servicios responden un `code` estable, y el frontend lo traduce en un solo módulo, `codes.js`. Por eso los servicios Flask no necesitan Flask-Babel |
| Catálogos | `locale/{es,en}/LC_MESSAGES/` (`django.po` y `djangojs.po`); los `.mo` se compilan en el build de la imagen |
| Cero textos quemados (A-23) | Tres tests: uno revisa todas las plantillas, otro analiza el JavaScript (falla si arma texto visible con literales fuera de gettext) y otro exige catálogos completos, sin entradas vacías ni `fuzzy` |

## Auditoría de UI/UX

Resumen de [`docs/UX-AUDIT.md`](https://github.com/tsepulvedf/Finty/blob/main/docs/UX-AUDIT.md):

| | Antes | Después |
|---|---|---|
| Lighthouse, accesibilidad | 98–100 | **100** en las 80 combinaciones (11 páginas × es/en × 1440/390 px × Free/Premium) |
| Violaciones de axe-core | 102 (2 serias) | **0** |
| Hallazgos heurísticos (Nielsen) de severidad 3 | 4 | 0: todos corregidos |

Hallazgos corregidos:
- En móvil, las tablas de Movimientos e Insights escondían el monto. Ahora se apilan.
- El formulario de Movimientos quedaba lejos en móvil. Ahora tiene un acceso directo.
- Al elegir un movimiento, el detalle cambiaba fuera de la vista. Ahora se trae a la vista con el foco.
- Landmarks y roles que reportó axe.

Los hallazgos menores quedan documentados con su propuesta.

Los 4 recorridos de tarea, con sus pasos y su fricción, están en el documento: registrarse y crear la primera cuenta (4 pasos), registrar y recategorizar (4 en escritorio, 5 en móvil), pasar a Premium (4) y crear el perfil de riesgo y un plan (6).

Se repite con:

```bash
cd tools/ux-audit && npm install && node audit.mjs despues    # con el stack en Docker
```

## Accesibilidad y diseño adaptable

- **Marcado:** elementos nativos (`<button>`, `<label>`, `<dialog>`, `<fieldset>`), enlace para saltar al contenido, foco visible y `aria-live` en los avisos.
- **Toque:** objetivos táctiles de 44 px.
- **Navegación en móvil:** una fila con desplazamiento horizontal y la sección activa a la vista.
- **Montos:** un monto en cero se muestra sin signo (`$ 0`).
