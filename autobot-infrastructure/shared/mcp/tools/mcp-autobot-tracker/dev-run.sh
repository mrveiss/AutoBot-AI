#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
# shellcheck source=/dev/null
source "$_PROJECT_ROOT/autobot-infrastructure/shared/scripts/lib/ssot-config.sh" || {
    echo "FATAL: $_PROJECT_ROOT/autobot-infrastructure/shared/scripts/lib/ssot-config.sh could not be sourced -- refusing to run on hardcoded config fallbacks (#14172)" >&2
    return 1 2>/dev/null || exit 1
}

echo "Running AutoBot MCP Tracker in development mode..."
export NODE_ENV=development
export REDIS_HOST="${AUTOBOT_REDIS_HOST:-localhost}"
export REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
npm run dev
