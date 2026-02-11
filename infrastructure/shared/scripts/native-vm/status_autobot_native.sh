#!/bin/bash
# AutoBot Native VM - Status Check
# Shows current status of all services across VMs

set -e

# Load SSOT configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

# Load unified configuration system (legacy)
_NATIVE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." &> /dev/null && pwd)"
if [[ -f "${_NATIVE_SCRIPT_DIR}/config/load_config.sh" ]]; then
    export PATH="$HOME/bin:$PATH"  # Ensure yq is available
    source "${_NATIVE_SCRIPT_DIR}/config/load_config.sh"
    echo -e "\033[0;32m✓ Loaded unified configuration system\033[0m"
else
    echo -e "\033[0;31m✗ Warning: Unified configuration not found, using fallback values\033[0m"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# VM Configuration (from unified config, with SSOT fallback)
declare -A VMS
VMS[frontend]=$(get_config "infrastructure.hosts.frontend" 2>/dev/null || echo "${AUTOBOT_FRONTEND_HOST:-172.16.168.21}")
VMS[npu-worker]=$(get_config "infrastructure.hosts.npu_worker" 2>/dev/null || echo "${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}")
VMS[redis]=$(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "${AUTOBOT_REDIS_HOST:-172.16.168.23}")
VMS[ai-stack]=$(get_config "infrastructure.hosts.ai_stack" 2>/dev/null || echo "${AUTOBOT_AI_STACK_HOST:-172.16.168.24}")
VMS[browser]=$(get_config "infrastructure.hosts.browser_service" 2>/dev/null || echo "${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}")

# Service Configuration
declare -A SERVICES
SERVICES[frontend]="nginx"
SERVICES[npu-worker]="autobot-npu-worker.service"
SERVICES[redis]="redis-stack-server"
SERVICES[ai-stack]="autobot-ai-stack.service"
SERVICES[browser]="autobot-browser-service.service"

# Health Check URLs
declare -A HEALTH_URLS
HEALTH_URLS[frontend]="http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}/"
HEALTH_URLS[npu-worker]="http://${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:${AUTOBOT_NPU_WORKER_PORT:-8081}/health"
HEALTH_URLS[redis]="${AUTOBOT_REDIS_HOST:-172.16.168.23}:${AUTOBOT_REDIS_PORT:-6379}"
HEALTH_URLS[ai-stack]="http://${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:${AUTOBOT_AI_STACK_PORT:-8080}/health"
HEALTH_URLS[browser]="http://${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}/health"

SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${AUTOBOT_SSH_USER:-autobot}"

# Options
DETAILED=false
HEALTH_CHECK=true

print_usage() {
    echo -e "${GREEN}AutoBot Native VM - Status Check${NC}"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --detailed      Show detailed service information"
    echo "  --no-health     Skip health endpoint checks"
    echo "  --help          Show this help"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --detailed)
            DETAILED=true
            shift
            ;;
        --no-health)
            HEALTH_CHECK=false
            shift
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

check_vm_connectivity() {
    local vm_name=$1
    local vm_ip=$2

    if timeout 3 ssh -i "$SSH_KEY" -o ConnectTimeout=2 "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

get_service_status() {
    local vm_name=$1
    local vm_ip=$2
    local service_name=$3

    if ! check_vm_connectivity "$vm_name" "$vm_ip"; then
        echo -e "${RED}VM Unreachable${NC}"
        return 1
    fi

    local status_output=$(ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" \
        "sudo systemctl is-active $service_name 2>/dev/null" || echo "unknown")

    case "$status_output" in
        "active")
            echo -e "${GREEN}Running${NC}"
            return 0
            ;;
        "inactive"|"failed")
            echo -e "${RED}Stopped${NC}"
            return 1
            ;;
        "activating")
            echo -e "${YELLOW}Starting${NC}"
            return 2
            ;;
        *)
            echo -e "${YELLOW}Unknown${NC}"
            return 3
            ;;
    esac
}

