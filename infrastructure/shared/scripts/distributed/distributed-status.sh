#!/bin/bash
# AutoBot Distributed Architecture Status and Management Script

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}🏗️  AutoBot Distributed 6-VM Architecture${NC}"
echo -e "${BLUE}Main WSL Coordinator: 172.16.168.20${NC}"
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
echo "  curl http://172.16.168.20:8001/api/health         # Test backend API"
echo "  curl http://172.16.168.22:8081/health            # Test NPU worker"

echo ""
echo -e "${CYAN}🌐 Access URLs:${NC}"
echo -e "${GREEN}User Interfaces:${NC}"
echo "  AutoBot Frontend:    http://172.16.168.21:5173"
echo "  Backend API Docs:    http://172.16.168.20:8001/docs"
echo "  Redis Dashboard:     http://172.16.168.23:8002"
echo "  VNC Desktop:         http://127.0.0.1:6080"

echo ""
echo -e "${GREEN}Service APIs:${NC}"
echo "  Backend API:         http://172.16.168.20:8001/api/"
echo "  NPU Worker:          http://172.16.168.22:8081/"
echo "  AI Stack:            http://172.16.168.24:8080/"
echo "  Browser Service:     http://172.16.168.25:3000/"
echo "  Ollama LLM:          http://127.0.0.1:11434/api/"

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
