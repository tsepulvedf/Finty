FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-container.txt && useradd --create-home appuser
COPY --chown=appuser:appuser . .
RUN mkdir -p /app/staticfiles && chown appuser:appuser /app/staticfiles
USER appuser
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", "config.wsgi:application"]
