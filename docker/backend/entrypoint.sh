#!/bin/sh
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

# Subshell keeps the app's cwd at the image WORKDIR (/app) — the backend
# writes relative paths from there, so leaking the cd into exec would
# silently relocate runtime data when the user mode flips.
run_migrations() {
    (cd /app/autobot-backend && python3 -m alembic -c migrations/alembic.ini upgrade head)
}

if [ "$USER_MODE" != "single_user" ]; then
    echo "Running backend database migrations (user mode: ${USER_MODE})..."
    run_migrations || {
        echo "ERROR: Migration failed — retrying in 5s..."
        sleep 5
        run_migrations || {
            echo "FATAL: Migration failed after retry. Aborting."
            exit 1
        }
    }
    echo "Migrations complete."
fi

exec "$@"
