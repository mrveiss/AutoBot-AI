#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# #20639: the SLM's databases moved to their own Postgres. On an install that had them in the main
# one, copy them across, once, before the SLM starts. The old copies are left exactly as they are;
# deleting them is only ever proposed through the review queue (#17038).
#
# A failure exits non-zero, so the SLM doesn't start: starting it on an empty database while the
# real data sits next door would look like a fresh install. Rerunning replaces a partial copy.
# When the marker database exists, this needs nothing from the main Postgres, so the SLM can start
# without it.
set -euo pipefail

: "${POSTGRES_USER:?compose sets this}" "${PGPASSWORD:?compose sets this}" "${SLM_DB_NAME:?compose sets this}"
OLD_HOST="${SLM_COPY_OLD_HOST:-autobot-postgres}"
NEW_HOST="${SLM_COPY_NEW_HOST:-autobot-slm-postgres}"
OLD_DATA="${SLM_COPY_OLD_DATA:-/old-postgres}"
WAIT_SECONDS="${SLM_COPY_WAIT_SECONDS:-300}"
MARKER=slm_copy_done

OLD_PORT="${SLM_COPY_OLD_PORT:-5432}"
NEW_PORT="${SLM_COPY_NEW_PORT:-5432}"

new_psql() { psql -h "$NEW_HOST" -p "$NEW_PORT" -U "$POSTGRES_USER" -v ON_ERROR_STOP=1 -qtA "$@"; }
old_psql() { psql -h "$OLD_HOST" -p "$OLD_PORT" -U "$POSTGRES_USER" -v ON_ERROR_STOP=1 -qtA "$@"; }
database_exists() { [ "$("$1" -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$2'")" = 1 ]; }

mark_done() { new_psql -d postgres -c "CREATE DATABASE ${MARKER}"; }

if database_exists new_psql "$MARKER"; then
    echo "SLM databases: already in place"
    exit 0
fi

if [ ! -f "${OLD_DATA}/PG_VERSION" ]; then
    echo "SLM databases: no earlier Postgres data, nothing to copy"
    mark_done
    exit 0
fi

waited=0
until pg_isready -q -h "$OLD_HOST" -p "$OLD_PORT" -U "$POSTGRES_USER" -d postgres; do
    if [ "$waited" -ge "$WAIT_SECONDS" ]; then
        echo "ERROR: the SLM's data is still in the main Postgres, which isn't reachable at ${OLD_HOST}." >&2
        echo "  The SLM won't start on an empty database. Start it, then start the SLM again:" >&2
        echo "    docker compose up -d autobot-postgres" >&2
        exit 1
    fi
    sleep 5
    waited=$((waited + 5))
done

copy_database() {  # name
    if ! database_exists old_psql "$1"; then
        echo "SLM databases: ${1} isn't in the main Postgres, nothing to copy"
        return 0
    fi
    database_exists new_psql "$1" || new_psql -d postgres -c "CREATE DATABASE \"${1}\""
    # --clean: a rerun after a failure replaces the partial copy; the SLM hasn't started on it.
    pg_dump -h "$OLD_HOST" -p "$OLD_PORT" -U "$POSTGRES_USER" -Fc "$1" |
        pg_restore -h "$NEW_HOST" -p "$NEW_PORT" -U "$POSTGRES_USER" -d "$1" --clean --if-exists --no-owner --exit-on-error
    echo "SLM databases: copied ${1}; the original stays in the main Postgres"
}

copy_database "$SLM_DB_NAME"
copy_database slm_users
mark_done
