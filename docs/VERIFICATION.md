# Finty — Guía de verificación

Mapea cada criterio del **Anexo A** de [`ARCHITECTURE.md`](ARCHITECTURE.md) al test que lo demuestra y al comando que lo aísla.

**Desde E2-M3a** el contexto `finance` ya no vive en el monolito: lo sirve `services/finance-service/` (ADR-08). **Desde E2-M3b** la categorización (los categorizadores y `CategorizerFactory`) vive en `services/categorization-service/`, y `finance-service` la consume por HTTP con un respaldo local. Por eso los criterios de la Entrega 1 que hablaban de cuentas, transacciones, categorización y balance se verifican ahora en la suite de ese servicio. En el monolito quedan `core` e `identity`. El criterio autoritativo de capas sigue siendo el análisis del AST (A-15 en el monolito, A-16 en el servicio); un `grep` es solo una comprobación rápida.

Estado a la fecha de este documento (2026-10-22, E2-M7):

| Suite | Tests | Cómo se corre |
|---|---|---|
| Monolito (`core`, `identity`, frontend) | **369**, todos en verde (incluye los tests de Node de `frontend/tests/js/`) | `pytest` en la raíz |
| `finance-service` | **744**, todos en verde | `pytest` en `services/finance-service/` (ver README) |
| `categorization-service` | **853**, todos en verde | `pytest` en `services/categorization-service/`, sin base de datos |
| `analytics-service` | **250**, todos en verde | `pytest` en `services/analytics-service/` con `ANALYTICS_TEST_DATABASE_URL` (ver README) |
| `recommendation-service` | **197**, todos en verde | `pytest` en `services/recommendation-service/` con `RECOMMENDATION_TEST_DATABASE_URL` (ver README) |
| `subscription-service` | **142**, todos en verde | `pytest` en `services/subscription-service/` con `SUBSCRIPTION_TEST_DATABASE_URL` (ver README) |
| Contrato de caja negra (A-20) | **172**, más 8 opcionales (2 de throttling, A-13, dos de A-22, la degradación de A-28 y los dos de A-32) | `CONTRACT_BASE_URL=http://localhost pytest` en `tests/contract/` |
| Contratos estáticos entre servicios | **18** (incluye la convención de Celery en Compose, que se omite sin Docker) | `pytest` en `tests/services/` |

En las tablas, `fs/` abrevia `services/finance-service/tests/`, `cs/` abrevia `services/categorization-service/tests/`, `as/` abrevia `services/analytics-service/tests/`, `rs/` abrevia `services/recommendation-service/tests/` y `ss/` abrevia `services/subscription-service/tests/`.

---

## Criterios de la Entrega 1

