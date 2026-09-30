FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/categorization/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --create-home appuser
# Solo Python puro y el adaptador Flask; no se copia Django, ORM ni settings.
COPY core/__init__.py core/__init__.py
COPY core/domain/ core/domain/
COPY finance/__init__.py finance/__init__.py
COPY finance/domain/ finance/domain/
COPY finance/infra/__init__.py finance/infra/__init__.py
COPY finance/infra/categorizers.py finance/infra/categorizers.py
COPY services/__init__.py services/__init__.py
COPY services/categorization/ services/categorization/
USER appuser
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "15", "services.categorization.app:create_app()"]
