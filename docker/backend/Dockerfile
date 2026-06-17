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
# torch/torchvision/torchaudio are excluded from the filtered list and installed
# explicitly from the CPU index below. Otherwise the final filtered install pulls
# the default-PyPI CUDA build (libtorch_cuda.so + nvidia-*-cu13, several GB),
# bloating this CPU-only image and exhausting CI disk (#10251).
RUN grep -v -E "(autobot.shared|^-r |^torch==|^torchvision==|^torchaudio==)" /tmp/requirements.txt \
        > /app/requirements-filtered.txt \
    && python3 -m pip install --no-cache-dir -r /app/requirements-root.txt \
    && python3 -m pip install --no-cache-dir \
        torch==2.12.0 torchvision==0.27.0 torchaudio==2.11.0 \
        --index-url https://download.pytorch.org/whl/cpu \
    && python3 -m pip install --no-cache-dir -r /app/requirements-filtered.txt


# ---- Production stage ----
FROM python:3.12-slim-bookworm AS production

ENV DEBIAN_FRONTEND=noninteractive

# --- claude CLI install (GH#9950) ---
# Replaces the prior unpinned `curl | bash` supply-chain risk with Anthropic's
# official SIGNED apt repository — the same keyring + sources-list + apt-get
# pattern used for `gh` below. apt verifies every package against the Claude Code
# release signing key on every install, so there is no manual sha256 to supply
# and no self-updating-installer hash to chase. The signing key (fingerprint
# 31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE) is the stable trust anchor;
# new releases are just newer signed packages, so the build never fails-closed on
# an upstream installer refresh. apt installs do not auto-update (correct for an
# immutable image — the native curl|bash installer auto-updates in the background).
#
# CLAUDE_CLI_VERSION pins an exact package version for reproducible builds
# (e.g. 2.1.89); leave empty to take the current build from the stable channel.
ARG CLAUDE_CLI_VERSION=""

# Install runtime deps + LLC agent CLIs (GH#9793) from signed apt repos — no
# pipe-to-bash for either CLI. `claude` lands on the system PATH (no HOME
# redirect / symlink needed); the build-time `--version` checks prove both
# resolve, so an install regression fails the build instead of silently
# breaking LLC dispatch.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && install -m 0755 -d /etc/apt/keyrings \
    # gh — official GitHub signed apt repo
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    # claude-code — official Anthropic signed apt repo (stable channel)
    && curl -fsSL https://downloads.claude.ai/keys/claude-code.asc \
       -o /etc/apt/keyrings/claude-code.asc \
    && chmod go+r /etc/apt/keyrings/claude-code.asc \
    && echo "deb [signed-by=/etc/apt/keyrings/claude-code.asc] https://downloads.claude.ai/claude-code/apt/stable stable main" \
       > /etc/apt/sources.list.d/claude-code.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && if [ -n "$CLAUDE_CLI_VERSION" ]; then \
         apt-get install -y --no-install-recommends "claude-code=${CLAUDE_CLI_VERSION}"; \
       else \
         apt-get install -y --no-install-recommends claude-code; \
       fi \
    && gh --version \
    && claude --version \
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

# Copy entrypoint script (runs migrations before app start, #9759)
COPY docker/backend/entrypoint.sh /app/entrypoint.sh

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

# Runs Alembic migrations for Postgres-backed user modes, then exec's CMD (#9759)
ENTRYPOINT ["/app/entrypoint.sh"]

CMD ["python3", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "8001", \
     "--workers", "1", "--app-dir", "/app/autobot-backend"]