| Criterio | Qué exige | Test | Estado |
|---|---|---|---|
| **A-01** | `domain/` no depende de Django | `core/tests/test_architecture.py::TestPurezaDelDominio` para `core/domain/`; `fs/test_architecture.py::TestPurezaDelDominio` (A-16) para el dominio de finanzas | ✅ |
| **A-02** | Vistas sin lógica de negocio | `core/tests/test_architecture.py::TestVistasSinLogica` (identity); `fs/test_architecture.py::TestBlueprintsSinLogica` | ✅ |
| **A-03** | Modelos sin lógica de negocio | `core/tests/test_architecture.py::TestModelosAnemicos` (`User`, `UserProfile`); `fs/test_architecture.py::TestModelosAnemicos` (`Account`, `Transaction`, `Category`) | ✅ |
| **A-04** | Factory conmutable por entorno | `cs/categorization/test_categorizer_factory.py` — despacho por `CATEGORIZER_PROVIDER`, insensible a mayúsculas, y `ConfigurationError` ante un valor desconocido; `cs/api/test_suggestions.py::TestFactoryPorEntorno` por HTTP | ✅ |
| **A-05** | Builder valida antes de construir | `fs/domain/test_builders.py::TestInvariantes` (monto cero, negativo, moneda distinta, fecha futura, cuenta archivada) y `TestCamposObligatorios` | ✅ |
| **A-06** | Balance consistente (INV-07 según C-17) | `fs/test_opening_balance.py::TestInv07ConAperturaDistintaDeCero` y `fs/test_services.py::TestRegistroYBalance::test_inv_07_tras_varias_transacciones_mezcladas` | ✅ |
| **A-07** | Ownership aplicado | `fs/test_services.py::TestPropiedad`, `fs/api/test_contract.py::TestAislamientoEntreUsuarios` y, a través del Gateway, `tests/contract/test_isolation.py` (A-19) | ✅ |
| **A-08** | LSP en categorizadores | `fs/test_service_lsp.py::TestLSPEnElServicio` — la misma suite con `RemoteCategorizer` (remoto arriba y caído), `RuleBasedCategorizer` y un doble; `cs/categorization/test_categorizer_lsp.py` con entradas hostiles sobre los tres categorizadores | ✅ |
| **A-09** | Builder no conoce el ORM | `fs/test_architecture.py::TestPurezaDelDominio` — `domain/` no importa `models`, `infra` ni `sqlalchemy` | ✅ |
| **A-10** | Servicio no conoce implementaciones concretas | `fs/test_architecture.py::TestServiciosSinImplementacionesConcretas` y `cs/test_architecture.py::TestServiciosSinImplementacionesConcretas` | ✅ |
| **A-11** | Escritura bajo bloqueo | `fs/test_services.py::TestBloqueo` — captura el SQL real y exige `FOR UPDATE` al registrar, eliminar y recalcular | ✅ |
| **A-12** | Categoría emitida siempre existe | Entre servicios: `tests/services/test_category_catalog.py` (las reglas del remoto contra la siembra de `finty_finance`, por AST) y `fs/test_categorization_client.py::TestCatalogoA12` (en ejecución, una sugerencia fuera del catálogo cae al respaldo). Las reglas del respaldo local: `fs/persistence/test_catalog_contract.py` | ✅ |
| **A-13** | El Factory es observable desde fuera | Por el Gateway: `tests/contract/test_categorization.py` con `CONTRACT_CATEGORIZER_PROVIDER=RULE` y `=MOCK` (evidencia en `tests/contract/runs/2026-10-20-a13-a22-categorizacion.txt`). Además `cs/api/test_suggestions.py::TestFactoryPorEntorno` y `fs/api/test_contract.py::TestCategorizacionRemota` | ✅ |
| **A-14** | La procedencia registrada es veraz | `cs/test_categorization_provenance.py` (cada categorizador declara la suya; la degradación reporta la del respaldo) y `fs/test_categorization_provenance.py` (la del remoto llega a la fila; si actúa el respaldo, `rule`; los cuatro valores se persisten) | ✅ |
| **A-15** | Reglas de capas verificadas en la suite | `core/tests/test_architecture.py` (monolito) y `fs/test_architecture.py` (servicio), ambos por AST | ✅ |

## Criterios de la Entrega 2 verificados hasta hoy

