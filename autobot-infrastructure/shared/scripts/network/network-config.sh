#!/bin/bash
# AutoBot Network Configuration
# Centralized network configuration for all network-related scripts
# Uses environment variables with fallback to NetworkConstants defaults

# Load SSOT configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

# Backend API (Main Machine - WSL)
export BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
export BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"
export BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"

# Frontend (VM1)
export FRONTEND_HOST="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
export FRONTEND_PORT="${AUTOBOT_FRONTEND_PORT:-5173}"
export FRONTEND_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}"

# NPU Worker (VM2)
export NPU_WORKER_HOST="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
export NPU_WORKER_PORT="${AUTOBOT_NPU_WORKER_PORT:-8081}"
export NPU_WORKER_URL="http://${NPU_WORKER_HOST}:${NPU_WORKER_PORT}"

# Redis (VM3)
export REDIS_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
export REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"

# AI Stack (VM4)
export AI_STACK_HOST="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
export AI_STACK_PORT="${AUTOBOT_AI_STACK_PORT:-8080}"
export AI_STACK_URL="http://${AI_STACK_HOST}:${AI_STACK_PORT}"

# Browser Service (VM5)
export BROWSER_HOST="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
export BROWSER_PORT="${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"
export BROWSER_URL="http://${BROWSER_HOST}:${BROWSER_PORT}"

# VNC Services (Main Machine - WSL)
export VNC_WEB_HOST="${AUTOBOT_VNC_WEB_HOST:-172.16.168.20}"
export VNC_WEB_PORT="${AUTOBOT_VNC_WEB_PORT:-6080}"
export VNC_WEB_URL="http://${VNC_WEB_HOST}:${VNC_WEB_PORT}"

export VNC_SERVER_HOST="${AUTOBOT_VNC_SERVER_HOST:-localhost}"
export VNC_SERVER_PORT="${AUTOBOT_VNC_SERVER_PORT:-5902}"

# Log configuration loaded
echo "✅ Network configuration loaded:"
echo "   Backend:     ${BACKEND_URL}"
echo "   Frontend:    ${FRONTEND_URL}"
echo "   NPU Worker:  ${NPU_WORKER_URL}"
echo "   Redis:       ${REDIS_HOST}:${REDIS_PORT}"
echo "   AI Stack:    ${AI_STACK_URL}"
echo "   Browser:     ${BROWSER_URL}"
echo "   VNC Web:     ${VNC_WEB_URL}"
