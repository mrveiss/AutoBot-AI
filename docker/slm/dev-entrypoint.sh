#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Dev-mode entrypoint for the SLM container (#1985).
#
# Same bind-mount problem as the backend: host volume mounts destroy
# Dockerfile-created symlinks and shadow the pip-installed autobot-shared
# package. This script restores the environment before starting the app.
#
# In dev mode this script replaces the production entrypoint.sh which
# runs database migrations. Migrations still run here first.
set -e

echo "[dev-entrypoint] Recreating symlinks destroyed by bind mounts..."

# Symlink: /app/autobot_shared -> /app/autobot-shared
ln -sf /app/autobot-shared /app/autobot_shared

# Symlink: /app/autobot-slm-backend/autobot_shared -> /app/autobot-shared
ln -sf /app/autobot-shared /app/autobot-slm-backend/autobot_shared

echo "[dev-entrypoint] Re-installing autobot-shared (editable)..."
pip install -e /app/autobot-shared --quiet 2>/dev/null || true

echo "[dev-entrypoint] Running SLM database migrations..."
cd /app/autobot-slm-backend
python3.12 -m migrations.runner || {
    echo "ERROR: Migration failed -- retrying in 5s..."
    sleep 5
    python3.12 -m migrations.runner || {
        echo "FATAL: Migration failed after retry. Aborting."
        exit 1
    }
}
echo "[dev-entrypoint] Migrations complete. Starting application..."

exec "$@"
