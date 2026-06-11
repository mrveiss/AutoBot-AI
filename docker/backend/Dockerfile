# AutoBot Backend - FastAPI Application (#1809, #1836)
# python:3.12-slim-bookworm base — eliminates deadsnakes PPA cold build overhead (#6213)
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# ---- Dependencies stage ----
FROM python:3.12-slim-bookworm AS deps

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Install shared module first (backend depends on it)
COPY autobot_shared/pyproject.toml /app/autobot_shared/pyproject.toml
COPY autobot_shared/ /app/autobot_shared/
RUN python3 -m pip install --no-cache-dir /app/autobot_shared

# Copy root requirements (referenced by backend via -r ../requirements.txt)
COPY requirements.txt /app/requirements-root.txt

# Install backend dependencies (filter out local refs, install root deps separately)
COPY autobot-backend/requirements.txt /tmp/requirements.txt
RUN grep -v -E "(autobot.shared|^-r )" /tmp/requirements.txt > /app/requirements-filtered.txt \
    && python3 -m pip install --no-cache-dir -r /app/requirements-root.txt \
    && python3 -m pip install --no-cache-dir \
        "torch>=2.11.0" "torchvision>=0.26.0" \
        --index-url https://download.pytorch.org/whl/cpu \
    && python3 -m pip install --no-cache-dir -r /app/requirements-filtered.txt


# ---- Production stage ----
FROM python:3.12-slim-bookworm AS production

ENV DEBIAN_FRONTEND=noninteractive

# Install runtime deps + LLC agent CLIs (GH#9793).
# gh: official GitHub apt repo (keyring + sources list + apt-get install).
# claude: native installer writes to ~/.local/bin by default; we redirect the
#   install prefix to /usr/local so the binary lands in PATH for the autobot
#   user without shell-profile tricks.  Both CLIs are installed as root before
#   USER autobot so they reach /usr/local/bin with the correct ownership.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && CLAUDE_INSTALL_DIR=/usr/local curl -fsSL https://claude.ai/install.sh | bash \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user. Pin uid/gid 999 to match the SLM image (#9905) so the
# shared autobot_secrets volume is owned/readable consistently across services.
RUN groupadd -r --gid 999 autobot && useradd -r --uid 999 -g autobot -d /app autobot

WORKDIR /app

# Copy Python packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/ /usr/local/lib/python3.12/
COPY --from=deps /usr/local/bin/ /usr/local/bin/

# Copy shared module
COPY autobot_shared/ /app/autobot_shared/

# Copy backend source
COPY autobot-backend/ /app/autobot-backend/

# Copy shared config files (llm_models, permission_rules) into backend config dir
COPY autobot-infrastructure/shared/config/llm_models.yaml /app/autobot-backend/config/llm_models.yaml
COPY autobot-infrastructure/shared/config/permission_rules.yaml /app/autobot-backend/config/permission_rules.yaml

# Create required directories (including /opt/autobot for model storage)
RUN mkdir -p /app/data /app/logs /app/autobot-backend/data /opt/autobot/data \
    && chown -R autobot:autobot /app /opt/autobot

# Symlink for legacy import compatibility (database only)
RUN ln -s /app/autobot-backend/database /app/database

USER autobot

# Environment
ENV PYTHONPATH=/app:/app/autobot-backend:/app/autobot_shared
ENV AUTOBOT_ENVIRONMENT=production
ENV AUTOBOT_LOG_LEVEL=INFO
ENV AUTOBOT_DEPLOYMENT_MODE=local
ENV AUTOBOT_BACKEND_PORT=8001

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8001/api/system/health || exit 1

CMD ["python3", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "8001", \
     "--workers", "1", "--app-dir", "/app/autobot-backend"]
