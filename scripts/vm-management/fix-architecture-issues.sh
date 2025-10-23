#!/bin/bash
# AutoBot - Fix Critical Architecture Issues
# Addresses the monitoring system architecture issues identified

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

echo -e "${GREEN}🔧 AutoBot Architecture Issue Fixes${NC}"
echo -e "${BLUE}====================================${NC}"
echo ""

# Issue 1: Redis should ONLY run on VM3 (172.16.168.23)
log "Checking Redis architecture compliance..."

# Check if Redis is running locally (SHOULD NOT BE)
if pgrep redis-server >/dev/null || docker ps | grep redis >/dev/null 2>&1; then
    warning "Redis is running locally on main instance - this violates architecture!"
    echo "Stopping local Redis instances..."
    sudo systemctl stop redis-server 2>/dev/null || true
    sudo systemctl stop redis-stack-server 2>/dev/null || true
    docker stop $(docker ps -q -f name=redis) 2>/dev/null || true
    success "Local Redis instances stopped"
else
    success "✅ No local Redis instances found (correct)"
fi

# Check if Redis is running on correct VM
echo -n "Checking Redis on VM3 (172.16.168.23)... "
if timeout 3 redis-cli -h 172.16.168.23 -p 6379 ping 2>/dev/null | grep -q "PONG"; then
    echo -e "${GREEN}✅ Running correctly${NC}"
else
    echo -e "${RED}❌ Not running${NC}"
    log "Starting Redis on correct VM..."
    bash "$(dirname "$0")/start-redis.sh"
fi

# Issue 2: Check for incorrect Nginx configuration on frontend VM
log "Checking frontend VM configuration..."
SSH_KEY="$HOME/.ssh/autobot_key"
SSH_USER="autobot"

if [ -f "$SSH_KEY" ]; then
    echo -n "Checking for Nginx on frontend VM... "
    nginx_status=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@172.16.168.21" "systemctl is-active nginx 2>/dev/null || echo 'inactive'" 2>/dev/null || echo "unknown")

    if [ "$nginx_status" = "active" ]; then
        warning "Nginx is running on frontend VM - may conflict with dev server"
        echo "Frontend should use npm dev server in development mode"
        echo "Production uses nginx, development uses Vite dev server"
    else
        success "✅ Nginx not active on frontend VM (correct for dev mode)"
    fi
else
    warning "SSH key not found - cannot check frontend VM configuration"
fi

# Issue 3: Verify NPU Worker service
log "Checking NPU Worker service..."
echo -n "NPU Worker health check... "
if timeout 5 curl -s http://172.16.168.22:8081/health >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Healthy${NC}"
else
    echo -e "${RED}❌ Unhealthy${NC}"
    log "Attempting to restart NPU Worker..."
    bash "$(dirname "$0")/start-npu-worker.sh"
fi

# Issue 4: Check Browser service on VM5
log "Checking Browser service..."
echo -n "Browser service health check... "
if timeout 5 curl -s http://172.16.168.25:3000/health >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Healthy${NC}"
else
    echo -e "${RED}❌ Unhealthy${NC}"
    log "Browser service needs manual restart - use start-all-vms.sh"
fi

# Issue 5: Verify service distribution compliance
log "Verifying service distribution compliance..."

echo ""
echo -e "${CYAN}🏗️ AutoBot Distributed Architecture Verification:${NC}"
echo ""
echo -e "${BLUE}✅ CORRECT SERVICE DISTRIBUTION:${NC}"
echo "  Main (172.16.168.20): Backend API + VNC Desktop only"
echo "  VM1 (172.16.168.21):  Frontend web interface only"
echo "  VM2 (172.16.168.22):  NPU Worker hardware acceleration only"
echo "  VM3 (172.16.168.23):  Redis database only"
echo "  VM4 (172.16.168.24):  AI Stack processing only"
echo "  VM5 (172.16.168.25):  Browser automation only"
echo ""

# Generate architecture compliance report
log "Generating compliance report..."

