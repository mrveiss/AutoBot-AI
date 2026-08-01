#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Start AutoBot Backend Coordinator for Distributed 6-VM Architecture
# This script runs on the main WSL machine (${AUTOBOT_BACKEND_HOST}) as the coordinator

set -e

# Load SSOT configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}🚀 Starting AutoBot Backend Coordinator${NC}"
echo -e "${BLUE}Coordinator Node: ${AUTOBOT_BACKEND_HOST:-localhost}${NC}"
echo -e "${CYAN}Architecture: 6-VM Distributed System${NC}"
echo ""

# Change to AutoBot directory
cd ${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}

# Load environment variables for distributed mode
echo -e "${CYAN}📋 Loading distributed environment configuration...${NC}"
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
    echo "✅ Environment loaded from .env"
else
    echo -e "${YELLOW}⚠️  .env file not found, using defaults${NC}"
fi

# Set distributed mode environment variables (SSOT provides defaults)
export AUTOBOT_DEPLOYMENT_MODE=distributed
export AUTOBOT_BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-localhost}"
export AUTOBOT_REDIS_HOST="${AUTOBOT_REDIS_HOST:-localhost}"
export AUTOBOT_FRONTEND_HOST="${AUTOBOT_FRONTEND_HOST:-localhost}"
export AUTOBOT_AI_STACK_HOST="${AUTOBOT_AI_STACK_HOST:-localhost}"
export AUTOBOT_NPU_WORKER_HOST="${AUTOBOT_NPU_WORKER_HOST:-localhost}"
export AUTOBOT_BROWSER_SERVICE_HOST="${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}"

echo -e "${CYAN}🔧 Distributed Configuration:${NC}"
echo "  Backend Coordinator: ${AUTOBOT_BACKEND_HOST}:${AUTOBOT_BACKEND_PORT:-8001}"
echo "  Redis VM: ${AUTOBOT_REDIS_HOST}:${AUTOBOT_REDIS_PORT:-6379}"
echo "  Frontend VM: ${AUTOBOT_FRONTEND_HOST}:${AUTOBOT_FRONTEND_PORT:-5173}"
echo "  NPU Worker VM: ${AUTOBOT_NPU_WORKER_HOST}:${AUTOBOT_NPU_WORKER_PORT:-8081}"
echo "  AI Stack VM: ${AUTOBOT_AI_STACK_HOST}:${AUTOBOT_AI_STACK_PORT:-8080}"
echo "  Browser VM: ${AUTOBOT_BROWSER_SERVICE_HOST}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"

# Test connectivity to remote VMs
echo ""
echo -e "${CYAN}📡 Testing distributed services connectivity...${NC}"

# Test Redis VM
if nc -z -w3 ${AUTOBOT_REDIS_HOST} ${AUTOBOT_REDIS_PORT:-6379}; then
    echo -e "  Redis VM: ${GREEN}✅ Connected${NC}"
else
    echo -e "  Redis VM: ${RED}❌ Failed${NC}"
    exit 1
fi

# Test other VMs
VMS_TO_TEST=(
    "Frontend:${AUTOBOT_FRONTEND_HOST}:${AUTOBOT_FRONTEND_PORT:-5173}"
    "NPU Worker:${AUTOBOT_NPU_WORKER_HOST}:${AUTOBOT_NPU_WORKER_PORT:-8081}"
    "AI Stack:${AUTOBOT_AI_STACK_HOST}:${AUTOBOT_AI_STACK_PORT:-8080}"
    "Browser:${AUTOBOT_BROWSER_SERVICE_HOST}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"
)

for vm_test in "${VMS_TO_TEST[@]}"; do
    IFS=':' read -r name host port <<< "$vm_test"
    if nc -z -w3 "$host" "$port"; then
        echo -e "  $name VM: ${GREEN}✅ Connected${NC}"
    else
        echo -e "  $name VM: ${YELLOW}⚠️  Not accessible${NC}"
    fi
done

# Test local Ollama
echo -n "  Ollama (Local): "
if nc -z -w3 "${AUTOBOT_OLLAMA_HOST:-127.0.0.1}" "${AUTOBOT_OLLAMA_PORT:-11434}"; then
    echo -e "${GREEN}✅ Connected${NC}"
else
    echo -e "${YELLOW}⚠️  Not running${NC}"
    echo "    Starting Ollama in background..."
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
fi

echo ""
echo -e "${CYAN}🧪 Testing distributed Redis connection...${NC}"
if python src/utils/distributed_redis_client.py > /tmp/redis_test.log 2>&1; then
    echo -e "${GREEN}✅ Distributed Redis connection successful${NC}"
else
    echo -e "${YELLOW}⚠️  Redis connection test failed${NC}"
    echo "Check /tmp/redis_test.log for details"
fi

echo ""
echo -e "${CYAN}🔥 Starting Backend Coordinator...${NC}"

# Kill any existing backend process
if pgrep -f "python.*backend/main.py" > /dev/null; then
    echo "Stopping existing backend process..."
    pkill -f "python.*backend/main.py"
    sleep 2
fi

# Set Python path
export PYTHONPATH="${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}:$PYTHONPATH"

# Start backend with distributed configuration
echo "Starting FastAPI backend coordinator..."
cd backend

# Start backend in background with logging
nohup python main.py > ../logs/backend-coordinator.log 2>&1 &

BACKEND_PID=$!
echo "Backend coordinator started with PID: $BACKEND_PID"

# Wait for backend to start
echo "Waiting for backend to initialize..."
for i in {1..30}; do
    if curl -s "http://${AUTOBOT_BACKEND_HOST}:${AUTOBOT_BACKEND_PORT:-8001}/api/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend coordinator is running and healthy!${NC}"
        break
    fi

    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Backend failed to start within 30 seconds${NC}"
        echo "Check logs at: logs/backend-coordinator.log"
        exit 1
    fi

    echo -n "."
    sleep 1
done

echo ""
echo -e "${GREEN}🎉 AutoBot Distributed Architecture Started Successfully!${NC}"
echo ""
echo -e "${CYAN}📊 Access Points:${NC}"
echo "  Backend API: http://${AUTOBOT_BACKEND_HOST}:${AUTOBOT_BACKEND_PORT:-8001}"
echo "  Frontend: http://${AUTOBOT_FRONTEND_HOST}:${AUTOBOT_FRONTEND_PORT:-5173}"
echo "  Redis Insight: http://${AUTOBOT_REDIS_HOST}:8002"
echo "  NPU Worker: http://${AUTOBOT_NPU_WORKER_HOST}:${AUTOBOT_NPU_WORKER_PORT:-8081}"
echo "  AI Stack: http://${AUTOBOT_AI_STACK_HOST}:${AUTOBOT_AI_STACK_PORT:-8080}"
echo "  Browser Service: http://${AUTOBOT_BROWSER_SERVICE_HOST}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"
echo "  Ollama: http://${AUTOBOT_OLLAMA_HOST:-127.0.0.1}:${AUTOBOT_OLLAMA_PORT:-11434}"
echo "  VNC Desktop: http://127.0.0.1:${AUTOBOT_VNC_PORT:-6080}"
echo ""
echo -e "${CYAN}📋 Management Commands:${NC}"
echo "  Health Check: bash scripts/distributed/check-health.sh"
echo "  View Logs: tail -f logs/backend-coordinator.log"
echo "  Stop Backend: pkill -f 'python.*backend/main.py'"
echo ""
echo -e "${BLUE}Backend coordinator is now running in distributed mode!${NC}"
