#!/bin/sh
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Compose secrets-init (GH#9905): auto-provision per-deployment signing secrets
# so `docker compose up` works out of the box WITHOUT any committed secret.
#
# Generates AUTOBOT_JWT_SECRET / SECRET_KEY / AUTOBOT_SECRETS_ROOT_KEY ONCE into
# the shared `autobot_secrets` volume (mounted at /secrets) and reuses them on
# every subsequent start, so all services (backend, worker, slm) share one
# stable, unique-per-deployment value. The file is written as _GEN_* keys;
# with-secrets.sh applies them only when the corresponding env var is unset, so
# an explicit operator override still wins.
#
# Secrets live only in the named volume — never in git, never printed.
set -eu

SECRETS_FILE="/secrets/autobot.env"

# Busybox-friendly 64-hex-char (32-byte) generator. No openssl dependency.
gen_hex() {
    tr -dc 'a-f0-9' </dev/urandom | head -c 64
}

# #14758: the envelope secret store's root key is not interchangeable with the
# signing secrets above. `load_root_key` base64-decodes it and REQUIRES exactly
# 32 bytes, so a 64-hex-char value decodes to 48 and is rejected. Emit url-safe
# base64 of 32 random bytes instead.
gen_b64_32() {
    tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 | base64 | tr '+/' '-_' | tr -d '\n'
}

# Append one key only when it is absent. Per-key rather than all-or-nothing: an
# existing deployment already carrying _GEN_JWT/_GEN_SECRET_KEY must be able to
# GAIN the root key without its signing secrets being regenerated, which would
# invalidate every issued session and every envelope-encrypted secret.
ensure_key() {
    key="$1"
    gen="$2"
    if [ -f "$SECRETS_FILE" ] && grep -q "^${key}=" "$SECRETS_FILE" 2>/dev/null; then
        echo "secrets-init: ${key} already present — reusing."
        return 0
    fi
    printf '%s=%s\n' "$key" "$($gen)" >>"$SECRETS_FILE"
    echo "secrets-init: ${key} generated."
}

# Never world-readable, even momentarily: write under a restrictive umask, then
# grant access by OWNERSHIP to the autobot service user (uid/gid 999, pinned in
# both the backend and slm images) rather than by a permissive mode.
umask 077
touch "$SECRETS_FILE"
ensure_key _GEN_JWT gen_hex
ensure_key _GEN_SECRET_KEY gen_hex
ensure_key _GEN_SECRETS_ROOT_KEY gen_b64_32
chown 999:999 "$SECRETS_FILE"
chmod 640 "$SECRETS_FILE"
echo "secrets-init: done (values not printed)."
