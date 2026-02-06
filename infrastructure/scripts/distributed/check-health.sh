#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Check health of all distributed AutoBot services

# =============================================================================
# SSOT Configuration - Issue #694
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/ssot-config.sh" 2>/dev/null || source "$SCRIPT_DIR/lib/ssot-config.sh" 2>/dev/null || {
    # Fallback if lib not found
    PROJECT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
    [ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }
}

echo "AutoBot Distributed Services Health Check"
echo "============================================="

# Service configuration using SSOT variables
declare -A SERVICES=(
    ["Backend (Local)"]="127.0.0.1:${AUTOBOT_BACKEND_PORT:-8001}/api/health"
    ["Redis VM"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}:${AUTOBOT_REDIS_PORT:-6379}"
    ["NPU Worker VM"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:${AUTOBOT_NPU_WORKER_PORT:-8081}/health"
    ["Frontend VM"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}"
    ["AI Stack VM"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:${AUTOBOT_AI_STACK_PORT:-8080}/health"
    ["Browser VM"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}/health"
    ["Ollama (Local)"]="${AUTOBOT_OLLAMA_HOST:-127.0.0.1}:${AUTOBOT_OLLAMA_PORT:-11434}/api/tags"
)

for service_name in "${!SERVICES[@]}"; do
    endpoint="${SERVICES[$service_name]}"
    echo -n "Checking $service_name... "

    if [[ $endpoint == *":"*"/api/"* ]] || [[ $endpoint == *":"*"/health"* ]]; then
        # HTTP endpoint
        if curl -s --max-time 5 "http://$endpoint" >/dev/null 2>&1; then
            echo "OK"
        else
            echo "Failed"
        fi
    else
        # TCP port check
        IFS=':' read -r host port <<< "$endpoint"
        if nc -z -w3 "$host" "$port" 2>/dev/null; then
            echo "OK"
        else
            echo "Failed"
        fi
    fi
done

echo ""
echo "Service URLs:"
echo "  Backend API: http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}"
echo "  Frontend: http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}"
echo "  Redis Insight: http://${AUTOBOT_REDIS_HOST:-172.16.168.23}:8002"
echo "  AI Stack: http://${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:${AUTOBOT_AI_STACK_PORT:-8080}"
echo "  NPU Worker: http://${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:${AUTOBOT_NPU_WORKER_PORT:-8081}"
echo "  Browser Service: http://${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"
echo "  Ollama: http://${AUTOBOT_OLLAMA_HOST:-127.0.0.1}:${AUTOBOT_OLLAMA_PORT:-11434}"
echo "  VNC Desktop: http://${AUTOBOT_BACKEND_HOST:-127.0.0.1}:${AUTOBOT_VNC_PORT:-6080}"

echo ""
echo "Distributed Architecture Status:"
echo "  Main WSL (${AUTOBOT_BACKEND_HOST:-172.16.168.20}): Backend API + Ollama + VNC"
echo "  Frontend VM (${AUTOBOT_FRONTEND_HOST:-172.16.168.21}): Vue.js Web Interface"
echo "  NPU Worker VM (${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}): Intel OpenVINO + Hardware Acceleration"
echo "  Redis VM (${AUTOBOT_REDIS_HOST:-172.16.168.23}): Redis Stack + Vector Storage"
echo "  AI Stack VM (${AUTOBOT_AI_STACK_HOST:-172.16.168.24}): AI Processing Services"
echo "  Browser VM (${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}): Playwright Automation"

echo ""
echo "Testing Distributed Redis Connection:"
cd "${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
if python src/utils/distributed_redis_client.py 2>/dev/null | grep -q "connection working correctly"; then
    echo "  Redis Connection: OK"
else
    echo "  Redis Connection: Failed"
fi
