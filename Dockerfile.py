# syntax=docker/dockerfile:1

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cache layer)
COPY requirements.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-postgres.txt

# Copy project source
COPY . .

# Runtime defaults - override via .env or environment
ENV APP_HOST=0.0.0.0 \
    APP_PORT=8088 \
    LOG_LEVEL=INFO \
    DATA_DIR=/data \
    INTAKE_DIR=/data/intake \
    PROCESSED_DIR=/data/processed \
    REJECT_DIR=/data/reject \
    OUTBOX_DIR=/data/outbox \
    WORKER_POLL_SECONDS=5 \
    SFTP_ENABLED=false

EXPOSE 8088

# Persistent data and optional external master-data mount
VOLUME ["/data"]

# Default: run API server
# Override for worker: docker run <image> python run_worker.py
CMD ["python", "run_api.py"]
