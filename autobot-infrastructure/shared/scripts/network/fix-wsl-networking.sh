#!/bin/bash
# Fix WSL networking for AutoBot frontend-backend communication
# This script ensures proper port forwarding and network configuration

set -e

# Source centralized network configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/network-config.sh" 2>/dev/null || {
    # Fallback defaults if network-config.sh not available
    export BACKEND_PORT="${BACKEND_PORT:-8001}"
    export FRONTEND_PORT="${FRONTEND_PORT:-5173}"
}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 AutoBot WSL Networking Fix${NC}"
echo "=============================="

# Get current WSL IP
WSL_IP=$(hostname -I | awk '{print $1}')
echo -e "${BLUE}📍 Current WSL IP: ${WSL_IP}${NC}"

# Get Windows host IP (from WSL perspective)
WIN_HOST_IP=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}')
echo -e "${BLUE}📍 Windows Host IP: ${WIN_HOST_IP}${NC}"

# Test backend connectivity from WSL
echo -e "${YELLOW}🔍 Testing backend connectivity...${NC}"

if curl -s http://localhost:${BACKEND_PORT}/api/health >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend accessible via localhost:${BACKEND_PORT}${NC}"
else
    echo -e "${RED}❌ Backend not accessible via localhost:${BACKEND_PORT}${NC}"
    echo -e "${YELLOW}💡 Make sure backend is running with: python -m uvicorn backend.main:app --host 0.0.0.0 --port ${BACKEND_PORT}${NC}"
    exit 1
fi

if curl -s http://${WSL_IP}:${BACKEND_PORT}/api/health >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend accessible via WSL IP: ${WSL_IP}:${BACKEND_PORT}${NC}"
else
    echo -e "${RED}❌ Backend not accessible via WSL IP: ${WSL_IP}:${BACKEND_PORT}${NC}"
fi

# Check if Windows can access WSL backend (requires running from Windows)
echo -e "${YELLOW}🔍 Checking WSL port forwarding...${NC}"

# WSL2 should automatically forward ports, but let's verify
netstat -tlnp | grep ${BACKEND_PORT} && echo -e "${GREEN}✅ Port ${BACKEND_PORT} is listening${NC}"

# Update frontend configuration to use localhost
ENV_FILE="/home/kali/Desktop/AutoBot/autobot-slm-frontend/.env"
VITE_CONFIG="/home/kali/Desktop/AutoBot/autobot-slm-frontend/vite.config.ts"

echo -e "${YELLOW}🔧 Updating frontend configuration...${NC}"

# Backup files
cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
cp "$VITE_CONFIG" "$VITE_CONFIG.backup.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true

# Update .env to use localhost
sed -i 's/VITE_BACKEND_HOST=.*/VITE_BACKEND_HOST=localhost/' "$ENV_FILE"
sed -i 's|VITE_PLAYWRIGHT_VNC_URL=http://[^:]*:|VITE_PLAYWRIGHT_VNC_URL=http://localhost:|' "$ENV_FILE"
sed -i 's|VITE_OLLAMA_URL=http://[^:]*:|VITE_OLLAMA_URL=http://localhost:|' "$ENV_FILE"

echo -e "${GREEN}✅ Updated .env to use localhost${NC}"

# Update vite.config.ts defaults
sed -i "s/192\\.168\\.168\\.[0-9]\\+/localhost/g" "$VITE_CONFIG"
sed -i "s/host\\.docker\\.internal/localhost/g" "$VITE_CONFIG"

echo -e "${GREEN}✅ Updated vite.config.ts to use localhost${NC}"

# Check for any remaining hardcoded IPs in source files
echo -e "${YELLOW}🔍 Checking for hardcoded network references...${NC}"

HARDCODED_COUNT=$(find /home/kali/Desktop/AutoBot/autobot-slm-frontend/src -type f -name "*.ts" -o -name "*.js" -o -name "*.vue" | xargs grep -l "host\.docker\.internal\|192\.168\.168\." 2>/dev/null | wc -l)

if [ "$HARDCODED_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Found $HARDCODED_COUNT files with hardcoded network references:${NC}"
    find /home/kali/Desktop/AutoBot/autobot-slm-frontend/src -type f -name "*.ts" -o -name "*.js" -o -name "*.vue" | xargs grep -l "host\.docker\.internal\|192\.168\.168\." 2>/dev/null
    echo -e "${YELLOW}💡 These should be updated to use environment configuration${NC}"
else
    echo -e "${GREEN}✅ No hardcoded network references found${NC}"
fi

# Instructions
echo -e "${BLUE}📋 Next Steps:${NC}"
echo "1. Restart Vite dev server: cd autobot-slm-frontend && npm run dev"
echo "2. Access frontend from Windows browser at: http://localhost:${FRONTEND_PORT}"
echo "3. Frontend will proxy API calls to WSL backend via localhost:${BACKEND_PORT}"
echo ""
echo -e "${GREEN}✅ WSL networking configuration completed!${NC}"

# Show current configuration
echo -e "${BLUE}📋 Current Configuration:${NC}"
echo "Frontend: http://localhost:${FRONTEND_PORT} (Windows)"
echo "Backend:  http://localhost:${BACKEND_PORT} (WSL, auto-forwarded to Windows)"
echo "Proxy:    Frontend -> Windows localhost:${BACKEND_PORT} -> WSL localhost:${BACKEND_PORT}"
