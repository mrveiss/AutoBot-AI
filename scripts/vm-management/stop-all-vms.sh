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

    ssh -T -i "$SSH_KEY" "$SSH_USER@172.16.168.21" << 'EOF' || true
        # Stop frontend processes - only kill processes owned by current user
        pkill -u "$(whoami)" -f "npm.*dev" 2>/dev/null || echo "No npm dev processes to stop"
        pkill -u "$(whoami)" -f "npm run dev" 2>/dev/null || echo "No npm run dev processes to stop"
        pkill -u "$(whoami)" -f "node.*vite" 2>/dev/null || echo "No Vite node processes to stop"
        pkill -u "$(whoami)" -f "vite.*--host" 2>/dev/null || echo "No Vite dev server processes to stop"
        pkill -u "$(whoami)" -f "/snap/node.*/bin/node.*vite" 2>/dev/null || echo "No snap node vite processes to stop"
        pkill -u "$(whoami)" -f "esbuild" 2>/dev/null || echo "No esbuild processes to stop"
        pkill -u "$(whoami)" -f "sh.*vite" 2>/dev/null || echo "No shell vite processes to stop"
        pkill -u "$(whoami)" -f "bash.*npm run dev" 2>/dev/null || echo "No bash npm processes to stop"

        # Kill any processes using port 5173
        if lsof -ti:5173 2>/dev/null; then
            lsof -ti:5173 | xargs -r kill 2>/dev/null || echo "Failed to kill processes on port 5173"
        fi

        # Also kill any remaining SSH sessions running frontend commands
        pkill -u "$(whoami)" -f "ssh.*npm run dev" 2>/dev/null || echo "No SSH frontend sessions to stop"

        echo "Frontend service stopped"
EOF

    success "Frontend VM service stopped"
}

stop_npu_worker_vm() {
    log "Stopping NPU Worker service on VM (172.16.168.22)..."

    ssh -T -i "$SSH_KEY" "$SSH_USER@172.16.168.22" << 'EOF' || true
        # Stop NPU Worker systemd service
        if systemctl is-active autobot-npu-worker >/dev/null 2>&1; then
            echo "Stopping NPU Worker systemd service..."
            if sudo -n systemctl stop autobot-npu-worker 2>/dev/null; then
                echo "NPU Worker service stopped via systemctl"
            else
                echo "Warning: Could not stop NPU Worker service (passwordless sudo not configured)"
                echo "Attempting to kill processes directly..."
                pkill -u "$(whoami)" -f "npu_worker_main.py" 2>/dev/null && echo "Stopped NPU worker main process"
            fi
        else
            echo "NPU Worker service not running"
        fi

        # Disable auto-restart
        if sudo -n systemctl disable autobot-npu-worker 2>/dev/null; then
            echo "Disabled NPU Worker auto-restart"
        fi

        echo "NPU Worker service stopped"
EOF

    success "NPU Worker VM service stopped"
}

stop_redis_vm() {
    log "Stopping Redis service on VM (172.16.168.23)..."

    ssh -T -i "$SSH_KEY" "$SSH_USER@172.16.168.23" << 'EOF' || true
        # Stop Redis Stack systemd service
        if systemctl is-active redis-stack-server >/dev/null 2>&1; then
            echo "Stopping Redis Stack systemd service..."
            if sudo -n systemctl stop redis-stack-server 2>/dev/null; then
                echo "Redis Stack service stopped via systemctl"
            else
                echo "Warning: Could not stop Redis Stack service (passwordless sudo not configured)"
                echo "Attempting to kill processes directly..."
                pkill -u "$(whoami)" -f "redis-stack-server" 2>/dev/null && echo "Stopped Redis Stack wrapper script"
                pkill -u "$(whoami)" -f "/opt/redis-stack/bin/redis-server" 2>/dev/null && echo "Stopped Redis server process"
            fi
        else
            echo "Redis Stack service not running"
        fi

        # Disable auto-restart and mask service to prevent any restart
        if sudo -n systemctl disable redis-stack-server 2>/dev/null; then
            echo "Disabled Redis Stack auto-restart"
        fi
        if sudo -n systemctl mask redis-stack-server 2>/dev/null; then
            echo "Masked Redis Stack service to prevent restart"
        fi

        echo "Redis service stopped"
EOF

    success "Redis VM service stopped"
}

stop_ai_stack_vm() {
    log "Stopping AI Stack service on VM (172.16.168.24)..."

    ssh -T -i "$SSH_KEY" "$SSH_USER@172.16.168.24" << 'EOF' || true
        # Stop AI stack processes - only kill processes owned by current user
        pkill -u "$(whoami)" -f "ai.*stack" 2>/dev/null || echo "No AI stack processes to stop"
        pkill -u "$(whoami)" -f "python.*8080" 2>/dev/null || echo "No Python processes on port 8080 to stop"
        pkill -u "$(whoami)" -f "ollama" 2>/dev/null || echo "No Ollama processes to stop"

        echo "AI Stack service stopped"
EOF

    success "AI Stack VM service stopped"
}

stop_browser_vm() {
    log "Stopping Browser service on VM (172.16.168.25)..."

    ssh -T -i "$SSH_KEY" "$SSH_USER@172.16.168.25" << 'EOF' || true
        # Stop Browser systemd services
        if systemctl is-active autobot-browser.service >/dev/null 2>&1; then
            echo "Stopping Browser systemd service..."
            if sudo -n systemctl stop autobot-browser.service 2>/dev/null; then
                echo "Browser service stopped via systemctl"
            else
                echo "Warning: Could not stop Browser service (passwordless sudo not configured)"
            fi
        fi

        if systemctl is-active autobot-browser-service.service >/dev/null 2>&1; then
            echo "Stopping Browser service systemd service..."
            if sudo -n systemctl stop autobot-browser-service.service 2>/dev/null; then
                echo "Browser service service stopped via systemctl"
            fi
        fi

        # Disable auto-restart and mask services
        if sudo -n systemctl disable autobot-browser.service 2>/dev/null; then
            echo "Disabled Browser auto-restart"
        fi
        if sudo -n systemctl mask autobot-browser.service 2>/dev/null; then
            echo "Masked Browser service to prevent restart"
        fi
        if sudo -n systemctl disable autobot-browser-service.service 2>/dev/null; then
            echo "Disabled Browser service auto-restart"
        fi
        if sudo -n systemctl mask autobot-browser-service.service 2>/dev/null; then
            echo "Masked Browser service service to prevent restart"
        fi

        # Kill remaining processes if any
        pkill -u "$(whoami)" -f "playwright-server.js" 2>/dev/null && echo "Stopped remaining Playwright server processes"
        pkill -u "$(whoami)" -f "headless_shell" 2>/dev/null && echo "Stopped remaining Chromium processes"

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
        
        if timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
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
    if echo "PING" | nc -w 1 172.16.168.23 6379 2>/dev/null | grep -q "PONG" 2>/dev/null; then
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