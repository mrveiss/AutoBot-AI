#!/bin/bash
# AutoBot - Check Status of All VM Services
# Comprehensive health check for all distributed VM services

set -e

# Source centralized network configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../network/network-config.sh" 2>/dev/null || {
    # Fallback defaults if network-config.sh not available
    export BACKEND_PORT="${BACKEND_PORT:-8001}"
}

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

# Service ports
declare -A SERVICE_PORTS=(
    ["frontend"]="5173"
    ["npu-worker"]="8081"
    ["redis"]="6379"
    ["ai-stack"]="8080"
    ["browser"]="3000"
)

# Health check URLs
declare -A HEALTH_URLS=(
    ["frontend"]="http://172.16.168.21:5173"
    ["npu-worker"]="http://172.16.168.22:8081/health"
    ["redis"]="172.16.168.23:6379"
    ["ai-stack"]="http://172.16.168.24:8080/health"
    ["browser"]="http://172.16.168.25:3000/health"
)

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

check_vm_connectivity() {
    local vm_name="$1"
    local vm_ip="$2"
    
    if [ ! -f "$SSH_KEY" ]; then
        echo -e "${YELLOW}⚠️  No SSH key${NC}"
        return 1
    fi
    
    if timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Connected${NC}"
        return 0
    else
        echo -e "${RED}❌ Disconnected${NC}"
        return 1
    fi
}

check_service_health() {
    local vm_name="$1"
    local health_url="${HEALTH_URLS[$vm_name]}"
    
    if [ "$vm_name" = "redis" ]; then
        # Special case for Redis (TCP connection)
        if echo "PING" | nc -w 2 172.16.168.23 6379 | grep -q "PONG" 2>/dev/null; then
            echo -e "${GREEN}✅ Healthy${NC}"
            return 0
        else
            echo -e "${RED}❌ Unhealthy${NC}"
            return 1
        fi
    else
        # HTTP health check
        if timeout 5 curl -s "$health_url" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Healthy${NC}"
            return 0
        else
            echo -e "${RED}❌ Unhealthy${NC}"
            return 1
        fi
    fi
}

get_vm_uptime() {
    local vm_ip="$1"
    
    if [ ! -f "$SSH_KEY" ]; then
        echo "Unknown"
        return
    fi
    
    local uptime=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "uptime -p" 2>/dev/null | sed 's/up //' || echo "Unknown")
    echo "$uptime"
}

get_vm_load() {
    local vm_ip="$1"
    
    if [ ! -f "$SSH_KEY" ]; then
        echo "Unknown"
        return
    fi
    
    local load=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "uptime | awk -F'load average:' '{print \$2}' | sed 's/^ *//'" 2>/dev/null || echo "Unknown")
    echo "$load"
}

get_service_processes() {
    local vm_ip="$1"
    local vm_name="$2"
    
    if [ ! -f "$SSH_KEY" ]; then
        echo "0"
        return
    fi
    
    local process_count=0
    
    case "$vm_name" in
        "frontend")
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "pgrep -f 'npm.*dev' | wc -l" 2>/dev/null || echo "0")
            ;;
        "redis")
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "systemctl is-active redis-stack-server >/dev/null && echo '1' || echo '0'" 2>/dev/null || echo "0")
            ;;
        "npu-worker")
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "pgrep -f 'python.*8081' | wc -l" 2>/dev/null || echo "0")
            ;;
        "ai-stack")
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "pgrep -f 'python.*8080' | wc -l" 2>/dev/null || echo "0")
            ;;
        "browser")
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "pgrep -f 'python.*3000' | wc -l" 2>/dev/null || echo "0")
            ;;
    esac
    
    echo "$process_count"
}

check_backend_status() {
    echo -e "${CYAN}🔧 Backend Service (WSL - 172.16.168.20):${NC}"
    
    # Check if backend is running
    echo -n "  Process Status: "
    if pgrep -f "python.*backend/main.py" >/dev/null; then
        echo -e "${GREEN}✅ Running${NC}"
        local backend_pid=$(pgrep -f "python.*backend/main.py")
        echo "  PID: $backend_pid"
    else
        echo -e "${RED}❌ Not Running${NC}"
    fi
    
    # Check health endpoint
    echo -n "  Health Check: "
    if timeout 5 curl -s http://localhost:${BACKEND_PORT}/api/health >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Healthy${NC}"
        echo "  URL: http://172.16.168.20:${BACKEND_PORT}"
    else
        echo -e "${RED}❌ Unhealthy${NC}"
    fi
    
    # Check log file
    if [ -f "logs/backend.log" ]; then
        local log_size=$(du -h logs/backend.log | cut -f1)
        local last_modified=$(stat -c %y logs/backend.log | cut -d'.' -f1)
        echo "  Log Size: $log_size"
        echo "  Last Updated: $last_modified"
    else
        echo "  Log File: Not found"
    fi
}

