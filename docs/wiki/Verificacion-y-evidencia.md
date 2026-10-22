# Verificación y evidencia

El mapa completo de cada criterio al test que lo demuestra está en [`docs/VERIFICATION.md`](https://github.com/tsepulvedf/Finty/blob/main/docs/VERIFICATION.md), incluido el **checklist final del enunciado**. Esta página resume cómo se verifica Finty.

## Suites

Estado al 2026-10-22, todas en verde:

| Suite | Tests | Qué cubre |
|---|---|---|
| Monolito (`core`, `identity`, frontend) | 369 | Identidad, verificación interna del token, plantillas, i18n (A-23), checkout sin datos de tarjeta, tests de Node del JavaScript y reglas de capas por AST (A-15) |
| `finance-service` | 744 | Builder e invariantes, saldo bajo bloqueo (`FOR UPDATE`), propiedad, categorización remota con respaldo, outbox y relay |
| `categorization-service` | 853 | Factory por entorno, LSP con entradas hostiles, procedencia veraz |
| `analytics-service` | 260 | Proyección idempotente, dashboard, insights, gating premium, reportes y tareas |
| `recommendation-service` | 197 | Perfil de riesgo, recomendaciones explicables, cadena de degradación de la TRM y gating |
| `subscription-service` | 155 | INV-05, idempotencia del pago, rechazo de datos de tarjeta, avisos una sola vez (reloj controlado) |
| Contrato de caja negra (`tests/contract/`) | 172 + 8 opcionales | El sistema completo a través del Gateway, sin importar código |
| Contratos estáticos y documentación (`tests/services/`) | 20 | Eventos entre servicios, catálogo de categorías, convención de Celery en Compose, diagramas Mermaid y enlaces de esta Wiki |

**Arquitectura verificada por AST en cada servicio:**
- `domain/` no importa el framework, el ORM ni `infra/` (A-16).
- Los blueprints no tienen lógica.
- Los modelos son anémicos.
- Los servicios no conocen implementaciones concretas.
- Las tareas de Celery solo llaman a casos de uso.

## Suite de contrato

`tests/contract/` habla con el sistema **solo por HTTP**, como lo haría un cliente. Es la red de seguridad del Strangler (A-20): pasó idéntica antes de conmutar `finance`, después de conmutarlo y tras retirarlo del monolito.

```bash
docker compose up -d --build
cd tests/contract && CONTRACT_BASE_URL=http://localhost python -m pytest -q
```

Los 8 tests opcionales necesitan preparar el entorno. Por ejemplo, `CONTRACT_CATEGORIZATION_DOWN=1` exige detener `categorization-service`. El throttling y los modos del categorizador también se ejercitan aparte.

## Evidencia en `tests/contract/runs/`

Corridas reales guardadas como texto, con fecha:

| Archivo | Qué demuestra |
|---|---|
| `2026-10-20-antes-de-conmutar.txt`, `2026-10-20-despues-de-conmutar.txt`, `2026-10-20-tras-retirar-finance-del-monolito.txt` | El Strangler: el mismo contrato en las tres etapas (A-20) |
| `2026-10-20-a13-a22-categorizacion.txt` | El Factory observable desde fuera y el respaldo con el servicio caído |
| `2026-10-20-outbox-eventos.txt`, `2026-10-20-analytics-eventos.txt` | Eventos del outbox al stream y su consumo idempotente |
| `2026-10-21-recomendaciones-y-tasas.txt` | TRM `live` → `cached` → `fallback` y recomendaciones con analytics caído |
| `2026-10-21-suscripciones-y-gating.txt` | De Free a Premium, gating y `subscription-service` caído |
| `2026-10-22-tareas-asincronas.txt` | Reporte asíncrono, correo de bienvenida y resiliencia de Celery |
| `2026-10-22-seed-demo.txt` | Datos de demostración idempotentes |
| `2026-10-22-resiliencia-sustentacion.txt` | El ensayo de las demos de resiliencia de la sustentación |

Están en [`tests/contract/runs/`](https://github.com/tsepulvedf/Finty/tree/main/tests/contract/runs).

## Documentación verificada

```bash
cd tools/mermaid && npm install && node check-mermaid.mjs   # cada bloque Mermaid del repositorio compila
python tools/check_wiki_links.py                            # sin enlaces rotos en la Wiki ni citas desactualizadas
```

Ambos corren también dentro de `tests/services/test_docs.py`. El de Mermaid se omite si Node o `tools/mermaid/node_modules` no están instalados.

## Auditoría de invariantes en el stack

```bash
docker compose exec finance-service flask verify-invariants
```

Recalcula el saldo de cada cuenta desde sus movimientos y lo compara con el persistido (INV-07).
