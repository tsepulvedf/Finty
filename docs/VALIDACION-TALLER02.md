# Validación del Taller 02

**Fecha de preparación:** 30 de septiembre de 2026.
**Fuente:** commit `d19eb9d` de `tsepulvedf/Finty`.
**Runtime usado:** Python 3.12; dependencias declaradas en los requirements.

## Resultados ejecutados

| Comprobación | Resultado real |
|---|---|
| Suite seleccionada sin PostgreSQL | **1090 passed, 492 deselected**, 1.26 s |
| Pruebas específicas de migración | **39 passed**, 0.19 s; son parte de las 1090, no adicionales |
| `python manage.py check` | System check identified no issues (0 silenced) |
| Importar y ejecutar Flask bloqueando Django y DRF | HTTP 200; Alimentación, confianza 0.75, fuente rule; no se importaron dichos frameworks |
| Llamada HTTP real adaptador → Flask | Incluida en las pruebas; confianza 0.75 demuestra camino remoto en vez de respaldo |
| Parseo AST de archivos Python | Correcto |
| Parseo YAML + revisión estructural Compose | Cuatro servicios, solo Nginx publica puerto, Flask sin variables DB |
| `git diff --check` | Correcto |

Comandos principales ejecutados desde la raíz, con variables de prueba:

```bash
python -m pytest -m 'not django_db' -k 'not TestAdminDeSoloLectura' -q
python -m pytest services/categorization/tests finance/tests/test_remote_categorizer.py identity/tests/test_auth_verify.py -q
python manage.py check
```

La primera selección excluye las pruebas con marca `django_db` y los 19 casos
de `TestAdminDeSoloLectura`, que piden `db` sin estar marcados. Un intento previo
solo con `-m 'not django_db'` produjo 19 errores de conexión porque PostgreSQL
no está instalado/levantado. No fue una suite completa aprobada. Los 492 casos
excluidos siguen pendientes de ejecutar con PostgreSQL.

## Comprobaciones pendientes en Docker

Este entorno no tiene ejecutables Docker, Nginx ni servidor PostgreSQL. Por
tanto, el parseo YAML **no equivale** a `docker compose config`, el análisis del
archivo proxy **no equivale** a `nginx -t` y la prueba HTTP directa a Flask
**no demuestra** todavía el ruteo real por Nginx.

Ejecutar en un equipo con Docker y registrar fecha y resultados reales:

```bash
python scripts/setup_taller_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker exec nginx nginx -t
python scripts/smoke_strangler.py
docker compose --env-file .env.docker stop flask_categorization
python scripts/smoke_strangler.py --fallback
docker compose --env-file .env.docker start flask_categorization
docker compose --env-file .env.docker run --rm django_web sh -c 'pip install --user -r requirements-test.txt && python -m pytest -q'
```

Guardar la salida o capturas como evidencia del arranque simultáneo, las dos
rutas y el respaldo. No reemplazar "pendiente" por "aprobado" sin ejecutarlo.

## Publicación y trabajo colaborativo

Los archivos y el parche están preparados localmente. No se realizó push,
merge, publicación de Wiki ni commits atribuidos a integrantes. Completar el
flujo descrito en `docs/TALLER02.md` con las identidades reales del equipo.
No hay datos medidos de mejora de rendimiento ni acreditación de bonificación
temporal. El tiempo de pytest no es un benchmark del sistema en producción.