| Criterio | Test | Estado |
|---|---|---|
| **A-16** | `fs/test_architecture.py::TestPurezaDelDominio`, `as/test_architecture.py::TestPurezaDelDominio`, `rs/test_architecture.py::TestPurezaDelDominio`, `ss/test_architecture.py::TestPurezaDelDominio` | ✅ |
| **A-17** | `docker compose config`: solo `nginx` declara `ports` (verificado en E2-M1a y E2-M2a) | ✅ |
| **A-18** | `tests/contract/test_auth.py::TestA18XUserIdDelCliente` | ✅ |
| **A-19** | `tests/contract/test_isolation.py` | ✅ |
| **A-20** | `tests/contract/` — mismo resultado antes y después de conmutar, y tras retirar `finance` del monolito (`tests/contract/runs/`) | ✅ |
| **A-21** | `services/finance-service/.env.docker`, `services/analytics-service/.env.docker`, `services/recommendation-service/.env.docker` y `services/subscription-service/.env.docker` solo contienen `DATABASE_URL` (cada uno, la de su base) y `TIME_ZONE`; `categorization-service` no tiene base ni secretos | ✅ |
| **A-22** | Categorización: `tests/contract/test_categorization.py` con `CONTRACT_CATEGORIZATION_DOWN=1` y el servicio detenido (201 con `rule`); `fs/test_categorization_client.py::TestRespaldoA22` (timeout, conexión rechazada, 5xx, cuerpo inválido). Tasas: `rs/test_exchange_rate_service.py::TestCadenaDeDegradacion` y `rs/test_adapters.py::TestTrmExchangeRateProvider`; por el Gateway, `live` → `cached` → `fallback` en `tests/contract/runs/2026-10-21-recomendaciones-y-tasas.txt` | ✅ (categorización y tasas) |
| **A-23** | `core/tests/test_frontend.py::TestA23SinTextosQuemados` (ningún texto visible fuera de `{% translate %}` en todas las plantillas), `core/tests/test_frontend_a23_js.py` (ningún texto visible con literales en el JavaScript) y `TestCatalogos` (catálogos `es` y `en` completos, sin entradas vacías ni `fuzzy`) | ✅ |
| **A-24** | `curl http://<ip>/api/v1/health/` — pendiente del despliegue en EC2 | ⏳ |
| **A-25** | `as/test_projection.py` (`TestProyector`, `TestConsumidor`: duplicados, fuera de orden, lápida, `XACK` solo tras el commit) y `tests/services/test_event_contract.py` | ✅ |
| **A-26** | `tests/contract/test_analytics.py::TestResumenPublico::test_k_anonimato`, `as/api/test_api.py::TestResumenPublico` | ✅ |
| **A-27** | `tests/contract/test_analytics.py::TestDePuntaAPunta` (sondeo con límite de 15 s) | ✅ |
| **A-28** | `tests/contract/test_recommendations.py::TestDegradacion` con `CONTRACT_ANALYTICS_DOWN=1` y `analytics-service` detenido; `rs/api/test_api.py::TestRecomendaciones::test_analytics_caido_degrada_sin_500`; evidencia en `runs/` | ✅ |
| **A-29** | `tests/contract/test_recommendations.py::TestInversionPorPerfil`; `rs/domain/test_recommendation_domain.py::TestInversion` | ✅ |
| **A-30** | `ss/domain/test_subscription_domain.py::TestInv05`; `ss/api/test_api.py::TestCheckout` y `TestIdempotencia` (confirmar dos veces no extiende; el índice único impide dos vigentes) | ✅ |
| Sin datos de tarjeta (ADR-14) | `ss/api/test_card_data.py`: `card_number`, `cvc`, `expiry` y cualquier otro campo además de `plan` → 400, sin crear filas ni llamar a la pasarela, y ningún valor aparece en la respuesta ni en el log; `tests/contract/test_subscriptions.py::TestSuscripciones::test_el_checkout_rechaza_datos_de_tarjeta` | ✅ |
| **A-31** | `tests/contract/test_subscriptions.py::TestSuscripciones::test_de_free_a_premium_y_cancelacion`; `as/api/test_gating.py`, `rs/api/test_gating.py`; evidencia en `tests/contract/runs/2026-10-21-suscripciones-y-gating.txt` | ✅ |
| **A-32** | `tests/contract/test_subscriptions.py::TestSubscriptionCaido` con `CONTRACT_SUBSCRIPTION_DOWN=1` y `subscription-service` detenido; `TestSubscriptionCaido` de `as/` y `rs/`; evidencia en `runs/` | ✅ |

## Eventos de dominio (ADR-15, E2-M4a)

| Qué se verifica | Test o evidencia |
|---|---|
| Los eventos son value objects inmutables y su serialización es la de §10.5 | `fs/test_outbox.py::TestEventosDeDominio`, `TestSerializacion` |
| Registrar, reclasificar y eliminar escriben su evento | `fs/test_outbox.py::TestCadaEscrituraRegistraSuEvento`, `TestPorHttp` |
| Atomicidad: sin cambio no hay evento, y sin evento no hay cambio | `fs/test_outbox.py::TestAtomicidad` |
| El relay publica en orden, no republica y no pierde eventos con el stream caído | `fs/test_outbox.py::TestRelay`, `TestComandos` |
| El backfill es idempotente | `fs/test_outbox.py::TestBackfill` |
| Por el Gateway: tres eventos en `XRANGE`; con `docker compose stop redis` el registro sigue y el evento se publica al volver | `tests/contract/runs/2026-10-20-outbox-eventos.txt` |

