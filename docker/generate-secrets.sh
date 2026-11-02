#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Generate per-deployment secrets and the management network range (#16833) for
# the docker-compose stack (GH#9775, #16275).
#
# PASSWORDS (#16275, #17793): this writes every credential compose requires --
# AUTOBOT_DB_PASSWORD, GRAFANA_ADMIN_PASSWORD, AUTOBOT_ADMIN_PASSWORD and
# SLM_ADMIN_PASSWORD (and VNC_PASSWORD for the playwright-vnc stack). Compose has no fallback for any of them and refuses to
# start, naming the variable, when one is missing. Pass docker/.env.secrets AFTER
# docker/.env.docker, as shown below, so the generated values win.
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

# #19864: decided before the file is created, for the encryption key below. An empty file is
# still new: a run refused by the volume check below has already created it.
NEW_INSTALL=true
[ -s "$SECRETS_FILE" ] && NEW_INSTALL=false

# Created owner-only from the first byte, not chmod-ed after a world-readable moment.
(umask 077 && touch "$SECRETS_FILE")
chmod 600 "$SECRETS_FILE"

# #17793: an existing Postgres volume keeps the password it was created with and ignores a new
# one. Generating AUTOBOT_DB_PASSWORD for it would lock the stack out of its own database, so
# when the key is missing, refuse -- before anything is written -- if that volume exists, AND if
# docker cannot be asked: not knowing is treated as "it may exist" (fail closed).
# The project name is COMPOSE_PROJECT_NAME or this checkout's directory name, the compose
# defaults. A stack started with `docker compose -p NAME` (or a project name set elsewhere)
# needs COMPOSE_PROJECT_NAME=NAME exported for this check to find its volume.
postgres_volume_state() {  # prints the volume name; 0 = exists, 1 = absent, 2 = cannot tell
    local project="${COMPOSE_PROJECT_NAME:-$(basename "$(cd "$(dirname "$0")/.." && pwd)")}" names
    project="$(printf '%s' "$project" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
    printf '%s_postgres_data' "$project"
    names="$(docker volume ls --format '{{.Name}}' 2>/dev/null)" || return 2
    grep -qx "${project}_postgres_data" <<<"${names}" || return 1
}
if ! grep -q '^AUTOBOT_DB_PASSWORD=' "$SECRETS_FILE"; then
    state=0; volume="$(postgres_volume_state)" || state=$?
    if [[ ${state} -ne 1 ]]; then
        if [[ ${state} -eq 0 ]]; then
            echo "ERROR: ${SECRETS_FILE} has no AUTOBOT_DB_PASSWORD, but the Postgres volume ${volume} exists." >&2
        else
            echo "ERROR: ${SECRETS_FILE} has no AUTOBOT_DB_PASSWORD, and docker cannot be asked whether the" >&2
            echo "  Postgres volume ${volume} exists (is docker installed and running, and may this user use it?)." >&2
        fi
        echo "  Postgres keeps the password a volume was created with; a new one would lock the stack out." >&2
        echo "  Add the password this deployment already uses (a stack started from the old tracked" >&2
        echo "  default used 'autobot') as AUTOBOT_DB_PASSWORD=... to ${SECRETS_FILE}, then rerun." >&2
        echo "  On a new host, start docker first so this check can see there is no volume yet." >&2
        exit 1
    fi
fi

gen_password() {  # 32 URL-safe chars meeting the user schema's policy: upper, lower and a digit
    local value=""
    until [[ "${value}" =~ [A-Z] && "${value}" =~ [a-z] && "${value}" =~ [0-9] ]]; do
        value="$(openssl rand -base64 24 | tr -d '+/=\n')"
    done
    printf '%s' "${value}"
}

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
            password) value="$(gen_password)" ;;
            *)      value="$(openssl rand -hex 32)" ;;
        esac
        printf '%s=%s\n' "$key" "$value" >>"$SECRETS_FILE"
        echo "  ${key}: generated"
    fi
}

echo "Writing secrets to ${SECRETS_FILE}"
# #19864: new installs only. Losing this key makes everything encrypted with it unreadable, so an
# existing deployment opts in by setting it here rather than having a re-run switch it on.
# First of all: a run stopped part-way leaves a non-empty file, which reads as existing on the rerun.
if [ "$NEW_INSTALL" = true ]; then
    ensure_secret AUTOBOT_ENCRYPTION_KEY
fi
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
# #18729: the main app seeds its first admin from this on first start; without it a
# fresh Docker install has no account to log in with. Read it back from this file.
ensure_secret AUTOBOT_ADMIN_PASSWORD password
# #17793: the SLM's first admin; compose no longer falls back to 'admin' and refuses to start without it.
ensure_secret SLM_ADMIN_PASSWORD password
# #17500: the playwright-vnc dev stack's VNC password; it no longer falls back to a fixed one.
ensure_secret VNC_PASSWORD

# #16833: the compose management network has no default range -- a fixed one took
# over the host's route on a LAN using the same /24. Pick a free private /24 once
# and keep it: changing it later re-addresses every container. A value already in
# the environment wins (e.g. AUTOBOT_DOCKER_MGMT_PREFIX=10.77.3).
if grep -q '^AUTOBOT_DOCKER_MGMT_PREFIX=' "$SECRETS_FILE"; then
    echo "  AUTOBOT_DOCKER_MGMT_PREFIX: already set — keeping existing value"
else
    prefix="${AUTOBOT_DOCKER_MGMT_PREFIX:-$(python3 "$(dirname "$0")/pick_mgmt_prefix.py")}"
    if ! [[ "$prefix" =~ ^(25[0-5]|2[0-4][0-9]|1?[0-9]?[0-9])(\.(25[0-5]|2[0-4][0-9]|1?[0-9]?[0-9])){2}$ ]]; then
        echo "ERROR: AUTOBOT_DOCKER_MGMT_PREFIX must be three octets, e.g. 10.77.3 (got '${prefix}')" >&2
        exit 1
    fi
    printf 'AUTOBOT_DOCKER_MGMT_PREFIX=%s\n' "$prefix" >>"$SECRETS_FILE"
    echo "  AUTOBOT_DOCKER_MGMT_PREFIX: ${prefix} (management network ${prefix}.0/24)"
fi

echo ""
echo "Main-app login: user 'admin', password = the AUTOBOT_ADMIN_PASSWORD line in ${SECRETS_FILE}"
echo "  (the value is not printed here; read it with: grep '^AUTOBOT_ADMIN_PASSWORD=' ${SECRETS_FILE})"
echo ""
echo "Done. Start the stack with both env files:"
echo "  docker compose --env-file docker/.env.docker --env-file docker/.env.secrets up -d"
