# Validación del Taller 02

**Fecha de revisión de evidencias:** 30 de septiembre de 2026.
**Fuente del código:** commit base `d19eb9d` de `tsepulvedf/Finty` y parche del taller.
**Rama reportada:** `feat/taller02-strangler`.
**Evidencia:** salidas aportadas por el equipo, conservadas en
[`evidencias/taller02-consola.txt`](evidencias/taller02-consola.txt).

## 1. Validación en el equipo

Las comprobaciones pendientes durante la preparación ya fueron ejecutadas en
el equipo local. Estos resultados se verifican en las salidas aportadas; no
son resultados esperados ni ejecuciones del entorno de preparación.

| Comprobación | Resultado observado |
|---|---|
| Aplicación del parche | Sin errores; rama feature creada |
| Generación de `.env.docker` y `config --quiet` | Configuración creada y validada sin errores |
| Build de Django y Flask | Ambas imágenes construidas correctamente |
| `up --build --wait --wait-timeout 300` | Arranque completado correctamente |
| `docker compose ... ps` | PostgreSQL, Django y Flask healthy; Nginx en ejecución |
| Puerto publicado | Solo Nginx: `127.0.0.1:8080->80/tcp`; los otros puertos son internos |
| `nginx -t` | `syntax is ok` y `test is successful` |
| Smoke normal | OK: autenticación, rutas v1/v2, clasificación y balance remoto |
| Smoke tras detener Flask | OK: respaldo local; v2 devuelve 503 según los asserts del script |
| Restauración de Flask | `start flask_categorization` completado correctamente |
| Suite completa con PostgreSQL | **1582 passed, 1 warning in 151.68s (0:02:31)** |

Los scripts verifican mediante asserts el rechazo sin token, sugerencia
servida por Flask, error 400 en el caso normal, registro en Django y balance
`100000 - 25000 = 75000`. En la caída verifican 503 en v2 y registro exitoso
en v1 con confianza 0.20. El éxito de ambos scripts acredita esas
comprobaciones en las ejecuciones aportadas.

Cada demostración elimina la cuenta y el movimiento al finalizar con éxito;
queda un usuario de prueba sin datos financieros.

## 2. Comandos ejecutados

Desde la raíz del proyecto, con Docker activo:

```bash
python scripts/setup_taller_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up --build --wait --wait-timeout 300
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker exec nginx nginx -t
python scripts/smoke_strangler.py
docker compose --env-file .env.docker stop flask_categorization
python scripts/smoke_strangler.py --fallback
docker compose --env-file .env.docker start flask_categorization
docker compose --env-file .env.docker run --rm django_web sh -c "pip install --user -r requirements-test.txt && python -m pytest -q"
```

El equipo usa Git Bash en Windows y Python local 3.10.6 para los scripts.
Los contenedores usan Python 3.12; `tzdata` ya estaba instalado en el Python
local según la salida de pip.

Se verificó en la rama publicada que `HealthView` incluye
`throttle_classes = []` para que las sondas no consuman la cuota anónima.
El ajuste está incorporado al código de la entrega.

## 3. Advertencias observadas

La suite completa no presenta fallos ni errores. Tiene un
`PytestCacheWarning`: el usuario del contenedor no puede crear la caché de
pytest bajo `/app`. Afecta a la caché entre ejecuciones, no al resultado de
las 1582 pruebas aprobadas.

Para futuras ejecuciones puede usarse una ubicación escribible. No es
necesario repetir ahora la suite aprobada solo por esta advertencia:

```bash
docker compose --env-file .env.docker run --rm django_web sh -c "pip install --user -r requirements-test.txt && python -m pytest -q -o cache_dir=/tmp/finty-pytest-cache"
```

Pip avisa también que el ejecutable `flask` no está en PATH. Las pruebas se
ejecutan con `python -m pytest` e importan Flask como módulo, por lo que ese
aviso no impidió la validación. Los avisos de una nueva versión de pip no son
errores.

## 4. Comprobaciones previas de preparación

- **1090 passed, 492 deselected** en la selección sin PostgreSQL.
- **39 passed** específicos de migración, incluidos en las 1090.
- `manage.py check` sin incidencias.
- Flask operativo bloqueando imports de Django y DRF.
- Llamada HTTP real adaptador-Flask, AST, YAML y `git diff --check` correctos.

Los 492 casos antes excluidos quedan cubiertos por la suite completa de
1582 pruebas aportada. Las cifras no se suman: corresponden a la misma
suite con distintas selecciones.

## 5. Publicación y revisión del equipo

Se verificó la rama publicada `feat/taller02-strangler`, con los cuatro commits
del taller y los logs en `docs/evidencias/taller02-consola.txt`. El commit de
documentación revisado es `6f30b1f`.

- Código: https://github.com/tsepulvedf/Finty/tree/feat/taller02-strangler
- Pull Request: https://github.com/tsepulvedf/Finty/pull/1
- La Wiki está publicada; la aclaración de alcance dirige a la rama del taller.

El PR #1 está abierto y sin merge. Ese estado es intencional: el Taller 02 se
entrega en su rama y `main` conserva la versión anterior. El merge no es un
paso pendiente de esta entrega.

Los cuatro commits revisados están atribuidos a Tomás. Falta acreditar una
revisión o aporte real de otro integrante, con su identidad y evidencia en el
PR o historial. La existencia del PR, por sí sola, no demuestra colaboración.

Antes del envío, publicar el ajuste documental de cierre y confirmar que la
Wiki muestra las 1582 pruebas aprobadas y usa el título exacto del taller.

No hay benchmark de rendimiento ni acreditación de bonificación temporal.
Los 151.68 segundos son tiempo de pruebas, no latencia del sistema.
