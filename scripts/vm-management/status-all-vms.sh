#!/bin/bash
# AutoBot - FIXED Check Status of All VM Services
# Comprehensive health check for all distributed VM services with proper error detection

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# SSOT Configuration - Issue #694
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/ssot-config.sh"

SSH_KEY="$AUTOBOT_SSH_KEY"
SSH_USER="$AUTOBOT_SSH_USER"
# VMS array is provided by ssot-config.sh

# Service ports (derived from SSOT)
declare -A SERVICE_PORTS=(
    ["frontend"]="$AUTOBOT_FRONTEND_PORT"
    ["npu-worker"]="$AUTOBOT_NPU_WORKER_PORT"
    ["redis"]="$AUTOBOT_REDIS_PORT"
    ["ai-stack"]="$AUTOBOT_AI_STACK_PORT"
    ["browser"]="$AUTOBOT_BROWSER_SERVICE_PORT"
)

# FIXED Health check URLs - removed incorrect /health endpoints (derived from SSOT)
declare -A HEALTH_URLS=(
    ["frontend"]="http://${VMS["frontend"]}:$AUTOBOT_FRONTEND_PORT"
    ["npu-worker"]="http://${VMS["npu-worker"]}:$AUTOBOT_NPU_WORKER_PORT/health"
    ["redis"]="${VMS["redis"]}:$AUTOBOT_REDIS_PORT"
    ["ai-stack"]="http://${VMS["ai-stack"]}:$AUTOBOT_AI_STACK_PORT/health"
    ["browser"]="http://${VMS["browser"]}:$AUTOBOT_BROWSER_SERVICE_PORT/health"
)

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

check_vm_connectivity() {
    local vm_name="$1"
    local vm_ip="$2"

    if [ ! -f "$SSH_KEY" ]; then
        echo -e "${YELLOW}No SSH key${NC}"
        return 1
    fi

    if timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
        echo -e "${GREEN}Connected${NC}"
        return 0
    else
        echo -e "${RED}Disconnected${NC}"
        return 1
    fi
}

check_service_health() {
    local vm_name="$1"
    local health_url="${HEALTH_URLS[$vm_name]}"

    if [ "$vm_name" = "redis" ]; then
        # FIXED: Use redis-cli instead of netcat for better compatibility
        if timeout 3 redis-cli -h "${VMS["redis"]}" -p "$AUTOBOT_REDIS_PORT" ping 2>/dev/null | grep -q "PONG"; then
            echo -e "${GREEN}Healthy${NC}"
            return 0
        else
            echo -e "${RED}Unhealthy${NC}"
            return 1
        fi
    else
        # HTTP health check with better error detection
        local response_code=$(timeout 5 curl -s -o /dev/null -w "%{http_code}" "$health_url" 2>/dev/null || echo "000")

        if [ "$response_code" -ge 200 ] && [ "$response_code" -lt 400 ]; then
            echo -e "${GREEN}Healthy (HTTP $response_code)${NC}"
            return 0
        else
            echo -e "${RED}Unhealthy (HTTP $response_code)${NC}"
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
            # FIXED: Check for both npm dev and nginx processes
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "pgrep -f 'npm.*dev\|vite.*5173' | wc -l" 2>/dev/null || echo "0")
            ;;
        "redis")
            # FIXED: Check for redis-stack-server service specifically
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "systemctl is-active redis-stack-server >/dev/null && echo '1' || echo '0'" 2>/dev/null || echo "0")
            ;;
        "npu-worker")
            # FIXED: Check for NPU worker service or Python server on 8081
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "systemctl is-active autobot-npu-worker >/dev/null && echo '1' || pgrep -f 'python.*8081' | wc -l" 2>/dev/null || echo "0")
            ;;
        "ai-stack")
            # FIXED: Check for AI stack service on 8080 (not Ollama on 11434)
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "pgrep -f 'python.*8080' | wc -l" 2>/dev/null || echo "0")
            ;;
        "browser")
            # FIXED: Check for browser service on 3000
            process_count=$(timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "pgrep -f 'python.*3000' | wc -l" 2>/dev/null || echo "0")
            ;;
    esac

    echo "$process_count"
}

