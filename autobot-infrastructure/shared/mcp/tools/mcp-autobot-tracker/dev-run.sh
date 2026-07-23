#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true

echo "Running AutoBot MCP Tracker in development mode..."
export NODE_ENV=development
export REDIS_HOST="${AUTOBOT_REDIS_HOST:-localhost}"
export REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
npm run dev
