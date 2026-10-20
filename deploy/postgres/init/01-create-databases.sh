#!/bin/sh
# Crea una base logica por servicio (ADR-10, D-E2-04).
#
# La imagen de PostgreSQL ejecuta este script solo la primera vez, cuando el
# volumen de datos esta vacio. Es idempotente: crea las bases que falten y deja
# intactas las que ya existen, asi que tambien se puede correr a mano.
#
# Como agregar la base de un servicio nuevo (por ejemplo, en E2-M2):
#   1. Agrega su nombre a FINTY_DATABASES, abajo (finty_finance, finty_analytics,
#      finty_recommendation, finty_subscription).
#   2. Si el volumen ya existe, el script no se vuelve a ejecutar solo. Correlo:
#        docker compose exec db sh /docker-entrypoint-initdb.d/01-create-databases.sh
#   3. Pasa al servicio nuevo solo la URL de su propia base (A-21).
set -e

FINTY_DATABASES="finty_identity"

for db in $FINTY_DATABASES; do
    echo "finty: asegurando la base '$db'"
    # \gexec ejecuta el CREATE DATABASE solo si el SELECT devuelve una fila,
    # es decir, solo si la base todavia no existe.
    sql="SELECT 'CREATE DATABASE $db OWNER \"$POSTGRES_USER\"'"
    sql="$sql WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db')"
    printf '%s \\gexec\n' "$sql" | psql -v ON_ERROR_STOP=1 \
        --username "$POSTGRES_USER" --dbname postgres
done
