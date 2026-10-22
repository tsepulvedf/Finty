# Eventos y tareas asíncronas

Cuando un servicio no necesita la respuesta de otro, no lo llama: **publica un evento** o **encola una tarea** (ADR-15). Redis cumple los dos papeles, en bases lógicas distintas:

| Base de Redis | Contenido |
|---|---|
| 0 | El stream `finty.finance.events` y las cachés de derechos premium (`finty:entitlements:*`) y de tasas (`finty:fx:*`) |
| 1 | El broker de Celery, con una cola por servicio: `analytics` y `subscription` |

Redis corre con AOF (`appendfsync everysec`) para no perder entradas del stream en un reinicio.

## Outbox transaccional y Redis Streams

`finance-service` publica `TransactionManuallyAdded`, `TransactionCategorized` y `TransactionDeleted`:

1. **Outbox:** `TransactionService` escribe el evento en la tabla `outbox_event` **dentro de la misma transacción** que el cambio de negocio. O quedan los dos o no queda ninguno: publicar directo a Redis desde la petición dejaría una ventana en la que la base confirma y Redis no recibe.
2. **Relay:** `finance-outbox-relay` (`flask relay-outbox`) lee los pendientes en orden con `FOR UPDATE SKIP LOCKED`, los publica con `XADD` y marca cada uno. Si Redis no responde, espera y reintenta sin perder nada.
3. **Consumidor:** `analytics-worker` (`flask consume-events`) lee con el grupo `analytics` (`XREADGROUP`) y aplica cada evento en su propia transacción. Hace `XACK` solo después del `COMMIT`.
4. **Idempotencia:** la entrega es al menos una vez. Un evento repetido choca con la clave primaria de `processed_event` y no se aplica dos veces.
5. **Recuperación:** al arrancar, el worker reclama los pendientes de un worker anterior (`XAUTOCLAIM`).

```mermaid
sequenceDiagram
    autonumber
    actor U as Navegador
    participant NGX as nginx
    participant FIN as finance-service
    participant CAT as categorization-service
    participant RL as finance-outbox-relay
    participant RD as Redis Stream finty.finance.events
    participant W as analytics-worker
    participant DB as finty_analytics
    participant AN as analytics-service

    U->>NGX: POST /api/v1/transactions/ (Token)
    NGX->>FIN: auth_request ok → X-User-Id
    FIN->>CAT: POST /v1/suggestions/ (timeout 1 s)
    alt responde con una categoría del catálogo
        CAT-->>FIN: {category_name, confidence, source}
    else timeout, error o fuera de contrato
        FIN->>FIN: RuleBasedCategorizer local (procedencia rule)
    end
    rect rgb(240, 245, 250)
        Note over FIN: una transacción de finty_finance
        FIN->>FIN: INSERT transaction, recalcula el saldo (FOR UPDATE)
        FIN->>FIN: INSERT outbox_event TransactionManuallyAdded
    end
    FIN-->>U: 201 (transacción y evento en un solo COMMIT)

    RL->>RD: XADD TransactionManuallyAdded
    W->>RD: XREADGROUP analytics >
    RD-->>W: entrada pendiente para el grupo
    rect rgb(240, 245, 250)
        Note over W,DB: una transacción
        W->>DB: INSERT processed_event ON CONFLICT DO NOTHING
        alt event_id nuevo
            W->>DB: upsert de transaction_fact (o lápida si es TransactionDeleted)
        else ya procesado
            Note over W: duplicado: no toca los hechos
        end
        W->>DB: COMMIT
    end
    W->>RD: XACK (solo después del COMMIT)

    U->>NGX: GET /api/v1/analytics/dashboard/?period=2026-10 (Token)
    NGX->>AN: auth_request ok → X-User-Id
    AN->>DB: SELECT hechos vigentes del usuario (período y tendencia)
    AN-->>U: 200 Dashboard por moneda, calculado al leer

    Note over U,AN: Consistencia eventual: entre el 201 y el dashboard actualizado pasan unos instantes.<br/>Si el worker está detenido, finance sigue respondiendo, el worker se pone al día al volver.
```

**Consistencia eventual:** el dashboard refleja un movimiento alrededor de un segundo después de registrarlo. Si `analytics-worker` se detiene, `finance-service` sigue funcionando y el worker se pone al día al volver.

## Celery

| Convención (todas las tareas) | |
|---|---|
| Versión | `celery==5.5.3` |
| Broker | Redis, base 1; **sin result backend**: el estado que ve el usuario vive en la base del servicio |
| Entrega | `acks_late`, `reject_on_worker_lost` y una tarea a la vez: si el worker muere, la tarea vuelve a la cola. Toda tarea es **idempotente** |
| Reintentos | Espera creciente con *jitter* ante errores transitorios: la base, la red o identity |
| Límites | 60 s suave y 90 s duro |
| Diseño | **Las tareas son mecanismo de entrega:** cada una solo llama a un caso de uso de `services.py` (lo verifica un test de arquitectura) |
| Contenedores | La imagen de su servicio, sin puertos, con `restart: unless-stopped` y un solo beat por servicio |

