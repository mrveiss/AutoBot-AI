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
# User management is always Postgres-backed (#10636), so migrations always run.
# The retired single_user mode used to skip them; skipping now would leave the
# users schema missing (#18729).
set -eu

USER_MODE="${AUTOBOT_USER_MODE:-single_company}"

# The one retry below re-runs `upgrade head` after a partial failure. That is safe only
# because every non-transactional migration (autocommit_block) is resumable: enum values
# use ADD VALUE IF NOT EXISTS, and a concurrent index build drops an invalid leftover
# before rebuilding. repo_tests/docker_admin_seed_18729_test.py pins both.

# Subshell keeps the app's cwd at the image WORKDIR (/app) — the backend
# writes relative paths from there, so leaking the cd into exec would
# silently relocate runtime data when the user mode flips.
run_migrations() {
    (cd /app/autobot-backend && python3 -m alembic -c migrations/alembic.ini upgrade head)
}

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

# #19869, #19738: the pinned speech-to-text and code-embedding models, into the cache volume (HF_HOME). A model
# already there costs no network; one that cannot be fetched stops the container, naming it and the room left.
case "${AUTOBOT_PREFETCH_MODELS:-true}" in
    false | False | FALSE | 0 | no | off) echo "Model pre-fetch skipped (AUTOBOT_PREFETCH_MODELS=${AUTOBOT_PREFETCH_MODELS})." ;;
    *)
        echo "Fetching the pinned models into ${HF_HOME:-the default cache}..."
        python3 -m autobot_shared.model_prefetch || {
            echo "FATAL: a pinned model is missing and could not be fetched (see FAILED above). Aborting."
            exit 1
        }
        ;;
esac

exec "$@"
