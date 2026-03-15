# AutoBot Backend - FastAPI Application
# Multi-stage build for optimized production deployment
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# ---- Dependencies stage ----
FROM python:3.10-slim AS deps

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install shared module first (backend depends on it via -e ../autobot-shared)
COPY autobot-shared/requirements.txt /app/autobot-shared/requirements.txt
COPY autobot-shared/setup.py /app/autobot-shared/setup.py
COPY autobot-shared/ /app/autobot-shared/
RUN pip install --no-cache-dir -r /app/autobot-shared/requirements.txt \
    && pip install --no-cache-dir /app/autobot-shared

# Install backend dependencies (skip the -e ../autobot-shared line)
COPY autobot-backend/requirements.txt /tmp/requirements.txt
RUN grep -v "autobot-shared" /tmp/requirements.txt > /app/requirements-filtered.txt \
    && pip install --no-cache-dir -r /app/requirements-filtered.txt


# ---- Production stage ----
FROM python:3.10-slim AS production

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r autobot && useradd -r -g autobot -d /app autobot

WORKDIR /app

# Copy Python packages from deps stage
COPY --from=deps /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=deps /usr/local/bin/ /usr/local/bin/

# Copy shared module
COPY autobot-shared/ /app/autobot-shared/

# Copy backend source
COPY autobot-backend/ /app/autobot-backend/

# Create required directories
RUN mkdir -p /app/data /app/logs /app/autobot-backend/data \
    && chown -R autobot:autobot /app

# Symlink for import compatibility
RUN ln -s /app/autobot-shared /app/autobot_shared \
    && ln -s /app/autobot-shared /app/autobot-backend/autobot_shared

USER autobot

# Environment
ENV PYTHONPATH=/app:/app/autobot-backend:/app/autobot-shared
ENV AUTOBOT_ENVIRONMENT=production
ENV AUTOBOT_LOG_LEVEL=INFO
ENV AUTOBOT_DEPLOYMENT_MODE=local

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/api/system/health || exit 1

CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--app-dir", "/app/autobot-backend"]
