#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot Native VM - what the start, stop and status scripts share (#18557).
# Sourced, so a failure here stops them through their own `set -e`.

# Load SSOT configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../lib/ssot-config.sh" || {
    echo "FATAL: ${SCRIPT_DIR}/../lib/ssot-config.sh could not be sourced -- refusing to run on hardcoded config fallbacks (#14172)" >&2
    return 1 2>/dev/null || exit 1
}

# Load unified configuration system (legacy)
_NATIVE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." &> /dev/null && pwd)"
if [[ -f "${_NATIVE_SCRIPT_DIR}/config/load_config.sh" ]]; then
    export PATH="$HOME/bin:$PATH"  # Ensure yq is available
    source "${_NATIVE_SCRIPT_DIR}/config/load_config.sh"
    echo -e "\033[0;32m✓ Loaded unified configuration system\033[0m"
else
    echo -e "\033[0;31m✗ Warning: Unified configuration not found, using fallback values\033[0m"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# VM Configuration (from unified config, with SSOT fallback)
declare -A VMS
VMS[frontend]=$(get_config "infrastructure.hosts.frontend" 2>/dev/null || echo "${AUTOBOT_FRONTEND_HOST:-localhost}")
VMS[npu-worker]=$(get_config "infrastructure.hosts.npu_worker" 2>/dev/null || echo "${AUTOBOT_NPU_WORKER_HOST:-localhost}")
VMS[redis]=$(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "${AUTOBOT_REDIS_HOST:-localhost}")
VMS[ai-stack]=$(get_config "infrastructure.hosts.ai_stack" 2>/dev/null || echo "${AUTOBOT_AI_STACK_HOST:-localhost}")
VMS[browser]=$(get_config "infrastructure.hosts.browser_service" 2>/dev/null || echo "${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}")

# Service Configuration
declare -A SERVICES
SERVICES[frontend]="nginx"
SERVICES[npu-worker]="autobot-npu-worker.service"
SERVICES[redis]="redis-stack-server"
SERVICES[ai-stack]="autobot-ai-stack.service"
SERVICES[browser]="autobot-browser-service.service"

# Health Check URLs
declare -A HEALTH_URLS
HEALTH_URLS[frontend]="http://${AUTOBOT_FRONTEND_HOST:-localhost}/"
HEALTH_URLS[npu-worker]="http://${AUTOBOT_NPU_WORKER_HOST:-localhost}:${AUTOBOT_NPU_WORKER_PORT:-8081}/health"
HEALTH_URLS[redis]="${AUTOBOT_REDIS_HOST:-localhost}:${AUTOBOT_REDIS_PORT:-6379}"
HEALTH_URLS[ai-stack]="http://${AUTOBOT_AI_STACK_HOST:-localhost}:${AUTOBOT_AI_STACK_PORT:-8080}/health"
HEALTH_URLS[browser]="http://${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}:${AUTOBOT_BROWSER_SERVICE_PORT:-9001}/health"

SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${AUTOBOT_SSH_USER:-autobot}"
