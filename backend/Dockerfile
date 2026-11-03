# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
# CA d'entreprise optionnelle (proxy d'inspection TLS) : EXTRA_CA_FILE dans .env
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --no-cache-dir .
COPY alembic.ini ./
COPY alembic ./alembic
RUN useradd --system --no-create-home app && mkdir -p /data/outbox-mails && chown app /data/outbox-mails
USER app
EXPOSE 8000
# Les migrations sont appliquées au démarrage ; ne jamais modifier une migration existante.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
