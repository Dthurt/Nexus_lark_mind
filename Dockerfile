# syntax=docker/dockerfile:1
# Nexus-Lark-Mind — multi-stage image (React UI + Python services)
# Build:  docker build -t nexus-lark-mind:latest .
# Crawl:  docker build --build-arg ENABLE_CRAWL=1 -t nexus-lark-mind:crawl .

ARG PYTHON_IMAGE=python:3.11-slim-bookworm
ARG NODE_IMAGE=node:22-alpine

# ---------------------------------------------------------------------------
# Stage: frontend
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage: Python deps (cached layer)
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS python-deps
ARG ENABLE_CRAWL=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-crawl.txt ./
RUN pip install --upgrade pip \
    && if [ "$ENABLE_CRAWL" = "1" ]; then \
         pip install -r requirements-crawl.txt; \
       else \
         pip install -r requirements.txt; \
       fi

# ---------------------------------------------------------------------------
# Stage: runtime
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
ARG ENABLE_CRAWL=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    PYTHONPATH=/app \
    PLUGINS_DIR=/app/plugins_volume \
    WEB_STATIC_DIR=/app/web-static \
    ENABLE_CRAWL=${ENABLE_CRAWL}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        libglib2.0-0 \
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

COPY src ./src
COPY plugins_volume ./plugins_volume
COPY scripts ./scripts
COPY docs ./docs
COPY --from=web /src/web-static ./web-static

RUN mkdir -p /app/data /app/logs \
    && chmod +x /app/scripts/*.sh 2>/dev/null || true

# Optional Playwright browsers for Crawl4AI
RUN if [ "$ENABLE_CRAWL" = "1" ]; then \
      python -m playwright install --with-deps chromium || crawl4ai-setup || true; \
    fi

EXPOSE 8000 8001 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${HEALTH_PORT:-8000}/health" || exit 1

# Default: adapters; compose overrides per service
CMD ["python", "-m", "src.entry_adapters"]