## Consumo en analytics-service (ADR-15, E2-M4b)

| Qué se verifica | Test o evidencia |
|---|---|
| Reglas de `Dashboard`, `Insight` y `SpendingPattern`, con sus números exactos y sus umbrales | `as/domain/test_analytics_domain.py` |
| Alta, reclasificación y borrado proyectados; duplicados, eventos viejos y lápidas | `as/test_projection.py::TestProyector` |
| `XACK` solo después del commit; pendientes recuperados; mensajes fuera de contrato descartados sin bloquear | `as/test_projection.py::TestConsumidor`, `TestComando`, `TestRedisEventSource` |
| Contrato HTTP de la API y del resumen público | `as/api/test_api.py`, `tests/contract/test_analytics.py` |
| De punta a punta por el Gateway, idempotencia al reprocesar el stream completo, resiliencia con el worker detenido y privacidad con menos de *k* usuarios | `tests/contract/runs/2026-10-20-analytics-eventos.txt` |

---

## Invariantes del catálogo (§7)

| Invariante | Dónde se hace cumplir | Test |
|---|---|---|
| INV-01 · Usuario autenticado | Gateway (`auth_request`) para `finance`; DRF para `identity` | `tests/contract/test_auth.py`, `identity/tests/test_gateway_auth.py`, `fs/api/test_contract.py::TestAutenticacionRequerida` |
| INV-02 · Transacción con cuenta existente | FK de SQLAlchemy | `fs/persistence/test_constraints.py::TestTransaccion::test_inv_02_la_cuenta_debe_existir` |
| INV-03 · Cuenta del usuario | Filtro por `user_id` de `X-User-Id` | `fs/test_services.py::TestPropiedad`, `tests/contract/test_isolation.py` |
| INV-04 · Monto distinto de cero | Dominio **y** `CHECK` | `fs/domain/test_transaction_rules.py::TestMontoNoCero`, `fs/persistence/test_constraints.py` |
| INV-07 · Balance consistente | `BalanceCalculator` bajo bloqueo | `fs/test_opening_balance.py`, `fs/test_services.py::TestRegistroYBalance`, `fs/test_verify_invariants.py` |
| INV-08 · Categoría tras procesar | `TransactionBuilder.build()` | `fs/domain/test_builders.py::TestCategorizacion`, `fs/test_verify_invariants.py::TestAuditarCategorizacion` |
| INV-09 · Tipo válido | Dominio **y** `CHECK` | `fs/domain/test_domain_value_objects.py`, `fs/persistence/test_constraints.py` |
| INV-10 · Email único | `unique=True` | `identity/tests/test_profile_service.py` |
| INV-11 · Monedas coincidentes | `Money` y `TransactionRules` | `fs/domain/test_money.py::TestMonedasDistintas`, `fs/domain/test_transaction_rules.py::TestMonedaCoincide` |
| INV-12 · Fecha no futura | `TransactionRules.ensure_date_not_future` | `fs/domain/test_transaction_rules.py::TestFechaNoFutura` |
| INV-13 · No borrar cuenta con transacciones | FK con `RESTRICT` | `fs/persistence/test_constraints.py::TestCuenta::test_inv_13_no_se_borra_una_cuenta_con_transacciones` |
| INV-14 · Saldo negativo solo en crédito | Servicio bajo bloqueo, `AccountBuilder` y `CHECK` sobre la apertura | `fs/test_services.py::TestAtomicidad`, `fs/persistence/test_constraints.py::TestCuenta` |
| INV-05 · Pago aprobado antes de activar | `Subscription.activate()` y `confirm_payment()` idempotente | `ss/domain/test_subscription_domain.py::TestInv05`, `ss/api/test_api.py::TestIdempotencia` |
| INV-06 · Premium requiere suscripción activa | Middleware `api/gating.py` de analytics y recommendation | `as/api/test_gating.py`, `rs/api/test_gating.py`, `tests/contract/test_subscriptions.py` |

