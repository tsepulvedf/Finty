# Finty — Guía de verificación

Mapea cada criterio del **Anexo A** de [`ARCHITECTURE.md`](ARCHITECTURE.md) al test que lo demuestra y al comando que lo aísla.

Los criterios están redactados en el Anexo A como comprobaciones con `grep`. Desde M7 el criterio autoritativo es **A-15**: `core/tests/test_architecture.py` recorre el AST de cada módulo. Un `grep` sigue sirviendo como comprobación rápida, pero no distingue una sentencia de una subcadena — el caso concreto que lo motivó está documentado en A-02.

Estado a la fecha de este documento: **1432 tests, todos en verde**.

---

## Criterios de aceptación

| Criterio | Qué exige | Test o comando | Estado |
|---|---|---|---|
| **A-01** | `domain/` no depende de Django | `core/tests/test_architecture.py::TestPurezaDelDominio::test_ningun_modulo_de_dominio_importa_hacia_afuera` — parametrizado sobre cada `.py` de `core/domain/` y `finance/domain/`; verifica nodos `ast.Import`/`ast.ImportFrom` contra `django`, `rest_framework`, `finance.models`, `finance.infra`, `identity` y `config` | ✅ Cubierto |
| **A-02** | Vistas sin lógica de negocio | `TestVistasSinLogica` — `test_cero_bloques_try` (cero nodos `ast.Try`), `test_cero_aritmetica` (cero `ast.BinOp` aritméticos), `test_no_importa_piezas_del_dominio`, `test_todo_acceso_a_datos_pasa_por_un_servicio` | ✅ Cubierto |
| **A-03** | Modelos sin lógica de negocio | `TestModelosAnemicos` — `test_solo_se_permiten_str_y_meta`, `test_no_sobreescriben_metodos_del_orm`, `test_no_declaran_propiedades_calculadas`, `test_no_hay_receptores_de_senales`. Cubre `Account`, `Transaction`, `Category`, `User` y `UserProfile` | ✅ Cubierto |
| **A-04** | Factory conmutable por entorno | `finance/tests/test_categorizer_factory.py` — despacho por `override_settings(CATEGORIZER_PROVIDER=…)`, insensible a mayúsculas, y `ImproperlyConfigured` ante un valor desconocido | ✅ Cubierto |
| **A-05** | Builder valida antes de construir | `finance/tests/test_builders.py::TestInvariantes::test_monto_cero` y el resto de la clase: monto negativo, moneda distinta, fecha futura, cuenta archivada, campos obligatorios | ✅ Cubierto |
| **A-06** | Balance consistente (INV-07 según C-17) | `finance/tests/test_services.py::TestRegistroYBalance::test_inv_07_tras_varias_transacciones_mezcladas` y `finance/tests/test_opening_balance.py::TestInv07ConAperturaDistintaDeCero` — compara `account.balance` con `opening_balance + Σ movimientos` | ✅ Cubierto |
| **A-07** | Ownership aplicado | `finance/tests/test_services.py::TestPropiedad` (13 tests) y `finance/tests/test_api.py::TestAislamientoEntreUsuarios` | ✅ Cubierto |
| **A-08** | LSP en categorizadores | `finance/tests/test_services.py::TestLSPEnElServicio` — la misma suite parametrizada sobre `RuleBasedCategorizer`, `MockCategorizer` y `AICategorizer(client=None)`. Complementado por `finance/tests/test_categorizer_lsp.py` con entradas hostiles | ✅ Cubierto |
| **A-09** | Builder no conoce el ORM | `TestPurezaDelDominio::test_los_builders_solo_conocen_la_stdlib_y_el_dominio` | ✅ Cubierto |
| **A-10** | Servicio no conoce implementaciones concretas | `TestServiciosSinImplementacionesConcretas` — `test_no_importan_categorizadores_ni_la_fabrica` y `test_finance_services_no_importa_nada_de_infra` | ✅ Cubierto |
| **A-11** | Escritura bajo bloqueo | `finance/tests/test_services.py::TestBloqueo::test_el_sql_contiene_for_update` — captura el SQL real con `CaptureQueriesContext`. Además `TestBloqueoFueraDeTransaccion` verifica que `get_locked_account` exige un bloque atómico | ✅ Cubierto |
| **A-12** | Categoría emitida siempre existe | `finance/tests/test_categorizer_catalog_contract.py` — recolecta todos los nombres que el mapa de reglas puede emitir y verifica que cada uno existe en la tabla `Category` con el `applies_to` correcto | ✅ Cubierto |
| **A-13** | El Factory es observable desde fuera | `finance/tests/test_api.py::TestFactoryMismoRequestDistintoResultado` y `finance/tests/test_categorization_provenance.py::TestProcedenciaPorHttp::test_el_mismo_cuerpo_produce_procedencias_distintas` | ✅ Cubierto |
| **A-14** | La procedencia registrada es veraz | `finance/tests/test_categorization_provenance.py` (19 tests) — cada categorizador declara la suya, la degradación reporta la del respaldo, y los cuatro valores se persisten y recuperan | ✅ Cubierto |
| **A-15** | Reglas de capas verificadas en la suite | `core/tests/test_architecture.py` (46 tests) — pureza del dominio, vistas sin lógica, modelos anémicos, servicios sin concreciones, serializers sin acceso a datos, migraciones sin código vivo | ✅ Cubierto |

