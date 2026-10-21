# Finty — Guía de verificación

Mapea cada criterio del **Anexo A** de [`ARCHITECTURE.md`](ARCHITECTURE.md) al test que lo demuestra y al comando que lo aísla.

**Desde E2-M3a** el contexto `finance` ya no vive en el monolito: lo sirve `services/finance-service/` (ADR-08). Por eso los criterios de la Entrega 1 que hablaban de cuentas, transacciones, categorización y balance se verifican ahora en la suite de ese servicio. En el monolito quedan `core` e `identity`. El criterio autoritativo de capas sigue siendo el análisis del AST (A-15 en el monolito, A-16 en el servicio); un `grep` es solo una comprobación rápida.

Estado a la fecha de este documento (2026-10-20):

| Suite | Tests | Cómo se corre |
|---|---|---|
| Monolito (`core`, `identity`) | **175**, todos en verde | `pytest` en la raíz |
| `finance-service` | **1324**, todos en verde | `pytest` en `services/finance-service/` (ver README) |
| Contrato de caja negra (A-20) | **111** más 2 de throttling, opcionales | `CONTRACT_BASE_URL=http://localhost pytest` en `tests/contract/` |

En las tablas, `fs/` abrevia `services/finance-service/tests/`.

---

## Criterios de la Entrega 1

| Criterio | Qué exige | Test | Estado |
|---|---|---|---|
| **A-01** | `domain/` no depende de Django | `core/tests/test_architecture.py::TestPurezaDelDominio` para `core/domain/`; `fs/test_architecture.py::TestPurezaDelDominio` (A-16) para el dominio de finanzas | ✅ |
| **A-02** | Vistas sin lógica de negocio | `core/tests/test_architecture.py::TestVistasSinLogica` (identity); `fs/test_architecture.py::TestBlueprintsSinLogica` | ✅ |
| **A-03** | Modelos sin lógica de negocio | `core/tests/test_architecture.py::TestModelosAnemicos` (`User`, `UserProfile`); `fs/test_architecture.py::TestModelosAnemicos` (`Account`, `Transaction`, `Category`) | ✅ |
| **A-04** | Factory conmutable por entorno | `fs/categorization/test_categorizer_factory.py` — despacho por `CATEGORIZER_PROVIDER`, insensible a mayúsculas, y `ConfigurationError` ante un valor desconocido | ✅ |
| **A-05** | Builder valida antes de construir | `fs/domain/test_builders.py::TestInvariantes` (monto cero, negativo, moneda distinta, fecha futura, cuenta archivada) y `TestCamposObligatorios` | ✅ |
| **A-06** | Balance consistente (INV-07 según C-17) | `fs/test_opening_balance.py::TestInv07ConAperturaDistintaDeCero` y `fs/test_services.py::TestRegistroYBalance::test_inv_07_tras_varias_transacciones_mezcladas` | ✅ |
| **A-07** | Ownership aplicado | `fs/test_services.py::TestPropiedad`, `fs/api/test_contract.py::TestAislamientoEntreUsuarios` y, a través del Gateway, `tests/contract/test_isolation.py` (A-19) | ✅ |
| **A-08** | LSP en categorizadores | `fs/test_service_lsp.py::TestLSPEnElServicio` — la misma suite sobre `RuleBasedCategorizer`, `MockCategorizer` y `AICategorizer(client=None)`; `fs/categorization/test_categorizer_lsp.py` con entradas hostiles | ✅ |
| **A-09** | Builder no conoce el ORM | `fs/test_architecture.py::TestPurezaDelDominio` — `domain/` no importa `models`, `infra` ni `sqlalchemy` | ✅ |
| **A-10** | Servicio no conoce implementaciones concretas | `fs/test_architecture.py::TestServiciosSinImplementacionesConcretas` | ✅ |
| **A-11** | Escritura bajo bloqueo | `fs/test_services.py::TestBloqueo` — captura el SQL real y exige `FOR UPDATE` al registrar, eliminar y recalcular | ✅ |
| **A-12** | Categoría emitida siempre existe | `fs/persistence/test_catalog_contract.py` — el catálogo que siembra Alembic coincide con lo que pueden emitir las reglas | ✅ |
| **A-13** | El Factory es observable desde fuera | `fs/api/test_contract.py::TestFactoryMismoRequestDistintoResultado` y `fs/test_categorization_provenance.py::TestProcedenciaPorHttp::test_el_mismo_cuerpo_produce_procedencias_distintas` | ✅ |
| **A-14** | La procedencia registrada es veraz | `fs/test_categorization_provenance.py` — cada categorizador declara la suya, la degradación reporta la del respaldo, y los cuatro valores se persisten y se recuperan por HTTP | ✅ |
| **A-15** | Reglas de capas verificadas en la suite | `core/tests/test_architecture.py` (monolito) y `fs/test_architecture.py` (servicio), ambos por AST | ✅ |

## Criterios de la Entrega 2 verificados hasta hoy

| Criterio | Test | Estado |
|---|---|---|
| **A-16** | `fs/test_architecture.py::TestPurezaDelDominio` | ✅ |
| **A-17** | `docker compose config`: solo `nginx` declara `ports` (verificado en E2-M1a y E2-M2a) | ✅ |
| **A-18** | `tests/contract/test_auth.py::TestA18XUserIdDelCliente` | ✅ |
| **A-19** | `tests/contract/test_isolation.py` | ✅ |
| **A-20** | `tests/contract/` — mismo resultado antes y después de conmutar, y tras retirar `finance` del monolito (`tests/contract/runs/`) | ✅ |
| **A-21** | `services/finance-service/.env.docker` solo contiene `DATABASE_URL`, `CATEGORIZER_PROVIDER` y `TIME_ZONE` | ✅ |
| **A-24** | `curl http://<ip>/api/v1/health/` — pendiente del despliegue en EC2 | ⏳ |

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

*Finty · Guía de verificación · Entrega 2 (E2-M3a)*
