FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir -U pip setuptools wheel

COPY pyproject.toml README.md /app/
COPY synqc_backend /app/synqc_backend

RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UVICORN_WORKERS=1

COPY --from=builder /install /usr/local

RUN mkdir -p /data
ENV SYNQC_JOB_QUEUE_DB_PATH=/data/jobs.sqlite3

EXPOSE 8001

CMD ["sh", "-c", "uvicorn synqc_backend.api:app --host 0.0.0.0 --port 8001 --workers ${UVICORN_WORKERS}"]