Ningún criterio queda sin test.

---

## Comandos por criterio

```bash
# A-01, A-02, A-03, A-09, A-10, A-15
pytest core/tests/test_architecture.py -v

# A-04
pytest finance/tests/test_categorizer_factory.py -v

# A-05
pytest finance/tests/test_builders.py -v

# A-06
pytest finance/tests/test_services.py::TestRegistroYBalance \
       finance/tests/test_opening_balance.py::TestInv07ConAperturaDistintaDeCero -v

# A-07
pytest finance/tests/test_services.py::TestPropiedad \
       finance/tests/test_api.py::TestAislamientoEntreUsuarios -v

# A-08
pytest finance/tests/test_services.py::TestLSPEnElServicio \
       finance/tests/test_categorizer_lsp.py -v

# A-11
pytest finance/tests/test_services.py::TestBloqueo \
       finance/tests/test_services.py::TestBloqueoFueraDeTransaccion -v

# A-12
pytest finance/tests/test_categorizer_catalog_contract.py -v

# A-13
pytest finance/tests/test_api.py::TestFactoryMismoRequestDistintoResultado -v

# A-14
pytest finance/tests/test_categorization_provenance.py -v
```

---

## Invariantes del catálogo (§7)

| Invariante | Dónde se hace cumplir | Test |
|---|---|---|
| INV-01 · Usuario autenticado | `DEFAULT_PERMISSION_CLASSES` de DRF | `finance/tests/test_api.py::TestAutenticacionRequerida` |
| INV-02 · Transacción con cuenta existente | `ForeignKey(null=False)` | `finance/tests/test_models.py::TestTransactionConstraints::test_la_cuenta_es_obligatoria` |
| INV-03 · Cuenta del usuario | `AccountService`, querysets filtrados | `finance/tests/test_services.py::TestPropiedad` |
| INV-04 · Monto distinto de cero | Dominio **y** `CheckConstraint` | `test_transaction_rules.py`, `test_models.py`, `test_builders.py` |
| INV-07 · Balance consistente | `BalanceCalculator` bajo bloqueo | `test_services.py::TestRegistroYBalance`, `test_opening_balance.py` |
| INV-08 · Categoría tras procesar | `TransactionBuilder.build()` | `test_builders.py::TestCategorizacion` |
| INV-09 · Tipo válido | Dominio **y** `CheckConstraint` | `test_domain_value_objects.py`, `test_models.py` |
| INV-10 · Email único | `unique=True` | `identity/tests/test_profile_service.py::TestRegistro` |
| INV-11 · Monedas coincidentes | `Money` y `TransactionRules` | `core/tests/test_money.py::TestMonedasDistintas` |
| INV-12 · Fecha no futura | `TransactionRules.ensure_date_not_future` | `test_transaction_rules.py::TestFechaNoFutura` |
| INV-13 · No borrar cuenta con transacciones | `on_delete=PROTECT` | `test_models.py::TestIntegridadReferencial` |
| INV-14 · Saldo negativo solo en crédito | Servicio bajo bloqueo, `AccountBuilder` y `CheckConstraint` sobre la apertura | `test_services.py::TestInvariantesEnElServicio`, `test_opening_balance.py::TestConstraintDeSigno` |

