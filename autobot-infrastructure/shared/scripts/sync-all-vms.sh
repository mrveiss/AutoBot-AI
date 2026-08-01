#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Sync code to all fleet VMs
# Fixed quote escaping and added missing components

set -e  # Exit on error

# Define components and their targets
declare -A SYNC_MAP
SYNC_MAP["${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/autobot-backend"]="${AUTOBOT_BACKEND_HOST:-localhost}:/opt/autobot/autobot-backend"
SYNC_MAP["${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/autobot-frontend"]="${AUTOBOT_FRONTEND_HOST:-localhost}:/opt/autobot/autobot-frontend"
SYNC_MAP["${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/autobot-slm-backend"]="${AUTOBOT_SLM_HOST:-localhost}:/opt/autobot/autobot-slm-backend"
SYNC_MAP["${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/autobot-slm-frontend"]="${AUTOBOT_SLM_HOST:-localhost}:/opt/autobot/autobot-slm-frontend"
SYNC_MAP["${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/autobot_shared"]="${AUTOBOT_SLM_HOST:-localhost},${AUTOBOT_BACKEND_HOST:-localhost},${AUTOBOT_FRONTEND_HOST:-localhost},${AUTOBOT_NPU_WORKER_HOST:-localhost},${AUTOBOT_REDIS_HOST:-localhost},${AUTOBOT_AI_STACK_HOST:-localhost},${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}:/opt/autobot/autobot_shared"
SYNC_MAP["${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/autobot-npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-localhost}:/opt/autobot/autobot-npu-worker"
SYNC_MAP["${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/autobot-browser-worker"]="${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}:/opt/autobot/autobot-browser-worker"

# Use array for rsync options to avoid quote escaping issues
RSYNC_OPTS=(
  -av
  --rsync-path="sudo rsync"
  --exclude="venv"
  --exclude="__pycache__"
  --exclude="*.pyc"
  --exclude=".git"
  --exclude="node_modules"
  --exclude="*.log"
)

echo "=== Syncing Code to All Fleet VMs ==="
echo ""

for src in "${!SYNC_MAP[@]}"; do
  targets="${SYNC_MAP[$src]}"
  IFS=',' read -ra DEST_ARRAY <<< "$targets"

  for dest in "${DEST_ARRAY[@]}"; do
    echo ">>> Syncing: $src -> autobot@$dest"
    if rsync "${RSYNC_OPTS[@]}" "$src/" "autobot@$dest/" 2>&1 | tail -10; then
      echo "✓ Done"
    else
      echo "✗ Failed"
    fi
    echo ""
  done
done

echo "=== Sync Complete ==="