---

## Auditoría de invariantes en el stack

```bash
docker compose exec finance-service flask verify-invariants          # todas las cuentas
docker compose exec finance-service flask verify-invariants --fix    # recalcula balances desviados
docker compose exec finance-service flask verify-invariants --user <user_id>
```

Sale con código 1 si quedan balances desviados (INV-07), así que se puede encadenar en un pipeline. Las incoherencias de categorización (INV-08) se reportan, pero `--fix` no las corrige: reasignar una categoría es una decisión humana.

---

## Tareas asíncronas (E2-M7)

| Criterio | Test o evidencia | Estado |
|---|---|---|
| **A-33** reporte mensual asíncrono | `tests/contract/test_reports.py`; `as/api/test_reports.py`, `as/test_tasks.py`, `as/test_report_csv.py` | ✅ |
| **A-34** avisos una sola vez y vencimiento | `ss/test_notifications.py` (reloj controlado), `ss/test_tasks.py` | ✅ |
| **A-35** resiliencia de las tareas | `tests/contract/runs/2026-10-22-tareas-asincronas.txt` (secciones 3 y 4) | ✅ |
| **A-36** tareas sin lógica y convención de Compose | `TestTareasSinLogica` en `as/test_architecture.py` y `ss/test_architecture.py`; `tests/services/test_compose_celery.py` | ✅ |
| Contacto interno de identity bloqueado desde fuera | `identity/tests/test_internal_contact.py`; `tests/contract/test_routing.py::TestInternal` | ✅ |

```bash
docker compose stop analytics-celery     # el reporte queda PENDING
docker compose start analytics-celery    # y se completa
docker compose logs subscription-worker | grep -A12 "\[correo\]"
```

---

## Frontend (E2-M8b)

| Requisito | Test | Estado |
|---|---|---|
| Checkout: el cuerpo solo lleva `{plan}`, sin consola ni almacenamiento, campos sin `name` y `autocomplete="off"` | `core/tests/test_frontend.py::TestCheckout` | ✅ |
| 403 `premium_required` → Planes; 503 → "intenta de nuevo"; avatar → Ajustes; cuatro secciones | `core/tests/test_frontend.py::TestNavegacionPremium` | ✅ |
| Búsqueda y tipo en Movimientos; comparaciones y saldo por moneda en el dashboard; sin barras en cero | `core/tests/test_frontend.py::TestDashboardYMovimientos` | ✅ |
| Monto en cero sin signo | `frontend/tests/js/format.test.mjs` (vía `core/tests/test_frontend_js.py`) | ✅ |
| Estáticos con hash y `import` reescritos | `core/tests/test_static_files.py` | ✅ |

Por el Gateway, con el stack arriba:

```bash
H=$(curl -s http://localhost/dashboard/ | grep -o '/static/finty/js/pages/dashboard[^"]*')
curl -sI "http://localhost$H" | grep -i cache-control          # public, max-age=31536000, immutable
curl -sI http://localhost/static/finty/js/pages/dashboard.js | grep -i cache-control   # no-cache
```

---

## Comprobaciones rápidas con `grep`

Complementarias, **no autoritativas**: el criterio es el AST.

```bash
grep -rn "django" core/domain/ services/finance-service/domain/           # vacío
grep -rnE "^from (flask|sqlalchemy|models|infra)" services/finance-service/domain/   # vacío
grep -rnE "AICategorizer|RuleBasedCategorizer|MockCategorizer|CategorizerFactory" services/finance-service/services.py   # vacío
grep -rnE "^[[:space:]]*(try:|except[[:space:]])" identity/api/views.py services/finance-service/api/routes.py   # vacío
```

El último **debe ir anclado a inicio de sentencia**. Sin anclar, `serializer.is_valid(raise_exception=True)` da un falso positivo: `raise_exception` contiene la subcadena `except`. Es el motivo por el que el AST sustituyó a los `grep` como criterio (A-15).

---

*Finty · Guía de verificación · Entrega 2 (E2-M7)*
