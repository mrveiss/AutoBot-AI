#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Watchdog for a GitHub Actions self-hosted runner.
#
# Detects the "ghost busy" condition — runner reports busy=true to GitHub but
# no job is actually running locally — and restarts the service to clear it.
#
# #15309: this must run ON THE HOST THAT ACTUALLY HOSTS THE RUNNER — the
# service restart below is local (`sudo systemctl restart`), so scheduling
# this from any other machine cannot work. RUNNER_NAME and SERVICE_NAME are
# REQUIRED (no default): the original defaults pointed at a runner
# ("MV-Stealth-VM") that was later decommissioned, and the script kept
# "working" — silently targeting nothing — for months. A missing required
# value now fails loudly instead of quietly matching the wrong runner.
#
# Install as a systemd instance timer, one instance per runner, using the
# tracked templates in scripts/systemd/ (see docs/developer/RUNNER_WATCHDOG.md for
# the full install sequence and the per-runner inventory):
#   scripts/systemd/runner-watchdog@.service
#   scripts/systemd/runner-watchdog@.timer
#
# Prerequisites:
#   - GH_TOKEN env var with repo scope (or set GITHUB_TOKEN)
#   - RUNNER_NAME and SERVICE_NAME env vars, set to THIS host's own runner
#   - jq installed
#   - systemd service named actions.runner.<owner>-<repo>.<runner>.service
#   - sudo passwordless for: systemctl restart <service>
#   - a log path the invoking (non-root) user can write — NOT /var/log,
#     which is root:syslog on these hosts and silently drops the redirect
#     before the script ever runs (#15309 fault #1)

set -euo pipefail

REPO="${REPO:-mrveiss/AutoBot-AI}"
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
LOG_PREFIX="[runner-watchdog $(date -u +%Y-%m-%dT%H:%M:%SZ)]"

if [[ -z "${RUNNER_NAME:-}" ]]; then
  echo "$LOG_PREFIX ERROR: RUNNER_NAME not set. This must be THIS host's own runner name" \
    "(gh api repos/${REPO}/actions/runners) — no default, so a stale or wrong value" \
    "cannot silently target a decommissioned runner (#15309)." >&2
  exit 1
fi

if [[ -z "${SERVICE_NAME:-}" ]]; then
  echo "$LOG_PREFIX ERROR: SERVICE_NAME not set. Expected" \
    "actions.runner.<owner>-<repo-with-dashes>.${RUNNER_NAME}.service for THIS host's runner." >&2
  exit 1
fi

if [[ -z "$TOKEN" ]]; then
  echo "$LOG_PREFIX ERROR: GH_TOKEN or GITHUB_TOKEN not set; cannot query runner state" >&2
  exit 1
fi

# Fetch runner state from GitHub
RUNNER_JSON=$(curl -fsSL \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${REPO}/actions/runners")

BUSY=$(echo "$RUNNER_JSON" | jq -r --arg name "$RUNNER_NAME" \
  '.runners[] | select(.name==$name) | .busy')
RUNNER_STATUS=$(echo "$RUNNER_JSON" | jq -r --arg name "$RUNNER_NAME" \
  '.runners[] | select(.name==$name) | .status')

if [[ -z "$BUSY" || -z "$RUNNER_STATUS" ]]; then
  echo "$LOG_PREFIX ERROR: runner '$RUNNER_NAME' not found in API response" >&2
  exit 1
fi

echo "$LOG_PREFIX runner=$RUNNER_NAME status=$RUNNER_STATUS busy=$BUSY"

if [[ "$BUSY" == "true" ]]; then
  # Check whether a job process is actually running locally
  RUNNER_PID_COUNT=$(pgrep -c -f "Runner.Worker" 2>/dev/null || echo "0")
  if [[ "$RUNNER_PID_COUNT" -eq 0 ]]; then
    echo "$LOG_PREFIX GHOST BUSY detected (busy=true, no Runner.Worker process). Restarting service."
    sudo systemctl restart "$SERVICE_NAME"
    echo "$LOG_PREFIX Service restarted."
  else
    echo "$LOG_PREFIX Runner is genuinely busy ($RUNNER_PID_COUNT worker process(es)). No action."
  fi
else
  echo "$LOG_PREFIX Runner is healthy (busy=false). No action."
fi
