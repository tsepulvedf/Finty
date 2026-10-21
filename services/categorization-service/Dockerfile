# syntax=docker/dockerfile:1
#
# Imagen de categorization-service (ADR-07, ADR-16). Sin base de datos ni
# migraciones: solo el proceso web (gunicorn).

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Las dependencias van antes que el codigo para reutilizar la capa mientras
# requirements.txt no cambie.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# El proceso no corre como root.
RUN groupadd --system --gid 10001 finty \
    && useradd --system --uid 10001 --gid finty --no-create-home finty
USER finty

EXPOSE 8000

CMD ["gunicorn", "app:create_app()", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--access-logfile", "-"]
