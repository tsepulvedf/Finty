# Finty — Guía de verificación

Mapea cada criterio del **Anexo A** de [`ARCHITECTURE.md`](ARCHITECTURE.md) al test que lo demuestra y al comando que lo aísla.

**Desde E2-M3a** el contexto `finance` ya no vive en el monolito: lo sirve `services/finance-service/` (ADR-08). **Desde E2-M3b** la categorización (los categorizadores y `CategorizerFactory`) vive en `services/categorization-service/`, y `finance-service` la consume por HTTP con un respaldo local. Por eso los criterios de la Entrega 1 que hablaban de cuentas, transacciones, categorización y balance se verifican ahora en la suite de ese servicio. En el monolito quedan `core` e `identity`. El criterio autoritativo de capas sigue siendo el análisis del AST (A-15 en el monolito, A-16 en el servicio); un `grep` es solo una comprobación rápida.

Estado a la fecha de este documento (2026-10-20):

| Suite | Tests | Cómo se corre |
|---|---|---|
| Monolito (`core`, `identity`) | **175**, todos en verde | `pytest` en la raíz |
| `finance-service` | **731**, todos en verde | `pytest` en `services/finance-service/` (ver README) |
| `categorization-service` | **853**, todos en verde | `pytest` en `services/categorization-service/`, sin base de datos |
| `analytics-service` | **136**, todos en verde | `pytest` en `services/analytics-service/` con `ANALYTICS_TEST_DATABASE_URL` (ver README) |
| Contrato de caja negra (A-20) | **125**, más 5 opcionales (2 de throttling, A-13 y dos de A-22) | `CONTRACT_BASE_URL=http://localhost pytest` en `tests/contract/` |
| Contratos estáticos entre servicios | **8** | `pytest` en `tests/services/` |

En las tablas, `fs/` abrevia `services/finance-service/tests/`, `cs/` abrevia `services/categorization-service/tests/` y `as/` abrevia `services/analytics-service/tests/`.

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
| **A-16** | `fs/test_architecture.py::TestPurezaDelDominio`, `as/test_architecture.py::TestPurezaDelDominio` | ✅ |
| **A-17** | `docker compose config`: solo `nginx` declara `ports` (verificado en E2-M1a y E2-M2a) | ✅ |
| **A-18** | `tests/contract/test_auth.py::TestA18XUserIdDelCliente` | ✅ |
| **A-19** | `tests/contract/test_isolation.py` | ✅ |
| **A-20** | `tests/contract/` — mismo resultado antes y después de conmutar, y tras retirar `finance` del monolito (`tests/contract/runs/`) | ✅ |
| **A-21** | `services/finance-service/.env.docker` y `services/analytics-service/.env.docker` solo contienen `DATABASE_URL` (cada uno, la de su base) y `TIME_ZONE`; `categorization-service` no tiene base ni secretos | ✅ |
| **A-22** | Categorización: `tests/contract/test_categorization.py` con `CONTRACT_CATEGORIZATION_DOWN=1` y el servicio detenido (201 con `rule`); `fs/test_categorization_client.py::TestRespaldoA22` (timeout, conexión rechazada, 5xx, cuerpo inválido) | ✅ (categorización) |
| **A-24** | `curl http://<ip>/api/v1/health/` — pendiente del despliegue en EC2 | ⏳ |
| **A-25** | `as/test_projection.py` (`TestProyector`, `TestConsumidor`: duplicados, fuera de orden, lápida, `XACK` solo tras el commit) y `tests/services/test_event_contract.py` | ✅ |
| **A-26** | `tests/contract/test_analytics.py::TestResumenPublico::test_k_anonimato`, `as/api/test_api.py::TestResumenPublico` | ✅ |
| **A-27** | `tests/contract/test_analytics.py::TestDePuntaAPunta` (sondeo con límite de 15 s) | ✅ |

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

INV-05 e INV-06 son de `subscription-service` (E2-M6).

---

## Auditoría de invariantes en el stack

```bash
docker compose exec finance-service flask verify-invariants          # todas las cuentas
docker compose exec finance-service flask verify-invariants --fix    # recalcula balances desviados
docker compose exec finance-service flask verify-invariants --user <user_id>
```

Sale con código 1 si quedan balances desviados (INV-07), así que se puede encadenar en un pipeline. Las incoherencias de categorización (INV-08) se reportan, pero `--fix` no las corrige: reasignar una categoría es una decisión humana.

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

*Finty · Guía de verificación · Entrega 2 (E2-M4b)*