check_backend_status() {
    echo -e "${CYAN}Backend Service (WSL - $AUTOBOT_BACKEND_HOST):${NC}"

    # Check if backend is running
    echo -n "  Process Status: "
    if pgrep -f "python.*backend/main.py" >/dev/null; then
        echo -e "${GREEN}Running${NC}"
        local backend_pid=$(pgrep -f "python.*backend/main.py")
        echo "  PID: $backend_pid"
    else
        echo -e "${RED}Not Running${NC}"
        echo -e "${YELLOW}  Start with: bash run_autobot.sh --dev${NC}"
    fi

    # Check health endpoint
    echo -n "  Health Check: "
    local health_response=$(timeout 5 curl -s "http://$AUTOBOT_BACKEND_HOST:$AUTOBOT_BACKEND_PORT/api/health" 2>/dev/null || echo "")
    if echo "$health_response" | grep -q "healthy\|ok" 2>/dev/null; then
        echo -e "${GREEN}Healthy${NC}"
        echo "  URL: http://$AUTOBOT_BACKEND_HOST:$AUTOBOT_BACKEND_PORT"
    else
        echo -e "${RED}Unhealthy${NC}"
        echo -e "${YELLOW}  Check logs: tail -f logs/backend.log${NC}"
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
    echo -e "${CYAN}VNC Desktop (WSL):${NC}"

    local xvfb_status=$(systemctl is-active xvfb@1 2>/dev/null || echo "inactive")
    local vnc_status=$(systemctl is-active vncserver@1 2>/dev/null || echo "inactive")
    local novnc_status=$(systemctl is-active novnc 2>/dev/null || echo "inactive")

    echo "  Xvfb: $xvfb_status"
    echo "  VNC Server: $vnc_status"
    echo "  noVNC: $novnc_status"

    if [ "$xvfb_status" = "active" ] && [ "$vnc_status" = "active" ] && [ "$novnc_status" = "active" ]; then
        echo -e "  Status: ${GREEN}All services running${NC}"
        echo "  Web URL: http://localhost:$AUTOBOT_VNC_PORT/vnc.html"
        echo "  VNC Client: localhost:5901"
    else
        echo -e "  Status: ${YELLOW}Partially running or stopped${NC}"
        echo "  Start with: bash run_autobot.sh --desktop"
    fi
}

# FIXED: Service-specific startup commands
get_service_startup_command() {
    local vm_name="$1"

    case "$vm_name" in
        "frontend")
            echo "ssh $SSH_USER@${VMS[$vm_name]} 'cd ~/AutoBot/autobot-vue && npm run dev -- --host 0.0.0.0 --port $AUTOBOT_FRONTEND_PORT'"
            ;;
        "redis")
            echo "bash scripts/vm-management/start-redis.sh"
            ;;
        "npu-worker")
            echo "bash scripts/vm-management/start-npu-worker.sh"
            ;;
        "ai-stack")
            echo "ssh $SSH_USER@${VMS[$vm_name]} 'cd ~/AutoBot && python -m http.server $AUTOBOT_AI_STACK_PORT'"
            ;;
        "browser")
            echo "ssh $SSH_USER@${VMS[$vm_name]} 'cd ~/AutoBot && python -c \"...browser service...\" &'"
            ;;
    esac
}

