#!/bin/sh
# Crea una base logica por servicio (ADR-10, D-E2-04). Idempotente: crea las que
# falten y deja intactas las que ya existen.
#
# Se ejecuta por dos caminos (ADR-04.1):
#   1. La imagen de PostgreSQL lo corre la primera vez que inicializa un volumen
#      vacio, por el socket local.
#   2. El servicio `db-init` de Compose lo corre en cada `docker compose up`, por
#      TCP contra `db`. Es lo que crea las bases nuevas en un volumen que ya
#      existe, como el de la EC2, sin pasos manuales.
#
# Como agregar la base de un servicio nuevo:
#   1. Agrega su nombre a FINTY_DATABASES, abajo.
#   2. Haz que el paso de migraciones del servicio dependa de `db-init` en
#      docker-compose.yml.
#   3. Pasa al servicio solo la URL de su propia base (A-21).
set -e

FINTY_DATABASES="finty_identity finty_finance finty_analytics finty_recommendation"

# Por TCP (camino 2) psql necesita la contrasena; por el socket local no.
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
export PGPASSWORD

for db in $FINTY_DATABASES; do
    echo "finty: asegurando la base '$db'"
    # \gexec ejecuta el CREATE DATABASE solo si el SELECT devuelve una fila,
    # es decir, solo si la base todavia no existe.
    sql="SELECT 'CREATE DATABASE $db OWNER \"$POSTGRES_USER\"'"
    sql="$sql WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db')"
    printf '%s \\gexec\n' "$sql" | psql -v ON_ERROR_STOP=1 \
        --username "$POSTGRES_USER" --dbname postgres
done
