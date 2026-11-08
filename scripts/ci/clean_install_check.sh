#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# After a clean install, prove the SLM is usable (#19403): health answers, the admin logs in
# with the password the installer stored, and this host is registered as a node. Each failure
# names its step. Run as root (the secrets file is root:autobot 0640).
#
#   SLM_URL=<base url> [EXPECT_PASSWORD_FILE=<file>] clean_install_check.sh
#
# EXPECT_PASSWORD_FILE (the tty run) holds the password typed at the prompt; the stored one
# must match it, which proves the prompt's answer was used rather than an auto-generated one.
set -euo pipefail

: "${SLM_URL:?SLM_URL is required}"
readonly SECRETS_FILE="/etc/autobot/slm-secrets.env"

fail() { echo "::error title=clean install: step '$1' failed::$2"; exit 1; }

step_health() {
    local i
    for i in $(seq 1 30); do
        curl -sfk --max-time 5 "${SLM_URL}/slm/api/health" >/dev/null && { echo "health: ok"; return; }
        sleep 5
    done
    fail health "${SLM_URL}/slm/api/health did not answer within 150s"
}

stored_password() {
    grep -oP '^SLM_ADMIN_PASSWORD=\K.*' "${SECRETS_FILE}" || fail login "no SLM_ADMIN_PASSWORD in ${SECRETS_FILE}"
}

step_login() {
    local pw
    pw=$(stored_password)
    echo "::add-mask::${pw}"
    if [[ -n "${EXPECT_PASSWORD_FILE:-}" ]] && [[ "${pw}" != "$(cat "${EXPECT_PASSWORD_FILE}")" ]]; then
        fail login "the stored password is not the one typed at the prompt"
    fi
    TOKEN=$(PW="${pw}" jq -n '{username: "admin", password: env.PW}' \
        | curl -sfk --max-time 10 -X POST "${SLM_URL}/slm/api/auth/login" \
            -H "Content-Type: application/json" --data @- | jq -r '.access_token // empty') || true
    [[ -n "${TOKEN}" ]] || fail login "admin login with the stored password returned no token"
    echo "::add-mask::${TOKEN}"
    echo "login: ok"
}

step_node() {
    local host nodes
    host=$(hostname)
    nodes=$(curl -sfk --max-time 10 -H "Authorization: Bearer ${TOKEN}" "${SLM_URL}/slm/api/nodes") \
        || fail node "GET /slm/api/nodes failed"
    HOST="${host}" jq -e '.nodes | any(.hostname == env.HOST)' <<<"${nodes}" >/dev/null \
        || fail node "this host (${host}) is not registered; nodes: $(jq -c '[.nodes[].hostname]' <<<"${nodes}")"
    echo "node: ok (${host})"
}

step_health
step_login
step_node
