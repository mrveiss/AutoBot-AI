# AutoBot SLM Backend - Service Lifecycle Manager (#1809, #1836)
# python:3.12-slim-bookworm base — eliminates deadsnakes PPA cold build overhead (#6213)
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# ---- Dependencies stage ----
FROM python:3.14-slim-bookworm AS deps

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Install shared module
COPY autobot_shared/pyproject.toml /app/autobot_shared/pyproject.toml
COPY autobot_shared/ /app/autobot_shared/
RUN python3 -m pip install --no-cache-dir /app/autobot_shared

# Install SLM dependencies
COPY autobot-slm-backend/requirements.txt /tmp/requirements.txt
RUN grep -v -E "(autobot_shared|^-r )" /tmp/requirements.txt > /app/requirements-filtered.txt || true \
    && python3 -m pip install --no-cache-dir -r /app/requirements-filtered.txt


# ---- Production stage ----
FROM python:3.14-slim-bookworm AS production

ENV DEBIAN_FRONTEND=noninteractive

# Install runtime deps (ansible for node provisioning)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git openssh-client sshpass rsync ansible \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r --gid 999 autobot && useradd -r --uid 999 -g autobot -d /app autobot

WORKDIR /app

# Copy Python packages from deps stage
COPY --from=deps /usr/local/lib/python3.14/ /usr/local/lib/python3.14/
COPY --from=deps /usr/local/bin/ /usr/local/bin/

# Copy shared module
COPY autobot_shared/ /app/autobot_shared/

# Copy SLM backend source
COPY autobot-slm-backend/ /app/autobot-slm-backend/

# Copy Ansible playbooks and inventory
COPY autobot-infrastructure/ /app/autobot-infrastructure/

# Create required directories
RUN mkdir -p /app/data /app/logs /app/autobot-slm-backend/data /app/autobot-slm-backend/config \
    && chown -R autobot:autobot /app

# Copy entrypoint script (runs migrations before app start)
COPY docker/slm/entrypoint.sh /app/entrypoint.sh

USER autobot

ENV PYTHONPATH=/app:/app/autobot-slm-backend:/app/autobot_shared
ENV AUTOBOT_ENVIRONMENT=production
ENV AUTOBOT_LOG_LEVEL=INFO

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python3", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--app-dir", "/app/autobot-slm-backend"]
