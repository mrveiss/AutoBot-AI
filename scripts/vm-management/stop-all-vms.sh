#!/bin/bash
# AutoBot - Stop All VM Services
# Stops all distributed VM services gracefully

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# VM Configuration
SSH_KEY="$HOME/.ssh/autobot_key"
SSH_USER="autobot"
declare -A VMS=(
    ["frontend"]="172.16.168.21"
    ["npu-worker"]="172.16.168.22"
    ["redis"]="172.16.168.23"
    ["ai-stack"]="172.16.168.24"
    ["browser"]="172.16.168.25"
)

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

stop_frontend_vm() {
    log "Stopping Frontend service on VM (172.16.168.21)..."
    
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.21" << 'EOF' || true
        # Stop frontend processes
        pkill -f "npm.*dev" || true
        pkill -f "node.*vite" || true
        
        echo "Frontend service stopped"
EOF
    
    success "Frontend VM service stopped"
}

stop_npu_worker_vm() {
    log "Stopping NPU Worker service on VM (172.16.168.22)..."
    
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.22" << 'EOF' || true
        # Stop NPU worker processes
        pkill -f "npu.*worker" || true
        pkill -f "python.*8081" || true
        
        echo "NPU Worker service stopped"
EOF
    
    success "NPU Worker VM service stopped"
}

stop_redis_vm() {
    log "Stopping Redis service on VM (172.16.168.23)..."
    
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.23" << 'EOF' || true
        # Stop Redis Stack service
        if systemctl is-active redis-stack-server >/dev/null 2>&1; then
            echo "Stopping Redis Stack service..."
            sudo systemctl stop redis-stack-server
        fi
        
        # Stop any standalone Redis processes
        sudo pkill redis-server 2>/dev/null || true
        
        echo "Redis service stopped"
EOF
    
    success "Redis VM service stopped"
}

stop_ai_stack_vm() {
    log "Stopping AI Stack service on VM (172.16.168.24)..."
    
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.24" << 'EOF' || true
        # Stop AI stack processes
        pkill -f "ai.*stack" || true
        pkill -f "python.*8080" || true
        
        echo "AI Stack service stopped"
EOF
    
    success "AI Stack VM service stopped"
}

stop_browser_vm() {
    log "Stopping Browser service on VM (172.16.168.25)..."
    
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.25" << 'EOF' || true
        # Stop browser service processes
        pkill -f "browser.*service" || true
        pkill -f "python.*3000" || true
        
        # Stop Xvfb processes
        pkill -f "Xvfb.*:99" || true
        
        # Kill any remaining browser processes
        pkill chromium || true
        pkill firefox || true
        pkill playwright || true
        
        echo "Browser service stopped"
EOF
    
    success "Browser VM service stopped"
}

check_ssh_connectivity() {
    log "Checking SSH connectivity to VMs..."
    
    if [ ! -f "$SSH_KEY" ]; then
        warning "SSH key not found: $SSH_KEY"
        echo "Some VMs may not be accessible"
        return 0
    fi
    
    local accessible_vms=()
    local failed_vms=()
    
    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        echo -n "  Testing $vm_name ($vm_ip)... "
        
        if timeout 5 ssh -i "$SSH_KEY" -o ConnectTimeout=3 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Connected${NC}"
            accessible_vms+=("$vm_name")
        else
            echo -e "${RED}❌ Failed${NC}"
            failed_vms+=("$vm_name")
        fi
    done
    
    if [ ${#failed_vms[@]} -gt 0 ]; then
        warning "Cannot connect to VMs: ${failed_vms[*]}"
        echo "These VMs will be skipped"
    fi
    
    if [ ${#accessible_vms[@]} -gt 0 ]; then
        success "Accessible VMs: ${accessible_vms[*]}"
        return 0
    else
        error "No VMs are accessible via SSH"
        return 1
    fi
}

main() {
    echo -e "${GREEN}🛑 AutoBot - Stopping All VM Services${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo ""
    
    # Check which VMs we can access
    if ! check_ssh_connectivity; then
        error "Cannot access any VMs. Exiting."
        exit 1
    fi
    echo ""
    
    log "Stopping VM services in reverse dependency order..."
    echo ""
    
    # Stop services in reverse order (frontend first, Redis last)
    
    # 1. Frontend (depends on backend and other services)
    stop_frontend_vm
    echo ""
    
    # 2. Browser service, AI Stack, and NPU Worker (can stop in parallel)
    stop_browser_vm &
    stop_ai_stack_vm &
    stop_npu_worker_vm &
    wait
    echo ""
    
    # 3. Redis (should be stopped last as other services may depend on it)
    stop_redis_vm
    echo ""
    
    # Wait a moment for processes to fully terminate
    log "Waiting for processes to terminate..."
    sleep 5
    
    # Verify services are stopped by checking ports
    log "Verifying services are stopped..."
    
    echo -n "  Frontend (172.16.168.21:5173)... "
    if timeout 3 curl -s http://172.16.168.21:5173 >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Still running${NC}"
    else
        echo -e "${GREEN}✅ Stopped${NC}"
    fi
    
    echo -n "  Redis (172.16.168.23:6379)... "
    if echo "PING" | nc -w 1 172.16.168.23 6379 | grep -q "PONG" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  Still running${NC}"
    else
        echo -e "${GREEN}✅ Stopped${NC}"
    fi
    
    echo -n "  NPU Worker (172.16.168.22:8081)... "
    if timeout 3 curl -s http://172.16.168.22:8081/health >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Still running${NC}"
    else
        echo -e "${GREEN}✅ Stopped${NC}"
    fi
    
    echo -n "  AI Stack (172.16.168.24:8080)... "
    if timeout 3 curl -s http://172.16.168.24:8080/health >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Still running${NC}"
    else
        echo -e "${GREEN}✅ Stopped${NC}"
    fi
    
    echo -n "  Browser (172.16.168.25:3000)... "
    if timeout 3 curl -s http://172.16.168.25:3000/health >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Still running${NC}"
    else
        echo -e "${GREEN}✅ Stopped${NC}"
    fi
    
    echo ""
    success "VM services shutdown completed!"
    echo ""
    echo -e "${CYAN}ℹ️  Note: VMs themselves are still running, only AutoBot services were stopped${NC}"
    echo -e "${BLUE}📋 To restart services:${NC}"
    echo -e "${CYAN}  bash scripts/vm-management/start-all-vms.sh${NC}"
    echo ""
}

main