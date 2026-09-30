# Taller 02 de Finty: guía de ejecución y entrega

La solución extrae **la sugerencia automática de categorías**, mantiene el
registro financiero en Django y agrega Flask, Nginx y PostgreSQL con Compose.
Fue preparada contra el commit `d19eb9d` del repositorio original.

## 1. Aplicar los cambios a tu repositorio

El paquete incluye una copia completa para consultar y ejecutar, y un parche
para incorporarlo a tu clon manteniendo su historial. El parche debe estar
fuera del clon; ajustar su ruta según donde descomprimiste el ZIP.

```bash
git clone https://github.com/tsepulvedf/Finty.git
cd Finty
git switch -c feat/taller02-strangler
git apply --check ../taller02.patch
git apply ../taller02.patch
```

Si ya tienes un clon, usa ese clon con tus cambios previos guardados y comienza
desde `git switch`. Si `git apply --check` falla porque el repositorio cambió,
compara los archivos con la copia del ZIP y adapta el parche. No restablezcas
la rama ni sobrescribas trabajo del equipo para forzarlo.

## 2. Levantar la arquitectura híbrida

Necesitas Git, Python 3.11+ y Docker con Compose v2. Las imágenes usan Python
3.12. Desde la raíz del proyecto:

```bash
python scripts/setup_taller_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker exec nginx nginx -t
```

El generador crea `.env.docker` con claves propias y no sobrescribe un archivo
existente. No se sube al repositorio. Compose usa `--env-file` para interpolar
variables; no supone que `.env.docker` se cargue automáticamente en Django.
Las variables de conexión se inyectan en el contenedor de Django.

Abrir `http://127.0.0.1:8080/`. La API antigua permanece bajo `/api/v1/` y la
nueva sugerencia se encuentra en `/api/v2/categorization/`. Si cambias
`PUBLIC_PORT`, indica el nuevo origen con `--base-url` al script de demostración.

Migraciones y `collectstatic` se ejecutan al iniciar Django. PostgreSQL conserva
datos en volumen y Flask no recibe configuración de base de datos.

Para examinar problemas:

```bash
docker compose --env-file .env.docker logs --tail=100 django_web flask_categorization nginx
```

## 3. Demostración de extremo a extremo

```bash
python scripts/smoke_strangler.py
```

Debe terminar con `OK`. Comprueba salud v1, rechazo v2 sin token, sugerencia
servida por Flask (cabecera `X-Finty-Service`), un error 400 y registro en Django
con saldo final de 75000 desde 100000. Se elimina la cuenta y el movimiento al
terminar; queda un usuario de demostración. Si falla a mitad, revisar los datos
de prueba antes de repetir.

Demostrar la caída y el respaldo:

```bash
docker compose --env-file .env.docker stop flask_categorization
python scripts/smoke_strangler.py --fallback
docker compose --env-file .env.docker start flask_categorization
```

La ruta v2 debe responder 503 y v1 seguir registrando con confianza 0.20.
Esta es una prueba ejecutable, **no un resultado ya obtenido en Docker**.

## 4. Ejecutar pruebas

La suite extendida usa Flask y Gunicorn además de los paquetes originales.
Las versiones se declaran en `services/categorization/requirements.txt`,
`requirements-container.txt` y `requirements-test.txt`. El adaptador HTTP de
Django usa `urllib` de la biblioteca estándar, sin añadir Requests.

Suite completa con PostgreSQL dentro de Compose, usando un contenedor
temporal y dependencias de prueba instaladas solo para ese comando:

```bash
docker compose --env-file .env.docker run --rm django_web sh -c 'pip install --user -r requirements-test.txt && python -m pytest -q'
```

La imagen oficial PostgreSQL configura el usuario inicial como superusuario,
por lo que puede crear la base de pruebas. Esto sirve para el laboratorio;
para otro servidor, el usuario de pruebas necesita `CREATEDB`.

