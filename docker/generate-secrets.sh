#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Generate per-deployment secrets for the docker-compose stack (GH#9775, #16275).
#
# PASSWORDS (#16275): this also writes AUTOBOT_DB_PASSWORD and
# GRAFANA_ADMIN_PASSWORD. The tracked docker/.env.docker and .env.docker, and
# the compose fallbacks, still default both to the application's own name,
# which anyone can guess. Pass docker/.env.secrets AFTER docker/.env.docker, as
# shown below, so the generated values win.
#
# EXISTING deployment? Do not hand it a newly generated AUTOBOT_DB_PASSWORD.
# Postgres keeps the password its volume was created with and ignores a new one,
# and the signing secrets pinned below would replace the ones the stack
# generated for itself, signing every session out.
#
# SIGNING SECRETS: since GH#9905 the compose stack auto-generates them on the
# first `up` (autobot-secrets-init + shared autobot_secrets volume). This script
# PINS them (share one across hosts, or manage them yourself) -- an explicit
# value always overrides the auto-generated one. The compose file ships no
# static fallback for AUTOBOT_JWT_SECRET / SECRET_KEY: a committed shared
# signing secret allows JWT/session forgery against any default deployment.
#
# Everything is written to a gitignored docker/.env.secrets that you then pass
# to compose. Idempotent: existing values are preserved, never overwritten or
# printed.
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
    # #14758: how the value is generated is per-key. The signing secrets are
    # opaque strings, but the envelope root key is base64-DECODED and must be
    # exactly 32 bytes, so `openssl rand -hex 32` (64 chars, decodes to 48) is
    # rejected by load_root_key. Default to hex, override where it matters.
    local generator="${2:-hex}"
    if grep -q "^${key}=" "$SECRETS_FILE" 2>/dev/null; then
        echo "  ${key}: already set — keeping existing value"
    else
        local value
        case "$generator" in
            b64_32) value="$(openssl rand -base64 32 | tr '+/' '-_')" ;;
            *)      value="$(openssl rand -hex 32)" ;;
        esac
        printf '%s=%s\n' "$key" "$value" >>"$SECRETS_FILE"
        echo "  ${key}: generated"
    fi
}

echo "Writing secrets to ${SECRETS_FILE}"
ensure_secret AUTOBOT_JWT_SECRET
ensure_secret SECRET_KEY
# The canonical envelope secret store is unreachable without this, and every
# consumer degrades silently, so its absence looked like "no such secret".
ensure_secret AUTOBOT_SECRETS_ROOT_KEY b64_32
# #16275: generated so a deployment need not keep the guessable template
# default. Hex, because the DB password is interpolated into SLM_DATABASE_URL
# and must need no URL escaping.
ensure_secret AUTOBOT_DB_PASSWORD
ensure_secret GRAFANA_ADMIN_PASSWORD

echo ""
echo "Done. Start the stack with both env files:"
echo "  docker compose --env-file docker/.env.docker --env-file docker/.env.secrets up -d"