get_detailed_service_info() {
    local vm_name=$1
    local vm_ip=$2
    local service_name=$3

    if ! check_vm_connectivity "$vm_name" "$vm_ip"; then
        echo "    VM is not accessible via SSH"
        return 1
    fi

    echo "    Service: $service_name"

    local status_info=$(ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" \
        "sudo systemctl status $service_name --no-pager -l -n 3" 2>/dev/null || echo "Status unavailable")

    if [[ "$status_info" == "Status unavailable" ]]; then
        echo "    Status: Information not available"
        return 1
    fi

    # Extract key information
    local main_pid=$(echo "$status_info" | grep "Main PID:" | awk '{print $3}' | head -1)
    local memory=$(echo "$status_info" | grep "Memory:" | awk '{print $2}' | head -1)
    local since=$(echo "$status_info" | grep "Active:" | sed 's/.*since //' | cut -d';' -f1 | head -1)

    echo "    PID: ${main_pid:-"N/A"}"
    echo "    Memory: ${memory:-"N/A"}"
    echo "    Started: ${since:-"N/A"}"

    # Show recent log entries
    local logs=$(echo "$status_info" | tail -3 | grep -v "^$")
    if [ -n "$logs" ]; then
        echo "    Recent logs:"
        echo "$logs" | sed 's/^/      /'
    fi
}

test_health_endpoint() {
    local vm_name=$1
    local health_url=$2

    if [ "$vm_name" = "redis" ]; then
        # Special case for Redis
        if timeout 3 bash -c "echo 'PING' | nc -w 2 ${AUTOBOT_REDIS_HOST:-172.16.168.23} ${AUTOBOT_REDIS_PORT:-6379}" | grep -q "PONG" 2>/dev/null; then
            echo -e "${GREEN}Healthy${NC}"
            return 0
        else
            echo -e "${RED}Unhealthy${NC}"
            return 1
        fi
    else
        # HTTP health check
        local response_code=$(timeout 5 curl -s -o /dev/null -w "%{http_code}" "$health_url" 2>/dev/null || echo "000")
        if [ "$response_code" = "200" ]; then
            echo -e "${GREEN}Healthy${NC}"
            return 0
        else
            echo -e "${RED}Unhealthy (${response_code})${NC}"
            return 1
        fi
    fi
}

check_wsl_backend() {
    echo -e "${CYAN}WSL Backend (${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}):${NC}"

    local backend_pids=$(pgrep -f "main.py\|uvicorn.*api.main:app" 2>/dev/null || true)

    if [ -n "$backend_pids" ]; then
        echo -e "  Process Status: ${GREEN}Running (PIDs: $backend_pids)${NC}"

        if [ "$HEALTH_CHECK" = true ]; then
            echo -n "  Health Status: "
            if timeout 3 curl -s http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
                echo -e "${GREEN}Healthy${NC}"
            else
                echo -e "${RED}Unhealthy${NC}"
            fi
        fi

        if [ "$DETAILED" = true ]; then
            for pid in $backend_pids; do
                local memory=$(ps -p $pid -o rss= 2>/dev/null | awk '{print int($1/1024)"MB"}' || echo "N/A")
                local cpu=$(ps -p $pid -o %cpu= 2>/dev/null | awk '{print $1"%"}' || echo "N/A")
                local cmd=$(ps -p $pid -o cmd= 2>/dev/null | cut -c1-50 || echo "N/A")
                echo "    PID $pid: Memory: $memory, CPU: $cpu"
                echo "    Command: $cmd"
            done
        fi
    else
        echo -e "  Process Status: ${RED}Not Running${NC}"
        if [ "$HEALTH_CHECK" = true ]; then
            echo -e "  Health Status: ${RED}Not Available${NC}"
        fi
    fi
}

# Main execution
echo -e "${GREEN}🔍 AutoBot Native VM - Status Check${NC}"
echo -e "${BLUE}====================================${NC}"
echo ""

# Check SSH key
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}❌ SSH key not found: $SSH_KEY${NC}"
    echo "Cannot check VM services without SSH key."
    exit 1
fi

# Check WSL Backend first
check_wsl_backend
echo ""

# Check each VM service
echo -e "${CYAN}VM Services Status:${NC}"
echo ""

total_services=0
running_services=0
healthy_services=0

for vm_name in frontend npu-worker redis ai-stack browser; do
    vm_ip=${VMS[$vm_name]}
    service_name=${SERVICES[$vm_name]}
    health_url=${HEALTH_URLS[$vm_name]}

    total_services=$((total_services + 1))

    echo -e "${BLUE}$vm_name ($vm_ip):${NC}"

    echo -n "  Service Status: "
    get_service_status "$vm_name" "$vm_ip" "$service_name"
    service_status=$?

    if [ $service_status -eq 0 ]; then
        running_services=$((running_services + 1))
    fi

    if [ "$HEALTH_CHECK" = true ]; then
        echo -n "  Health Status: "
        test_health_endpoint "$vm_name" "$health_url"
        health_status=$?

        if [ $health_status -eq 0 ]; then
            healthy_services=$((healthy_services + 1))
        fi
    fi

    if [ "$DETAILED" = true ]; then
        get_detailed_service_info "$vm_name" "$vm_ip" "$service_name"
    fi

    echo ""
done

# Summary
echo -e "${BLUE}📊 Summary:${NC}"
echo -e "Services Running: ${running_services}/${total_services}"

if [ "$HEALTH_CHECK" = true ]; then
    echo -e "Services Healthy: ${healthy_services}/${total_services}"
fi

if [ $running_services -eq $total_services ]; then
    if [ "$HEALTH_CHECK" = false ] || [ $healthy_services -eq $total_services ]; then
        echo -e "${GREEN}🎉 All systems operational!${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠️  All services running but some health checks failed${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ Some services are not running${NC}"
    exit 2
fi
