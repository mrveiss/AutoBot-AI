#!/bin/bash
# AutoBot Native VM - Single Startup Procedure
# Connects to all VMs and starts required services automatically

set -e

# Load unified configuration system
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." &> /dev/null && pwd)"
if [[ -f "${SCRIPT_DIR}/config/load_config.sh" ]]; then
    export PATH="$HOME/bin:$PATH"  # Ensure yq is available
    source "${SCRIPT_DIR}/config/load_config.sh"
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

# VM Configuration (from unified config)
declare -A VMS
VMS[frontend]=$(get_config "infrastructure.hosts.frontend" 2>/dev/null || echo "172.16.168.21")
VMS[npu-worker]=$(get_config "infrastructure.hosts.npu_worker" 2>/dev/null || echo "172.16.168.22")
VMS[redis]=$(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23")
VMS[ai-stack]=$(get_config "infrastructure.hosts.ai_stack" 2>/dev/null || echo "172.16.168.24")
VMS[browser]=$(get_config "infrastructure.hosts.browser_service" 2>/dev/null || echo "172.16.168.25")

# Service Configuration
declare -A SERVICES
SERVICES[frontend]="nginx"
SERVICES[npu-worker]="autobot-npu-worker.service"
SERVICES[redis]="redis-stack-server"
SERVICES[ai-stack]="autobot-ai-stack.service"
SERVICES[browser]="autobot-browser-service.service"

# Health Check URLs
declare -A HEALTH_URLS
HEALTH_URLS[frontend]="http://172.16.168.21/"
HEALTH_URLS[npu-worker]="http://172.16.168.22:8081/health"
HEALTH_URLS[redis]="172.16.168.23:6379"
HEALTH_URLS[ai-stack]="http://172.16.168.24:8080/health"
HEALTH_URLS[browser]="http://172.16.168.25:3000/health"

SSH_KEY="$HOME/.ssh/autobot_key"
SSH_USER="autobot"
BACKEND_PID=""
BROWSER_PID=""

# Default options
AUTO_BROWSER=true
SHOW_STATUS=true
PARALLEL_START=true

print_usage() {
    echo -e "${GREEN}AutoBot Native VM - Single Startup Procedure${NC}"
    echo "Prerequisites: All VMs must be running and accessible via SSH"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --no-browser    Don't auto-launch browser"
    echo "  --no-status     Don't show service status after startup"
    echo "  --sequential    Start services sequentially instead of parallel"
    echo "  --help          Show this help"
    echo ""
    echo -e "${BLUE}VM Architecture:${NC}"
    echo "  Frontend:   172.16.168.21 (VM1) - Nginx + Vue.js"
    echo "  NPU Worker: 172.16.168.22 (VM2) - Hardware detection"
    echo "  Redis:      172.16.168.23 (VM3) - Data layer"
    echo "  AI Stack:   172.16.168.24 (VM4) - AI processing"
    echo "  Browser:    172.16.168.25 (VM5) - Web automation"
    echo "  Backend:    172.16.168.20 (WSL) - API server"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-browser)
            AUTO_BROWSER=false
            shift
            ;;
        --no-status)
            SHOW_STATUS=false
            shift
            ;;
        --sequential)
            PARALLEL_START=false
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

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down AutoBot Native...${NC}"
    
    if [ ! -z "$BACKEND_PID" ]; then
        echo "Stopping WSL backend (PID: $BACKEND_PID)..."
        kill -TERM $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
    fi
    
    if [ ! -z "$BROWSER_PID" ]; then
        echo "Closing browser (PID: $BROWSER_PID)..."
        kill -TERM $BROWSER_PID 2>/dev/null || true
    fi
    
    echo -e "${YELLOW}Note: VM services continue running. Use 'stop_autobot_native.sh' to stop all services.${NC}"
    echo -e "${GREEN}✅ AutoBot Native WSL backend stopped${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

check_prerequisites() {
    echo -e "${BLUE}🔍 Checking Prerequisites...${NC}"
    
    # Check SSH key
    if [ ! -f "$SSH_KEY" ]; then
        echo -e "${RED}❌ SSH key not found: $SSH_KEY${NC}"
        echo "Please run the deployment script first to set up SSH keys."
        exit 1
    fi
    
    # Check native configuration
    if [ ! -f ".env.native-vm" ]; then
        echo -e "${RED}❌ Native VM configuration not found: .env.native-vm${NC}"
        echo "Please run the deployment script first."
        exit 1
    fi
    
    echo -e "${GREEN}✅ SSH key found${NC}"
    echo -e "${GREEN}✅ Configuration found${NC}"
}

test_vm_connectivity() {
    local vm_name=$1
    local vm_ip=$2
    
    echo -n "  Testing $vm_name ($vm_ip)... "
    
    if timeout 5 ssh -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Connected${NC}"
        return 0
    else
        echo -e "${RED}❌ Failed${NC}"
        return 1
    fi
}

start_vm_service() {
    local vm_name=$1
    local vm_ip=$2
    local service_name=$3
    
    echo -e "${CYAN}🚀 Starting $vm_name service...${NC}"
    
    # Start the service
    ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" \
        "sudo systemctl start $service_name && sudo systemctl enable $service_name" 2>/dev/null || {
        echo -e "${YELLOW}⚠️  Service may already be running or needs manual attention${NC}"
    }
    
    # Wait a moment for service to initialize
    sleep 2
    
    # Check service status
    if ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" \
        "sudo systemctl is-active $service_name" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ $vm_name service started successfully${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  $vm_name service status unclear, will test health endpoint${NC}"
        return 1
    fi
}

