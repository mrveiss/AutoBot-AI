#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# SLM Docker entrypoint — runs database migrations before starting the app.
# Ensures tables exist on first boot before uvicorn accepts connections (#1893).
set -e

cd /app/autobot-slm-backend

echo "Running SLM database migrations..."
python3 -m migrations.runner || {
    echo "ERROR: Migration failed — retrying in 5s..."
    sleep 5
    python3 -m migrations.runner || {
        echo "FATAL: Migration failed after retry. Aborting."
        exit 1
    }
}
echo "Migrations complete."

exec "$@"