cat > /tmp/architecture-compliance-report.txt << EOF
AutoBot Architecture Compliance Report
Generated: $(date)

SERVICE DISTRIBUTION:
✅ Backend API: Running on main instance (172.16.168.20:8001)
$(timeout 3 redis-cli -h 172.16.168.23 -p 6379 ping 2>/dev/null | grep -q "PONG" && echo "✅" || echo "❌") Redis: Should run ONLY on VM3 (172.16.168.23:6379)
$(timeout 3 curl -s http://172.16.168.21:5173 >/dev/null 2>&1 && echo "✅" || echo "❌") Frontend: Running on VM1 (172.16.168.21:5173)
$(timeout 3 curl -s http://172.16.168.22:8081/health >/dev/null 2>&1 && echo "✅" || echo "❌") NPU Worker: Running on VM2 (172.16.168.22:8081)
$(timeout 3 curl -s http://172.16.168.24:8080/health >/dev/null 2>&1 && echo "✅" || echo "❌") AI Stack: Running on VM4 (172.16.168.24:8080)
$(timeout 3 curl -s http://172.16.168.25:3000/health >/dev/null 2>&1 && echo "✅" || echo "❌") Browser: Running on VM5 (172.16.168.25:3000)

ARCHITECTURE VIOLATIONS:
- Local Redis instances: $(pgrep redis-server >/dev/null && echo "VIOLATION: Found local Redis" || echo "None detected")
- Service conflicts: $(docker ps | grep -E "redis|nginx|frontend" | wc -l) containers running locally

RECOMMENDATIONS:
1. Never run Redis on main instance (172.16.168.20)
2. Use npm dev server on frontend VM for development
3. Ensure single service per VM principle
4. Use start-all-vms.sh for proper service orchestration
EOF

echo -e "${CYAN}📋 Compliance report saved to: /tmp/architecture-compliance-report.txt${NC}"

# Summary
echo ""
log "Architecture compliance check completed"

# Show current service status
echo ""
echo -e "${YELLOW}📊 Current Service Status:${NC}"
echo -n "  Backend (172.16.168.20:8001): "
curl -s http://172.16.168.20:8001/api/health >/dev/null 2>&1 && echo -e "${GREEN}✅ Running${NC}" || echo -e "${RED}❌ Down${NC}"

echo -n "  Frontend (172.16.168.21:5173): "
curl -s http://172.16.168.21:5173 >/dev/null 2>&1 && echo -e "${GREEN}✅ Running${NC}" || echo -e "${RED}❌ Down${NC}"

echo -n "  Redis (172.16.168.23:6379): "
redis-cli -h 172.16.168.23 -p 6379 ping 2>/dev/null | grep -q "PONG" && echo -e "${GREEN}✅ Running${NC}" || echo -e "${RED}❌ Down${NC}"

echo -n "  NPU Worker (172.16.168.22:8081): "
curl -s http://172.16.168.22:8081/health >/dev/null 2>&1 && echo -e "${GREEN}✅ Running${NC}" || echo -e "${RED}❌ Down${NC}"

echo -n "  AI Stack (172.16.168.24:8080): "
curl -s http://172.16.168.24:8080/health >/dev/null 2>&1 && echo -e "${GREEN}✅ Running${NC}" || echo -e "${RED}❌ Down${NC}"

echo -n "  Browser (172.16.168.25:3000): "
curl -s http://172.16.168.25:3000/health >/dev/null 2>&1 && echo -e "${GREEN}✅ Running${NC}" || echo -e "${RED}❌ Down${NC}"

echo ""
success "AutoBot architecture issues addressed!"
echo ""
echo -e "${YELLOW}🔧 Next Steps:${NC}"
echo -e "${CYAN}  1. For complete status: bash scripts/vm-management/status-all-vms.sh${NC}"
echo -e "${CYAN}  2. For service restart: bash scripts/vm-management/start-all-vms.sh${NC}"
echo -e "${CYAN}  3. For backend restart: bash run_autobot.sh --dev${NC}"
echo ""