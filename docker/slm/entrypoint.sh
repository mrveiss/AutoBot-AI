#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
