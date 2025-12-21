FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir -U pip setuptools wheel

COPY backend/ /app/backend/
RUN pip install --no-cache-dir /app/backend

# Optional: create a writable data dir for sqlite spool
RUN mkdir -p /data
ENV SYNQC_JOB_QUEUE_DB_PATH=/data/jobs.sqlite3

EXPOSE 8001

CMD ["uvicorn", "synqc_backend.api:app", "--host", "0.0.0.0", "--port", "8001"]
