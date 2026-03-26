#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Dev-mode entrypoint for the backend container (#1985).
#
# Problem: bind mounts in docker-compose.override.yml replace directories
# that contain Dockerfile-created symlinks and pip-installed packages.
# Specifically:
#   - ./autobot-backend:/app/autobot-backend  destroys the symlink at
#     /app/autobot-backend/autobot_shared -> /app/autobot-shared
#   - ./autobot-shared:/app/autobot-shared    replaces the directory that
#     pip installed as a package, shadowing the pip copy
#
# This script runs before the main command to restore the environment:
#   1. Recreates symlinks that bind mounts destroyed
#   2. Re-installs autobot-shared as editable pip package so imports work
#   3. Exec's the original command (passed as arguments)
set -e

echo "[dev-entrypoint] Recreating symlinks destroyed by bind mounts..."

# Symlink: /app/autobot_shared -> /app/autobot-shared
# Used by: PYTHONPATH imports of autobot_shared at /app level
ln -sf /app/autobot-shared /app/autobot_shared

# Symlink: /app/autobot-backend/autobot_shared -> /app/autobot-shared
# Used by: relative imports from within autobot-backend/
ln -sf /app/autobot-shared /app/autobot-backend/autobot_shared

# Symlink: /app/database -> /app/autobot-backend/database
# Used by: legacy imports that reference database at /app level
ln -sf /app/autobot-backend/database /app/database

echo "[dev-entrypoint] Re-installing autobot-shared (editable)..."

# The bind mount for autobot-shared replaces the pip-installed copy.
# Re-install in editable mode so code changes take effect immediately
# without rebuilding the container.
pip install -e /app/autobot-shared --quiet 2>/dev/null || true

echo "[dev-entrypoint] Dev environment ready. Starting application..."
exec "$@"