check_vnc_status() {
    echo -e "${CYAN}🖥️  VNC Desktop (WSL):${NC}"
    
    local xvfb_status=$(systemctl is-active xvfb@1 2>/dev/null || echo "inactive")
    local vnc_status=$(systemctl is-active vncserver@1 2>/dev/null || echo "inactive")
    local novnc_status=$(systemctl is-active novnc 2>/dev/null || echo "inactive")
    
    echo "  Xvfb: $xvfb_status"
    echo "  VNC Server: $vnc_status"
    echo "  noVNC: $novnc_status"
    
    if [ "$xvfb_status" = "active" ] && [ "$vnc_status" = "active" ] && [ "$novnc_status" = "active" ]; then
        echo -e "  Status: ${GREEN}✅ All services running${NC}"
        echo "  Web URL: http://localhost:6080/vnc.html"
        echo "  VNC Client: localhost:5901"
    else
        echo -e "  Status: ${YELLOW}⚠️  Partially running or stopped${NC}"
        echo "  Start with: bash run_autobot.sh --desktop"
    fi
}

main() {
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo -e "${BLUE}         AutoBot Distributed System Status      ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo ""
    
    # Show architecture overview
    echo -e "${CYAN}🏗️  Architecture Overview:${NC}"
    echo "  Main (WSL):     172.16.168.20 - Backend API server"
    echo "  VM1 Frontend:   172.16.168.21 - Vue.js web interface"
    echo "  VM2 NPU Worker: 172.16.168.22 - Hardware AI acceleration"
    echo "  VM3 Redis:      172.16.168.23 - Database and caching"
    echo "  VM4 AI Stack:   172.16.168.24 - AI processing services"
    echo "  VM5 Browser:    172.16.168.25 - Web automation (Playwright)"
    echo ""
    
    # Check backend status (local)
    check_backend_status
    echo ""
    
    # Check VNC status (local)
    check_vnc_status
    echo ""
    
    # Check each VM
    echo -e "${CYAN}🌐 VM Services Status:${NC}"
    echo ""
    
    local healthy_services=0
    local total_services=${#VMS[@]}
    
    for vm_name in frontend redis npu-worker ai-stack browser; do
        if [ -z "${VMS[$vm_name]}" ]; then
            continue
        fi
        
        local vm_ip=${VMS[$vm_name]}
        local service_port=${SERVICE_PORTS[$vm_name]}
        
        echo -e "${BLUE}📦 $vm_name (${vm_ip}):${NC}"
        
        # VM Connectivity
        echo -n "  SSH Connectivity: "
        local ssh_ok=false
        if check_vm_connectivity "$vm_name" "$vm_ip"; then
            ssh_ok=true
        fi
        
        # Service Health
        echo -n "  Service Health:   "
        if check_service_health "$vm_name"; then
            ((healthy_services++))
        fi
        
        if [ "$ssh_ok" = true ]; then
            # Additional details if SSH is available
            echo "  VM Uptime: $(get_vm_uptime "$vm_ip")"
            echo "  Load Average: $(get_vm_load "$vm_ip")"
            echo "  Processes: $(get_service_processes "$vm_ip" "$vm_name")"
            echo "  Port: $service_port"
        else
            echo "  VM Details: Unavailable (SSH connection failed)"
        fi
        
        echo "  Access URL: ${HEALTH_URLS[$vm_name]}"
        echo ""
    done
    
    # Summary
    echo -e "${CYAN}📊 System Summary:${NC}"
    echo "  Healthy Services: $healthy_services/$total_services"
    
    if [ $healthy_services -eq $total_services ]; then
        echo -e "  Overall Status: ${GREEN}✅ All services healthy${NC}"
    elif [ $healthy_services -gt 0 ]; then
        echo -e "  Overall Status: ${YELLOW}⚠️  Partially healthy${NC}"
    else
        echo -e "  Overall Status: ${RED}❌ All services down${NC}"
    fi
    
    # Quick actions
    echo ""
    echo -e "${YELLOW}📋 Quick Actions:${NC}"
    echo -e "${CYAN}  Start all VMs:    bash scripts/vm-management/start-all-vms.sh${NC}"
    echo -e "${CYAN}  Stop all VMs:     bash scripts/vm-management/stop-all-vms.sh${NC}"
    echo -e "${CYAN}  Start backend:    bash run_autobot.sh --dev${NC}"
    echo -e "${CYAN}  Check logs:       tail -f logs/*.log${NC}"
    echo ""
    
    # SSH key status
    if [ ! -f "$SSH_KEY" ]; then
        echo -e "${RED}⚠️  WARNING: SSH key not found ($SSH_KEY)${NC}"
        echo -e "${CYAN}  Generate keys:    bash setup.sh ssh-keys${NC}"
        echo ""
    fi
    
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
}

main