# syntax=docker/dockerfile:1
#
# Imagenes del monolito Django y del Gateway Nginx (ADR-16).
#
# Dos etapas en un solo archivo para que Nginx reciba los estaticos que
# `collectstatic` genera en la imagen de Django. Copiarlos en el build evita el
# volumen compartido, que solo se puebla la primera vez que se crea y dejaria
# estaticos viejos tras cada reconstruccion.
#
#   docker compose build   construye ambas con su `target`

# --- Catalogos de traduccion -------------------------------------------------
# Compila los .po de `locale/` a .mo con GNU gettext (ADR-11). Va en una etapa
# propia para que la imagen final no cargue gettext: solo recibe los .mo. Los .mo
# no se versionan, asi que nunca quedan desactualizados respecto a los .po.
FROM python:3.11-slim AS messages

RUN apt-get update     && apt-get install -y --no-install-recommends gettext     && rm -rf /var/lib/apt/lists/*

COPY locale/ /locale/
RUN find /locale -name "*.po" -exec sh -c 'msgfmt --check -o "${1%.po}.mo" "$1"' _ {} \;

# --- Monolito Django ---------------------------------------------------------
FROM python:3.11-slim AS django

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Las dependencias van antes que el codigo para que la capa se reutilice
# mientras requirements.txt no cambie.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY --from=messages /locale/ /app/locale/

# `settings.py` exige estas variables al importarse, pero collectstatic no abre
# conexion a la base: los valores son marcadores que solo existen en este paso y
# no quedan en la imagen.
RUN SECRET_KEY=solo-para-collectstatic \
    DB_NAME=no-usada DB_USER=no-usada DB_PASSWORD=no-usada \
    DB_HOST=no-usada DB_PORT=5432 \
    python manage.py collectstatic --noinput

# El proceso no corre como root.
RUN groupadd --system --gid 10001 finty \
    && useradd --system --uid 10001 --gid finty --no-create-home finty
USER finty

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--access-logfile", "-"]

# --- Gateway Nginx -----------------------------------------------------------
FROM nginx:1.28-alpine AS gateway

# El `default.conf` de la imagen tambien escucha en el puerto 80 y competiria
# con el servidor de Finty.
RUN rm /etc/nginx/conf.d/default.conf

COPY deploy/nginx/conf.d/ /etc/nginx/conf.d/
COPY deploy/nginx/snippets/ /etc/nginx/snippets/
COPY --from=django /app/staticfiles/ /usr/share/nginx/finty-static/
