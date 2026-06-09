#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Watchdog for the MV-Stealth-VM GitHub Actions runner.
#
# Detects the "ghost busy" condition — runner reports busy=true to GitHub but
# no job is actually running locally — and restarts the service to clear it.
#
# Run as a cron job or oneshot systemd timer (every 5–15 minutes):
#   */10 * * * * /opt/runner-watchdog/runner-watchdog.sh >> /var/log/runner-watchdog.log 2>&1
#
# Prerequisites:
#   - GH_TOKEN env var with repo scope (or set GITHUB_TOKEN)
#   - jq installed
#   - systemd service named actions.runner.<owner>-<repo>.<runner>.service
#   - sudo passwordless for: systemctl restart <service>

set -euo pipefail

REPO="${REPO:-mrveiss/AutoBot-AI}"
RUNNER_NAME="${RUNNER_NAME:-MV-Stealth-VM}"
SERVICE_NAME="${SERVICE_NAME:-actions.runner.mrveiss-AutoBot-AI.MV-Stealth-VM.service}"
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
LOG_PREFIX="[runner-watchdog $(date -u +%Y-%m-%dT%H:%M:%SZ)]"

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
