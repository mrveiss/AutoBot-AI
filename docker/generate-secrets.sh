#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Generate per-deployment signing secrets for the docker-compose stack (GH#9775).
#
# OPTIONAL since GH#9905: the compose stack auto-generates unique secrets on the
# first `up` (autobot-secrets-init + shared autobot_secrets volume), so
# `docker compose up` works with no manual step. Use this script only to PIN
# explicit secrets (share one across hosts, or manage them yourself) — an
# explicit value always overrides the auto-generated one.
#
# The compose file ships no static fallback values for AUTOBOT_JWT_SECRET /
# SECRET_KEY — a committed shared signing secret allows JWT/session forgery
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

echo "Writing signing secrets to ${SECRETS_FILE}"
ensure_secret AUTOBOT_JWT_SECRET
ensure_secret SECRET_KEY
# The canonical envelope secret store is unreachable without this, and every
# consumer degrades silently, so its absence looked like "no such secret".
ensure_secret AUTOBOT_SECRETS_ROOT_KEY b64_32

echo ""
echo "Done. Start the stack with both env files:"
echo "  docker compose --env-file docker/.env.docker --env-file docker/.env.secrets up -d"
