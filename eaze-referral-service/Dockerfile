# syntax=docker/dockerfile:1
FROM python:3.14-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
# Operational scripts need to be runnable against a real deployment, not just a dev checkout —
# scripts/check_redash.py in particular is meant to be run wherever the REDASH_* env vars
# actually live, which is inside this image.
COPY scripts ./scripts

RUN chown -R app:app /srv
USER app

EXPOSE 8000

# One process per pod — Kubernetes replicas provide horizontal scaling, so no gunicorn/multi-worker
# wrapper is needed inside the container (that would complicate graceful shutdown and logging for
# no benefit under this deployment model).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
