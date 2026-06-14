#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Dev-mode entrypoint for the backend container (#1985).
#
# Problem: bind mounts in docker-compose.override.yml replace directories
# that contain Dockerfile-created symlinks and pip-installed packages.
# Specifically:
#   - ./autobot-backend:/app/autobot-backend  may shadow installed packages
#   - ./autobot_shared:/app/autobot_shared    replaces the directory that
#     pip installed as a package, shadowing the pip copy
#
# This script runs before the main command to restore the environment:
#   1. Re-installs autobot_shared as editable pip package so imports work
#   2. Exec's the original command (passed as arguments)
set -e

echo "[dev-entrypoint] Re-installing autobot_shared (editable)..."

# The bind mount for autobot_shared replaces the pip-installed copy.
# Re-install in editable mode so code changes take effect immediately
# without rebuilding the container.
pip install -e /app/autobot_shared --quiet 2>/dev/null || true

# Symlink: /app/database -> /app/autobot-backend/database
# Used by: legacy imports that reference database at /app level
ln -sf /app/autobot-backend/database /app/database

echo "[dev-entrypoint] Dev environment ready. Starting application..."
exec "$@"
