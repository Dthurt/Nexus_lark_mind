# Nexus-Lark-Mind — single image, multi-process entrypoints
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
COPY web-static ./web-static
COPY plugins_volume ./plugins_volume
COPY scripts ./scripts
COPY docs ./docs

RUN mkdir -p /app/data /app/logs \
    && chmod +x /app/scripts/*.sh || true

ENV PYTHONPATH=/app

# Default entry is adapters; compose overrides CMD per service
EXPOSE 8000 8001 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${HEALTH_PORT:-8000}/health" || exit 1

CMD ["python", "-m", "src.entry_adapters"]