test_service_health() {
    local vm_name=$1
    local health_url=$2
    
    echo -n "  $vm_name health check... "
    
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

start_services_parallel() {
    echo -e "${YELLOW}🚀 Starting all VM services in parallel...${NC}"
    
    # Start all services in background
    for vm_name in "${!VMS[@]}"; do
        (
            vm_ip=${VMS[$vm_name]}
            service_name=${SERVICES[$vm_name]}
            start_vm_service "$vm_name" "$vm_ip" "$service_name"
        ) &
    done
    
    # Wait for all background jobs to complete
    wait
    echo -e "${GREEN}✅ All VM services start commands completed${NC}"
}

start_services_sequential() {
    echo -e "${YELLOW}🚀 Starting VM services sequentially...${NC}"
    
    # Start services in dependency order
    local service_order=("redis" "ai-stack" "npu-worker" "browser" "frontend")
    
    for vm_name in "${service_order[@]}"; do
        vm_ip=${VMS[$vm_name]}
        service_name=${SERVICES[$vm_name]}
        start_vm_service "$vm_name" "$vm_ip" "$service_name"
        echo ""
    done
}

start_wsl_backend() {
    echo -e "${CYAN}🔧 Starting WSL Backend...${NC}"
    
    # Load native VM configuration
    set -a
    source ".env.native-vm"
    set +a
    
    # Start backend
    if [ -f "backend/main.py" ]; then
        echo "Using optimized backend startup..."
        cd backend && python3 main.py &
    else
        echo "Using standard backend startup..."
        cd backend && python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload &
    fi
    
    BACKEND_PID=$!
    cd ..
    
    echo -e "${GREEN}✅ WSL Backend started (PID: $BACKEND_PID)${NC}"
    
    # Wait for backend to be ready
    echo -n "Waiting for backend to be ready"
    for i in {1..30}; do
        if curl -s http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
            echo -e " ${GREEN}✅ Ready!${NC}"
            return 0
        fi
        sleep 1
        echo -n "."
    done
    echo -e " ${YELLOW}⚠️  Backend may need more time${NC}"
}

launch_browser() {
    if [ "$AUTO_BROWSER" = true ]; then
        echo -e "${CYAN}🌐 Launching browser...${NC}"
        sleep 2  # Give services a moment to fully initialize
        
        if command -v firefox >/dev/null 2>&1; then
            firefox "http://172.16.168.21/" >/dev/null 2>&1 &
            BROWSER_PID=$!
            echo -e "${GREEN}✅ Firefox launched${NC}"
        elif command -v google-chrome >/dev/null 2>&1; then
            google-chrome "http://172.16.168.21/" >/dev/null 2>&1 &
            BROWSER_PID=$!
            echo -e "${GREEN}✅ Chrome launched${NC}"
        else
            echo -e "${YELLOW}⚠️  No browser found. Please open http://172.16.168.21/ manually${NC}"
        fi
    fi
}

show_final_status() {
    if [ "$SHOW_STATUS" = true ]; then
        echo ""
        echo -e "${BLUE}📊 Final Service Health Status:${NC}"
        
        for vm_name in "${!HEALTH_URLS[@]}"; do
            health_url=${HEALTH_URLS[$vm_name]}
            test_service_health "$vm_name" "$health_url"
        done
        
        # Test backend
        echo -n "  WSL Backend health check... "
        if curl -s http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Healthy${NC}"
        else
            echo -e "${RED}❌ Unhealthy${NC}"
        fi
    fi
}

# Main execution
echo -e "${GREEN}🚀 AutoBot Native VM - Single Startup Procedure${NC}"
echo -e "${BLUE}=================================================${NC}"
echo ""

# Check prerequisites
check_prerequisites

echo ""
echo -e "${BLUE}🔗 Testing VM Connectivity...${NC}"
connectivity_failed=false
for vm_name in "${!VMS[@]}"; do
    vm_ip=${VMS[$vm_name]}
    test_vm_connectivity "$vm_name" "$vm_ip" || connectivity_failed=true
done

if [ "$connectivity_failed" = true ]; then
    echo -e "${RED}❌ Some VMs are not accessible via SSH${NC}"
    echo -e "${YELLOW}Please ensure all VMs are running and SSH keys are properly configured${NC}"
    exit 1
fi

echo -e "${GREEN}✅ All VMs are accessible${NC}"
echo ""

# Start services
if [ "$PARALLEL_START" = true ]; then
    start_services_parallel
else
    start_services_sequential
fi

echo ""

# Start WSL backend
start_wsl_backend

echo ""

# Test all services health
echo -e "${YELLOW}🏥 Testing service health (waiting for initialization)...${NC}"
sleep 5  # Give services time to fully start

show_final_status

echo ""

# Launch browser
launch_browser

echo ""
echo -e "${GREEN}🎉 AutoBot Native VM Deployment Started Successfully!${NC}"
echo -e "${BLUE}🌐 Access Points:${NC}"
echo "  Frontend:   http://172.16.168.21/"
echo "  Backend:    http://172.16.168.20:8001/"
echo "  AI Stack:   http://172.16.168.24:8080/health"
echo "  NPU Worker: http://172.16.168.22:8081/health"
echo "  Browser:    http://172.16.168.25:3000/health"
echo ""
echo -e "${CYAN}ℹ️  VM services will continue running even after you stop this script${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop WSL backend (VM services will keep running)${NC}"
echo -e "${BLUE}📋 WSL Backend logs:${NC}"
echo ""

# Wait for backend and show logs
wait $BACKEND_PID