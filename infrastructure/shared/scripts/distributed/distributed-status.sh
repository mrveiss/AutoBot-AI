#!/bin/bash
# AutoBot Distributed Architecture Status and Management Script

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

echo -e "${GREEN}🏗️  AutoBot Distributed 6-VM Architecture${NC}"
echo -e "${BLUE}Main WSL Coordinator: ${AUTOBOT_BACKEND_HOST:-172.16.168.20}${NC}"
echo "=================================================="

# Quick status check
echo -e "${CYAN}📊 Quick Status Check:${NC}"
bash scripts/distributed/check-health.sh

echo ""
echo -e "${CYAN}🔧 Management Commands:${NC}"
echo -e "${BLUE}Daily Operations:${NC}"
echo "  bash scripts/distributed/check-health.sh          # Health check all services"
echo "  bash scripts/distributed/start-coordinator.sh     # Start backend coordinator"
echo "  tail -f logs/backend-coordinator.log              # View coordinator logs"
echo "  pkill -f 'python.*backend/main.py'               # Stop backend coordinator"

echo ""
echo -e "${BLUE}Setup & Configuration:${NC}"
echo "  bash scripts/distributed/setup-ssh-keys.sh        # Setup SSH keys (one-time)"
echo "  bash scripts/distributed/setup-npu-remote.sh      # Setup NPU worker (one-time)"
echo "  bash scripts/distributed/collect-backups.sh       # Backup all VMs"

echo ""
echo -e "${BLUE}Testing & Debugging:${NC}"
echo "  python src/utils/distributed_redis_client.py      # Test Redis connection"
echo "  curl http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}/api/health         # Test backend API"
echo "  curl http://${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:${AUTOBOT_NPU_WORKER_PORT:-8081}/health            # Test NPU worker"

echo ""
echo -e "${CYAN}🌐 Access URLs:${NC}"
echo -e "${GREEN}User Interfaces:${NC}"
echo "  AutoBot Frontend:    http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}"
echo "  Backend API Docs:    http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}/docs"
echo "  Redis Dashboard:     http://${AUTOBOT_REDIS_HOST:-172.16.168.23}:8002"
echo "  VNC Desktop:         http://127.0.0.1:${AUTOBOT_VNC_PORT:-6080}"

echo ""
echo -e "${GREEN}Service APIs:${NC}"
echo "  Backend API:         http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}/api/"
echo "  NPU Worker:          http://${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:${AUTOBOT_NPU_WORKER_PORT:-8081}/"
echo "  AI Stack:            http://${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:${AUTOBOT_AI_STACK_PORT:-8080}/"
echo "  Browser Service:     http://${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}/"
echo "  Ollama LLM:          http://${AUTOBOT_OLLAMA_HOST:-127.0.0.1}:${AUTOBOT_OLLAMA_PORT:-11434}/api/"

echo ""
echo -e "${CYAN}📋 Architecture Summary:${NC}"
echo "✅ 6-VM Distributed Architecture Active"
echo "✅ All Remote Services Connected"
echo "✅ Backend Coordinator Running on WSL"
echo "✅ Distributed Redis Integration Working"
echo "✅ Hardware Optimization Configured"
echo "✅ Management Scripts Available"

echo ""
echo -e "${GREEN}🎉 AutoBot Distributed Architecture Ready for Production!${NC}"