INV-05 e INV-06 quedan fuera del alcance de la Entrega 1 (§4.3).

---

## Verificación completa desde cero

Secuencia que ejecuta alguien externo sobre un clon limpio del repositorio.

```bash
# 1. Entorno
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux o macOS
pip install -r requirements.txt

# 2. Configuración
copy .env.example .env           # cp en Linux o macOS
# Editar .env: SECRET_KEY, DB_PASSWORD

# 3. Base de datos
psql -U postgres -c "CREATE ROLE finty LOGIN PASSWORD 'la-del-.env' CREATEDB;"
psql -U postgres -c "CREATE DATABASE finty OWNER finty ENCODING 'UTF8';"
#    El privilegio CREATEDB es necesario para que pytest cree la base de tests.

# 4. Esquema y datos iniciales
python manage.py check
python manage.py migrate
python manage.py makemigrations --check --dry-run   # no debe detectar cambios

# 5. Suite completa
pytest

# 6. Reglas de arquitectura aisladas
pytest core/tests/test_architecture.py -v

# 7. Cobertura
pytest --cov=. --cov-report=term-missing
```

### El dominio corre sin base de datos

La pureza del anillo interior es comprobable apuntando a una base inexistente: los tests de dominio y de arquitectura siguen pasando, y los que sí tocan la base fallan al conectar. Ese contraste es la prueba.

```bash
DB_HOST=192.0.2.1 DB_NAME=no_existe pytest \
    core/tests/test_money.py \
    core/tests/test_architecture.py \
    finance/tests/test_domain_value_objects.py \
    finance/tests/test_balance_calculator.py \
    finance/tests/test_transaction_rules.py \
    finance/tests/test_builders.py \
    finance/tests/test_categorizers.py \
    -p no:cacheprovider
```

### Conmutación del categorizador

```bash
CATEGORIZER_PROVIDER=RULE python manage.py shell -c \
  "from finance.infra.factories import CategorizerFactory; print(type(CategorizerFactory.get_categorizer()).__name__)"
# RuleBasedCategorizer

CATEGORIZER_PROVIDER=MOCK python manage.py shell -c \
  "from finance.infra.factories import CategorizerFactory; print(type(CategorizerFactory.get_categorizer()).__name__)"
# MockCategorizer

CATEGORIZER_PROVIDER=AI python manage.py shell -c \
  "from finance.infra.factories import CategorizerFactory; print(type(CategorizerFactory.get_categorizer()).__name__)"
# AICategorizer
```

Con el servidor levantado, el mismo `POST /api/v1/transactions/` devuelve `categorization_source` distinto según el proveedor: `rule`, `mock` o `rule` (este último porque `AICategorizer` sin cliente configurado degrada a su respaldo determinista, y la procedencia registrada es la del mecanismo que realmente clasificó — A-14).

---

## Comprobaciones rápidas con `grep`

Complementarias, **no autoritativas**. El criterio es A-15.

```bash
grep -rn "django" core/domain/ finance/domain/                       # vacío
grep -rnE "finance\.(models|infra)|identity" finance/domain/         # vacío
grep -rnE "AICategorizer|RuleBasedCategorizer|MockCategorizer|CategorizerFactory" finance/services.py   # vacío
grep -rn "objects\." finance/api/serializers.py                      # vacío
grep -rnE "def (save|clean|delete)\(" finance/models.py              # vacío
grep -rnE "^[[:space:]]*(try:|except[[:space:]])" */api/views.py     # vacío
```

El último **debe ir anclado a inicio de sentencia**. Sin anclar, `serializer.is_valid(raise_exception=True)` produce un falso positivo: la cadena `raise_exception` contiene la subcadena `except`. Es exactamente el motivo por el que A-15 sustituyó a los `grep` como criterio.

---

*Finty · Guía de verificación · Entrega 1*
