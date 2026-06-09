#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Generate per-deployment signing secrets for the docker-compose stack (GH#9775).
#
# The compose file no longer ships static fallback values for AUTOBOT_JWT_SECRET
# / SECRET_KEY — a committed shared signing secret allows JWT/session forgery
# against any default deployment. This script writes unique, random secrets to a
# gitignored docker/.env.secrets that you then pass to compose.
#
# Idempotent: existing values are preserved, never overwritten or printed.
#
# Usage:
#   bash docker/generate-secrets.sh
#   docker compose --env-file docker/.env.docker --env-file docker/.env.secrets up -d
set -euo pipefail

SECRETS_FILE="$(cd "$(dirname "$0")" && pwd)/.env.secrets"

if ! command -v openssl >/dev/null 2>&1; then
    echo "ERROR: openssl is required to generate secrets." >&2
    exit 1
fi

touch "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"

ensure_secret() {
    local key="$1"
    if grep -q "^${key}=" "$SECRETS_FILE" 2>/dev/null; then
        echo "  ${key}: already set — keeping existing value"
    else
        printf '%s=%s\n' "$key" "$(openssl rand -hex 32)" >>"$SECRETS_FILE"
        echo "  ${key}: generated"
    fi
}

echo "Writing signing secrets to ${SECRETS_FILE}"
ensure_secret AUTOBOT_JWT_SECRET
ensure_secret SECRET_KEY

echo ""
echo "Done. Start the stack with both env files:"
echo "  docker compose --env-file docker/.env.docker --env-file docker/.env.secrets up -d"