Pruebas locales sin PostgreSQL:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements-test.txt
```

Define variables de entorno de prueba `SECRET_KEY`, `DEBUG=False`,
`ALLOWED_HOSTS=localhost,127.0.0.1`, `DB_NAME=finty`, `DB_USER=finty`,
`DB_PASSWORD=test`, `DB_HOST=localhost` y `DB_PORT=5432` y ejecuta:

```bash
python -m pytest -m 'not django_db' -k 'not TestAdminDeSoloLectura' -q
python manage.py check
```

Ejemplo para Bash, en una sola línea:

```bash
SECRET_KEY=test-only DEBUG=False ALLOWED_HOSTS=localhost,127.0.0.1 DB_NAME=finty DB_USER=finty DB_PASSWORD=test DB_HOST=localhost DB_PORT=5432 python -m pytest -m 'not django_db' -k 'not TestAdminDeSoloLectura' -q
```

Se excluye explícitamente `TestAdminDeSoloLectura` porque usa la fixture `db`
aunque no lleva la marca `django_db`. Esa exclusión **no aplica a la suite
completa con PostgreSQL**. Resultados reales: `docs/VALIDACION-TALLER02.md`.

## 5. Publicar la Wiki

En GitHub, abrir **Wiki → New page**. Usar exactamente el título:

**Migración a Microservicios (Strangler Pattern)**

Copiar todo el contenido de
`docs/wiki/Migracion-a-Microservicios-Strangler-Pattern.md` y guardar. El archivo
en `docs/` es una copia versionada, pero **no sustituye la publicación en la
Wiki**. Si el repositorio no muestra Wiki, habilitarla en sus ajustes, si el
plan y los permisos lo permiten.

Si la Wiki ya está inicializada, también puedes clonar su repositorio separado:

```bash
git clone https://github.com/tsepulvedf/Finty.wiki.git ../Finty.wiki
```

Copiar el archivo Markdown allí y hacer un commit/push desde ese clon. No se
ha actualizado la Wiki remota desde este entorno.

## 6. Git Flow y participación real

Revisar el diff, ejecutar las pruebas anteriores y organizar commits por unidad:

```bash
git add services ':!services/categorization/tests' finance/infra/remote_categorizer.py finance/infra/factories.py config/settings.py identity/api/auth_verify.py identity/api/urls.py
git commit -m "feat(finance): extraer clasificacion automatica a servicio Flask"
git add Dockerfile docker-compose.yml infra .dockerignore .gitignore .env.docker.example requirements-container.txt scripts/setup_taller_env.py
git commit -m "chore(infra): orquestar Django Flask y PostgreSQL con Nginx"
git add services/categorization/tests finance/tests identity/tests core/tests/test_architecture.py scripts/smoke_strangler.py requirements-test.txt
git commit -m "test(strangler): verificar contratos autenticacion y respaldo remoto"
git add docs README.md
git commit -m "docs(arquitectura): documentar migracion mediante patron estrangulador"
git push -u origin feat/taller02-strangler
```

El pathspec `:!services/categorization/tests` deja los tests para el commit de
pruebas. No importa la cantidad exacta de commits, sino que sean semánticos,
ordenados y trazables.

Cada integrante debe realizar trabajo real (por ejemplo, revisión de matriz,
prueba de infraestructura o mejora de tests), comprometerlo con su propia
identidad y participar en la revisión del PR. **No se inventan autores ni
contribuciones.** Crear un Pull Request hacia la rama principal, revisar y
fusionar de acuerdo con el flujo habitual del equipo. La entrega debe permitir
al profesor localizar el código; dejar el PR abierto sin indicarlo puede hacer
que revise una rama sin cambios.

## 7. Lista de entrega y sustentación

- Matriz de cinco módulos y elección de clasificación automática en Wiki.
- Flask con JSON, errores 400/500 y sin acceso al ORM.
- Dockerfile Flask y Compose con Django, Flask, PostgreSQL y Nginx.
- Rutas v1/v2 verificadas en el proxy real.
- Wiki publicada con título exacto, diagrama y efecto esperado.
- Commits semánticos y contribuciones reales visibles.
- Capturar `docker compose ps`, `nginx -t`, smoke normal y de caída, y tests
  completos; añadir resultados reales a `docs/VALIDACION-TALLER02.md`.
- Entregar **https://github.com/tsepulvedf/Finty** con la rama final publicada y
  cambios visibles; incluir el enlace de Wiki si el formulario lo permite.

Para sustentar: explicar por qué no se separó el balance (consistencia del
agregado), por qué Flask no tiene base (operación pura), cómo la factory conserva
v1, cómo Nginx conserva la URL y cómo opera el respaldo. Reconocer que no hay
benchmark ni evidencia de inferencia pesada actual.

La bonificación +0.5 depende del push y envío del enlace durante la sesión.
El paquete no acredita ese requisito temporal.