| Tarea | Contenedor | Cuándo | Qué hace |
|---|---|---|---|
| `analytics.generate_monthly_report` | `analytics-celery` | Al pedir un reporte | Arma el CSV del mes, con encabezados en el idioma de la petición, y lo deja READY o FAILED |
| `analytics.requeue_pending_reports` | `analytics-celery-beat` | Cada 60 s (`REPORT_REQUEUE_EVERY_SECONDS`) | Vuelve a encolar los PENDING de más de 60 s (`REPORT_STALE_AFTER_SECONDS`) |
| `analytics.purge_expired_reports` | `analytics-celery-beat` | Cada día, 3:30 | Borra los reportes de más de 7 días |
| `subscription.send_premium_welcome` | `subscription-worker` | Al activar Premium | Envía la bienvenida en el idioma del usuario |
| `subscription.send_missing_welcomes` | `subscription-beat` | Cada 15 min | Red de seguridad: las bienvenidas que no se pudieron encolar en las últimas 24 h |
| `subscription.notify_expiring_subscriptions` | `subscription-beat` | Cada día, 9:00 | Avisa 3 días antes del fin del período |
| `subscription.expire_subscriptions` | `subscription-beat` | Cada 15 min | Pasa a EXPIRED las vencidas |

**Cada aviso sale una sola vez** por usuario, tipo y período: lo garantiza una restricción única en `sent_notification`.

## Reporte mensual asíncrono

```mermaid
sequenceDiagram
    autonumber
    actor U as Navegador
    participant NGX as nginx
    participant AN as analytics-service
    participant DB as finty_analytics
    participant RD as Redis (base 1, cola analytics)
    participant W as analytics-celery
    participant B as analytics-celery-beat

    U->>NGX: POST /api/v1/analytics/reports/ {period} · Accept-Language: es
    NGX->>AN: auth_request ok → X-User-Id
    AN->>AN: periodo dentro de la ventana del plan (INV-06)
    AN->>DB: INSERT monthly_report PENDING + COMMIT
    AN->>RD: send_task analytics.generate_monthly_report(id)
    Note over AN,RD: si el broker no responde, se registra y el reporte sigue PENDING
    AN-->>U: 202 {id, status: PENDING}
    loop cada 1,5 s (el frontend)
        U->>AN: GET /reports/{id}/ (por el Gateway)
        AN-->>U: {status: PENDING}
    end
    RD-->>W: mensaje (acks_late)
    rect rgb(240, 245, 250)
        W->>DB: SELECT ... FOR UPDATE SKIP LOCKED
        alt ya no esta PENDING
            W-->>RD: ack (idempotente: no hace nada)
        else PENDING
            W->>DB: hechos del periodo del usuario
            W->>W: MonthlyReport.build → CSV en su idioma
            W->>DB: content, READY, completed_at + COMMIT
        end
    end
    W-->>RD: ack
    Note over W,DB: error transitorio: reintento con espera creciente y el reporte sigue PENDING<br/>otro error: FAILED
    B->>RD: cada 60 s: requeue_pending_reports
    Note over B,RD: vuelve a encolar los PENDING de mas de 60 s (configurable)
    U->>AN: GET /reports/{id}/ → READY
    U->>AN: GET /reports/{id}/download/ (con el token)
    AN-->>U: 200 text/csv · attachment, filename="finty-reporte-AAAA-MM.csv"
```

## Vencimiento con aviso

```mermaid
sequenceDiagram
    autonumber
    participant B as subscription-beat
    participant RD as Redis (base 1, cola subscription)
    participant W as subscription-worker
    participant DB as finty_subscription
    participant ID as django (identity)
    participant M as correo (consola o archivo)

    B->>RD: 9:00 de Bogota: notify_expiring_subscriptions
    RD-->>W: mensaje (acks_late)
    W->>DB: ACTIVE o CANCELED con fin en los proximos 3 dias
    loop por cada una
        rect rgb(240, 245, 250)
            W->>DB: INSERT sent_notification (usuario, tipo, periodo) ON CONFLICT DO NOTHING
            alt ya existia
                W->>W: ya enviado: no se repite
            else nuevo
                W->>ID: GET /internal/users/{id}/contact/ (timeout 2 s)
                alt identity no responde
                    W->>DB: ROLLBACK (sin registro)
                    W-->>RD: reintento con espera creciente
                else responde {email, display_name, language}
                    W->>M: correo en su idioma: "Tu plan Premium termina el ..."
                    W->>DB: COMMIT
                end
            end
        end
    end
    B->>RD: cada 15 min: expire_subscriptions
    RD-->>W: mensaje
    W->>DB: UPDATE ACTIVE/CANCELED con fin <= ahora → EXPIRED + COMMIT
    Note over W,DB: idempotente: una ya vencida no cambia. La lectura ya la mostraba EXPIRED.<br/>esta tarea deja escrito el estado y libera el lugar unico del usuario
```
