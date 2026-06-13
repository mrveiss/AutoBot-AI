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

# --- claude CLI pinning + integrity (GH#9950) ---
# Hardening of the prior unpinned `curl | bash` supply-chain risk:
#   1. CLAUDE_CLI_VERSION pins an exact published release (not a moving channel).
#   2. CLAUDE_INSTALLER_SHA256 pins the sha256 of the installer bootstrap script.
#      The installer is downloaded to a file, its checksum verified, and ONLY
#      THEN executed — no piping of an unverified stream into bash.
#   3. The installer itself then fetches the version-pinned binary and verifies
#      it against its own signed sha256 manifest (second integrity layer).
#
# To update the pin:
#   curl -fsSLO https://claude.ai/install.sh
#   sha256sum install.sh        # -> paste into CLAUDE_INSTALLER_SHA256 below
#   # pick the target version from https://github.com/anthropics/claude-code/releases
# Build override (CI / release pipeline supplies the verified values):
#   docker build --build-arg CLAUDE_CLI_VERSION=1.2.3 \
#                --build-arg CLAUDE_INSTALLER_SHA256=<64-hex> ...
ARG CLAUDE_CLI_VERSION=stable
# REQUIRED: no default — the build MUST fail unless a real, human-verified
# sha256 is supplied. A placeholder/empty value makes the verification step
# (and therefore the build) fail loudly rather than silently piping to bash.
ARG CLAUDE_INSTALLER_SHA256=""

# Install runtime deps + LLC agent CLIs (GH#9793).
# gh: official GitHub apt repo (keyring + sources list + apt-get install) — signed apt, no pipe-to-bash.
# claude: download-then-verify-then-run (GH#9950). The official installer ONLY
#   installs to $HOME/.local/bin (CLAUDE_INSTALL_DIR is not honored — proven by
#   the smoke-test build gate), so HOME is redirected to a world-readable prefix
#   and the launcher symlinked into /usr/local/bin for the autobot user.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && install -m 0755 -d /opt/claude-cli \
    # Fail early if the integrity pin was not supplied (no blind pipe-to-bash).
    && if [ -z "$CLAUDE_INSTALLER_SHA256" ]; then \
         echo "ERROR: CLAUDE_INSTALLER_SHA256 build-arg is required (GH#9950). See Dockerfile comment for how to compute it." >&2; \
         exit 1; \
       fi \
    # 1) download the installer to a file (do NOT execute the stream)
    && curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh \
    # 2) verify its sha256 against the pinned, human-verified value
    && echo "${CLAUDE_INSTALLER_SHA256}  /tmp/claude-install.sh" | sha256sum -c - \
    # 3) only now execute it, pinned to an exact version, HOME-redirected
    && HOME=/opt/claude-cli bash /tmp/claude-install.sh "${CLAUDE_CLI_VERSION}" \
    && rm -f /tmp/claude-install.sh \
    && ln -s /opt/claude-cli/.local/bin/claude /usr/local/bin/claude \
    && chmod -R a+rX /opt/claude-cli \
    # Build-time proof both CLIs resolve on PATH — without this, an installer
    # prefix change would silently break LLC dispatch (gate skips forever).
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
