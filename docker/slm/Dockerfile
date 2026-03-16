# AutoBot SLM Backend - Service Lifecycle Manager (#1809, #1836)
# Ubuntu 22.04 + Python 3.12 (deadsnakes PPA)
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# ---- Dependencies stage ----
FROM ubuntu:22.04 AS deps

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install Python 3.12 from deadsnakes PPA + build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common gpg-agent \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/* \
    && python3.12 -m ensurepip --upgrade \
    && python3.12 -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Install shared module
COPY autobot-shared/requirements.txt /app/autobot-shared/requirements.txt
COPY autobot-shared/setup.py /app/autobot-shared/setup.py
COPY autobot-shared/ /app/autobot-shared/
RUN python3.12 -m pip install --no-cache-dir -r /app/autobot-shared/requirements.txt \
    && python3.12 -m pip install --no-cache-dir /app/autobot-shared

# Install SLM dependencies
COPY autobot-slm-backend/requirements.txt /tmp/requirements.txt
RUN grep -v -E "(autobot-shared|^-r )" /tmp/requirements.txt > /app/requirements-filtered.txt || true \
    && python3.12 -m pip install --no-cache-dir -r /app/requirements-filtered.txt


# ---- Production stage ----
FROM ubuntu:22.04 AS production

ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.12 + runtime deps (ansible for node provisioning)
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common gpg-agent \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv \
    curl openssh-client sshpass rsync ansible \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r autobot && useradd -r -g autobot -d /app autobot

WORKDIR /app

# Copy Python packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/dist-packages/ /usr/local/lib/python3.12/dist-packages/
COPY --from=deps /usr/lib/python3/dist-packages/ /usr/lib/python3/dist-packages/
COPY --from=deps /usr/local/bin/ /usr/local/bin/

# Copy shared module
COPY autobot-shared/ /app/autobot-shared/

# Copy SLM backend source
COPY autobot-slm-backend/ /app/autobot-slm-backend/

# Copy Ansible playbooks and inventory
COPY autobot-infrastructure/ /app/autobot-infrastructure/

# Create required directories
RUN mkdir -p /app/data /app/logs /app/autobot-slm-backend/data \
    && chown -R autobot:autobot /app

# Symlink for import compatibility
RUN ln -s /app/autobot-shared /app/autobot_shared \
    && ln -s /app/autobot-shared /app/autobot-slm-backend/autobot_shared

USER autobot

ENV PYTHONPATH=/app:/app/autobot-slm-backend:/app/autobot-shared
ENV AUTOBOT_ENVIRONMENT=production
ENV AUTOBOT_LOG_LEVEL=INFO

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python3.12", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--app-dir", "/app/autobot-slm-backend"]
