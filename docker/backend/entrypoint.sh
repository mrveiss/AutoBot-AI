#!/bin/sh
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Backend Docker entrypoint — runs Alembic migrations before starting the app
# so a fresh Postgres database is fully bootstrapped before uvicorn accepts
# connections (#9759). Mirrors the SLM entrypoint pattern (docker/slm).
#
# Migrations only apply to Postgres-backed user modes; the default single_user
# mode has no Postgres schema, so the step is skipped entirely.
set -eu

USER_MODE="${AUTOBOT_USER_MODE:-single_user}"

if [ "$USER_MODE" != "single_user" ]; then
    cd /app/autobot-backend
    echo "Running backend database migrations (user mode: ${USER_MODE})..."
    python3 -m alembic -c migrations/alembic.ini upgrade head || {
        echo "ERROR: Migration failed — retrying in 5s..."
        sleep 5
        python3 -m alembic -c migrations/alembic.ini upgrade head || {
            echo "FATAL: Migration failed after retry. Aborting."
            exit 1
        }
    }
    echo "Migrations complete."
fi

exec "$@"