main() {
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}    AutoBot Distributed System Status (FIXED)   ${NC}"
    echo -e "${BLUE}================================================${NC}"
    echo ""

    # Show architecture overview
    echo -e "${CYAN}Architecture Overview:${NC}"
    echo "  Main (WSL):     $AUTOBOT_BACKEND_HOST - Backend API server"
    echo "  VM1 Frontend:   ${VMS["frontend"]} - Vue.js web interface"
    echo "  VM2 NPU Worker: ${VMS["npu-worker"]} - Hardware AI acceleration"
    echo "  VM3 Redis:      ${VMS["redis"]} - Database and caching"
    echo "  VM4 AI Stack:   ${VMS["ai-stack"]} - AI processing services"
    echo "  VM5 Browser:    ${VMS["browser"]} - Web automation (Playwright)"
    echo ""

    # Check backend status (local)
    check_backend_status
    echo ""

    # Check VNC status (local)
    check_vnc_status
    echo ""

    # Check each VM
    echo -e "${CYAN}VM Services Status:${NC}"
    echo ""

    local healthy_services=0
    local total_services=${#VMS[@]}
    local failed_services=()

    for vm_name in frontend redis npu-worker ai-stack browser; do
        if [ -z "${VMS[$vm_name]}" ]; then
            continue
        fi

        local vm_ip=${VMS[$vm_name]}
        local service_port=${SERVICE_PORTS[$vm_name]}

        echo -e "${BLUE}$vm_name (${vm_ip}):${NC}"

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
        else
            failed_services+=("$vm_name")
            echo -e "  ${YELLOW}Start Command: ${NC}$(get_service_startup_command "$vm_name")"
        fi

        if [ "$ssh_ok" = true ]; then
            # Additional details if SSH is available
            echo "  VM Uptime: $(get_vm_uptime "$vm_ip")"
            echo "  Load Average: $(get_vm_load "$vm_ip")"
            echo "  Processes: $(get_service_processes "$vm_ip" "$vm_name")"
            echo "  Port: $service_port"
        else
            echo "  VM Details: Unavailable (SSH connection failed)"
            echo -e "  ${YELLOW}SSH Setup: bash setup.sh ssh-keys${NC}"
        fi

        echo "  Access URL: ${HEALTH_URLS[$vm_name]}"
        echo ""
    done

    # Summary
    echo -e "${CYAN}System Summary:${NC}"
    echo "  Healthy Services: $healthy_services/$total_services"

    if [ $healthy_services -eq $total_services ]; then
        echo -e "  Overall Status: ${GREEN}All services healthy${NC}"
    elif [ $healthy_services -gt 0 ]; then
        echo -e "  Overall Status: ${YELLOW}Partially healthy${NC}"
        echo -e "  ${RED}Failed Services: ${failed_services[*]}${NC}"
    else
        echo -e "  Overall Status: ${RED}All services down${NC}"
    fi

    # FIXED: Service-specific startup recommendations
    if [ ${#failed_services[@]} -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}Recommended Actions:${NC}"

        for service in "${failed_services[@]}"; do
            case "$service" in
                "redis")
                    echo -e "${CYAN}  Fix Redis:      bash scripts/vm-management/start-redis.sh${NC}"
                    ;;
                "npu-worker")
                    echo -e "${CYAN}  Fix NPU Worker: bash scripts/vm-management/start-npu-worker.sh${NC}"
                    ;;
                "frontend")
                    echo -e "${CYAN}  Fix Frontend:   ssh $SSH_USER@${VMS["frontend"]} 'cd ~/AutoBot/autobot-vue && npm run dev -- --host 0.0.0.0'${NC}"
                    ;;
                "ai-stack")
                    echo -e "${CYAN}  Fix AI Stack:   ssh $SSH_USER@${VMS["ai-stack"]} 'cd ~/AutoBot && python -m http.server $AUTOBOT_AI_STACK_PORT'${NC}"
                    ;;
                "browser")
                    echo -e "${CYAN}  Fix Browser:    # Use start-all-vms.sh to start browser service${NC}"
                    ;;
            esac
        done
    fi

    # Quick actions
    echo ""
    echo -e "${YELLOW}Quick Actions:${NC}"
    echo -e "${CYAN}  Start all VMs:    bash scripts/vm-management/start-all-vms.sh${NC}"
    echo -e "${CYAN}  Stop all VMs:     bash scripts/vm-management/stop-all-vms.sh${NC}"
    echo -e "${CYAN}  Start backend:    bash run_autobot.sh --dev${NC}"
    echo -e "${CYAN}  Check logs:       tail -f logs/*.log${NC}"
    echo ""

    # SSH key status
    if [ ! -f "$SSH_KEY" ]; then
        echo -e "${RED}WARNING: SSH key not found ($SSH_KEY)${NC}"
        echo -e "${CYAN}  Generate keys:    bash setup.sh ssh-keys${NC}"
        echo ""
    fi

    echo -e "${BLUE}================================================${NC}"
}

main
