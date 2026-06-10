#!/bin/sh
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Compose secrets-init (GH#9905): auto-provision per-deployment signing secrets
# so `docker compose up` works out of the box WITHOUT any committed secret.
#
# Generates AUTOBOT_JWT_SECRET / SECRET_KEY ONCE into the shared `autobot_secrets`
# volume (mounted at /secrets) and reuses them on every subsequent start, so all
# services (backend, worker, slm) share one stable, unique-per-deployment secret.
# The file is written as _GEN_* keys; with-secrets.sh applies them only when the
# corresponding env var is unset, so an explicit operator override still wins.
#
# Secrets live only in the named volume — never in git, never printed.
set -eu

SECRETS_FILE="/secrets/autobot.env"

# Busybox-friendly 64-hex-char (32-byte) generator. No openssl dependency.
gen_hex() {
    tr -dc 'a-f0-9' </dev/urandom | head -c 64
}

if [ -f "$SECRETS_FILE" ] && grep -q '^_GEN_JWT=' "$SECRETS_FILE" 2>/dev/null \
    && grep -q '^_GEN_SECRET_KEY=' "$SECRETS_FILE" 2>/dev/null; then
    echo "secrets-init: existing secrets found in $SECRETS_FILE — reusing."
    exit 0
fi

echo "secrets-init: generating per-deployment signing secrets in $SECRETS_FILE"
{
    printf '_GEN_JWT=%s\n' "$(gen_hex)"
    printf '_GEN_SECRET_KEY=%s\n' "$(gen_hex)"
} >"$SECRETS_FILE"
# World-readable: the secret-consuming services (backend/worker/slm) run as the
# non-root `autobot` user and must read this file. The security boundary is the
# private named volume (never in git, not host-mounted), not the file mode —
# anything that can read this volume already runs inside the trusted stack.
chmod 644 "$SECRETS_FILE"
echo "secrets-init: done (values not printed)."
