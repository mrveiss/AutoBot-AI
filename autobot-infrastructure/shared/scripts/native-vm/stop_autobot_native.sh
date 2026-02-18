#!/bin/bash
# AutoBot Native VM - Complete Shutdown Procedure
# Connects to all VMs and stops all services gracefully

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

SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${AUTOBOT_SSH_USER:-autobot}"

# Default options
FORCE_STOP=false
PARALLEL_STOP=true

print_usage() {
    echo -e "${GREEN}AutoBot Native VM - Complete Shutdown Procedure${NC}"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --force       Force stop services (kill if necessary)"
    echo "  --sequential  Stop services sequentially instead of parallel"
    echo "  --help        Show this help"
    echo ""
    echo "This script will:"
    echo "  1. Stop WSL backend if running"
    echo "  2. Stop all VM services gracefully"
    echo "  3. Verify all services are stopped"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_STOP=true
            shift
            ;;
        --sequential)
            PARALLEL_STOP=false
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

stop_wsl_backend() {
    echo -e "${CYAN}🛑 Stopping WSL Backend...${NC}"

    # Find and stop backend processes
    local backend_pids=$(pgrep -f "main.py\|uvicorn.*api.main:app" 2>/dev/null || true)

    if [ -n "$backend_pids" ]; then
        echo "Found backend process(es): $backend_pids"
        for pid in $backend_pids; do
            echo "Stopping backend process $pid..."
            if [ "$FORCE_STOP" = true ]; then
                kill -KILL $pid 2>/dev/null || true
            else
                kill -TERM $pid 2>/dev/null || true
                sleep 2
                # Check if still running and force kill if needed
                if kill -0 $pid 2>/dev/null; then
                    echo "Process $pid still running, force killing..."
                    kill -KILL $pid 2>/dev/null || true
                fi
            fi
        done
        echo -e "${GREEN}✅ WSL Backend stopped${NC}"
    else
        echo -e "${YELLOW}ℹ️  No WSL Backend processes found${NC}"
    fi
}

stop_vm_service() {
    local vm_name=$1
    local vm_ip=$2
    local service_name=$3

    echo -e "${CYAN}🛑 Stopping $vm_name service...${NC}"

    # Check if service is running first
    if ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" \
        "sudo systemctl is-active $service_name" >/dev/null 2>&1; then

        # Stop the service
        if [ "$FORCE_STOP" = true ]; then
            ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" \
                "sudo systemctl kill $service_name && sudo systemctl stop $service_name" 2>/dev/null || true
        else
            ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" \
                "sudo systemctl stop $service_name" 2>/dev/null || true
        fi

        # Wait a moment
        sleep 2

        # Verify service is stopped
        if ! ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" \
            "sudo systemctl is-active $service_name" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ $vm_name service stopped${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠️  $vm_name service may still be running${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}ℹ️  $vm_name service already stopped${NC}"
        return 0
    fi
}

stop_services_parallel() {
    echo -e "${YELLOW}🛑 Stopping all VM services in parallel...${NC}"

    # Stop all services in background
    for vm_name in "${!VMS[@]}"; do
        (
            vm_ip=${VMS[$vm_name]}
            service_name=${SERVICES[$vm_name]}
            stop_vm_service "$vm_name" "$vm_ip" "$service_name"
        ) &
    done

    # Wait for all background jobs to complete
    wait
    echo -e "${GREEN}✅ All VM services stop commands completed${NC}"
}

stop_services_sequential() {
    echo -e "${YELLOW}🛑 Stopping VM services sequentially...${NC}"

    # Stop services in reverse dependency order
    local service_order=("frontend" "browser" "npu-worker" "ai-stack" "redis")

    for vm_name in "${service_order[@]}"; do
        vm_ip=${VMS[$vm_name]}
        service_name=${SERVICES[$vm_name]}
        stop_vm_service "$vm_name" "$vm_ip" "$service_name"
        echo ""
    done
}

verify_services_stopped() {
    echo -e "${BLUE}🔍 Verifying all services are stopped...${NC}"

    local all_stopped=true

    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        service_name=${SERVICES[$vm_name]}

        echo -n "  Checking $vm_name... "

        if ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" \
            "sudo systemctl is-active $service_name" >/dev/null 2>&1; then
            echo -e "${RED}❌ Still running${NC}"
            all_stopped=false
        else
            echo -e "${GREEN}✅ Stopped${NC}"
        fi
    done

    # Check WSL backend
    echo -n "  Checking WSL Backend... "
    local backend_pids=$(pgrep -f "main.py\|uvicorn.*api.main:app" 2>/dev/null || true)
    if [ -n "$backend_pids" ]; then
        echo -e "${RED}❌ Still running (PIDs: $backend_pids)${NC}"
        all_stopped=false
    else
        echo -e "${GREEN}✅ Stopped${NC}"
    fi

    if [ "$all_stopped" = true ]; then
        echo -e "${GREEN}✅ All services successfully stopped${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  Some services may still be running${NC}"
        if [ "$FORCE_STOP" = false ]; then
            echo -e "${BLUE}💡 Try running with --force flag for forceful shutdown${NC}"
        fi
        return 1
    fi
}

# Main execution
echo -e "${GREEN}🛑 AutoBot Native VM - Complete Shutdown Procedure${NC}"
echo -e "${BLUE}===================================================${NC}"
echo ""

# Check prerequisites
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}❌ SSH key not found: $SSH_KEY${NC}"
    echo "Cannot connect to VMs without SSH key."
    exit 1
fi

# Stop WSL backend first
stop_wsl_backend
echo ""

# Stop VM services
if [ "$PARALLEL_STOP" = true ]; then
    stop_services_parallel
else
    stop_services_sequential
fi

echo ""

# Verify everything is stopped
verify_services_stopped

echo ""
if [ $? -eq 0 ]; then
    echo -e "${GREEN}🎉 AutoBot Native VM Deployment Stopped Successfully!${NC}"
    echo -e "${BLUE}All services are now offline.${NC}"
    echo ""
    echo -e "${YELLOW}To start AutoBot again, run: ./start_autobot_native.sh${NC}"
else
    echo -e "${YELLOW}⚠️  Shutdown completed with some warnings.${NC}"
    echo -e "${BLUE}Check the status above and use --force if needed.${NC}"
fi
