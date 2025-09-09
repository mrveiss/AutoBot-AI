#!/bin/bash
# AutoBot - Unified Startup Script
# Supports native VM deployment with all previous features
# Combines functionality from run_agent.sh, run_agent_unified.sh, and native VM scripts

set -e

# CRITICAL FIX: Force tf-keras usage to fix Transformers compatibility with Keras 3
export TF_USE_LEGACY_KERAS=1
export KERAS_BACKEND=tensorflow

# Load unified configuration system
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
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

# VM Configuration for Native Mode (from unified config)
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

# Health Check URLs (from unified config)
declare -A HEALTH_URLS
HEALTH_URLS[frontend]="http://$(get_config "infrastructure.hosts.frontend" 2>/dev/null || echo "172.16.168.21")/"
HEALTH_URLS[npu-worker]="http://$(get_config "infrastructure.hosts.npu_worker" 2>/dev/null || echo "172.16.168.22"):$(get_config "infrastructure.ports.npu_worker" 2>/dev/null || echo "8081")/health"
HEALTH_URLS[redis]="$(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23"):$(get_config "infrastructure.ports.redis" 2>/dev/null || echo "6379")"
HEALTH_URLS[ai-stack]="http://$(get_config "infrastructure.hosts.ai_stack" 2>/dev/null || echo "172.16.168.24"):$(get_config "infrastructure.ports.ai_stack" 2>/dev/null || echo "8080")/health"
HEALTH_URLS[browser]="http://$(get_config "infrastructure.hosts.browser_service" 2>/dev/null || echo "172.16.168.25"):$(get_config "infrastructure.ports.browser_service" 2>/dev/null || echo "3000")/health"

SSH_KEY="$HOME/.ssh/autobot_key"
SSH_USER="autobot"

# Process tracking
BACKEND_PID=""
BROWSER_PID=""
VNC_PID=""

# Default options (matching previous run scripts)
DEV_MODE=false
TEST_MODE=false
DEPLOYMENT_MODE="native-vm"  # Default to native VM
NO_BUILD=false
REBUILD=false
BUILD_DEFAULT=false
NO_BROWSER=false
CLEAN_SHUTDOWN=false
DESKTOP_ACCESS=false  # Disable by default to prevent VNC connection errors
PARALLEL_START=true
SHOW_STATUS=true
FORCE_ENV=""
STOP_SERVICES=false
RESTART_SERVICES=false
SHOW_STATUS_ONLY=false
SHUTDOWN_VMS=false

print_help() {
    echo -e "${GREEN}AutoBot - Unified Startup Script${NC}"
    echo "Supports native VM deployment with full feature set"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo -e "${YELLOW}Development Options:${NC}"
    echo "  --dev           Development mode (hot reload, detailed logging, browser with DevTools)"
    echo "  --test-mode     Test mode (minimal services for testing)"
    echo ""
    echo -e "${YELLOW}Deployment Options:${NC}"
    echo "  --native        Native VM deployment (default)"
    echo "  --docker        Docker container deployment (if available)"
    echo "  --force-env     Force specific environment (native-vm|docker|localhost)"
    echo ""
    echo -e "${YELLOW}Build Options:${NC}"
    echo "  --no-build      Skip building/starting services (use existing)"
    echo "  --build         Force build/restart services even if running"  
    echo "  --rebuild       Force complete rebuild/restart of all services"
    echo ""
    echo -e "${YELLOW}UI Options:${NC}"
    echo "  --no-browser    Don't auto-launch browser"
    echo "  --desktop       Enable desktop access via VNC"
    echo "  --no-desktop    Disable desktop access via VNC (default: disabled)"
    echo ""
    echo -e "${YELLOW}Service Management:${NC}"
    echo "  --stop          Stop all AutoBot services (VMs and WSL backend)"
    echo "  --restart       Stop and restart all AutoBot services"
    echo "  --status        Show detailed status of all services"
    echo "  --shutdown      ⚠️  Shutdown remote VMs (DANGER: Powers off VMs!)"
    echo ""
    echo -e "${YELLOW}Advanced Options:${NC}"
    echo "  --sequential    Start services sequentially instead of parallel"
    echo "  --no-status     Don't show service status after startup"
    echo "  --clean         Remove/stop all services on shutdown"
    echo "  --help          Show this help"
    echo ""
    echo -e "${BLUE}Native VM Architecture (Default):${NC}"
    echo "  Frontend:   $(get_config "infrastructure.hosts.frontend" 2>/dev/null || echo "172.16.168.21") (VM1) - Nginx + Vue.js"
    echo "  NPU Worker: $(get_config "infrastructure.hosts.npu_worker" 2>/dev/null || echo "172.16.168.22") (VM2) - Hardware detection"
    echo "  Redis:      $(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23") (VM3) - Data layer"
    echo "  AI Stack:   $(get_config "infrastructure.hosts.ai_stack" 2>/dev/null || echo "172.16.168.24") (VM4) - AI processing"
    echo "  Browser:    $(get_config "infrastructure.hosts.browser_service" 2>/dev/null || echo "172.16.168.25") (VM5) - Web automation"
    echo "  Backend:    $(get_config "infrastructure.hosts.backend" 2>/dev/null || echo "172.16.168.20") (WSL) - API server"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  $0                    # Standard native VM startup"
    echo "  $0 --dev              # Development mode with debugging"
    echo "  $0 --dev --no-desktop # Dev mode without VNC"
    echo "  $0 --rebuild          # Force restart all services"
    echo "  $0 --test-mode        # Minimal testing setup"
    echo "  $0 --stop             # Stop all services (VMs + WSL backend)"
    echo "  $0 --restart          # Restart all services"
    echo "  $0 --restart --dev    # Restart in development mode"
    echo "  $0 --status           # Show detailed service status"
    echo "  $0 --shutdown         # ⚠️  Power off all VMs (DANGER!)"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --dev)
            DEV_MODE=true
            SHOW_STATUS=true
            shift
            ;;
        --test-mode)
            TEST_MODE=true
            shift
            ;;
        --native)
            DEPLOYMENT_MODE="native-vm"
            shift
            ;;
        --docker)
            DEPLOYMENT_MODE="docker"
            shift
            ;;
        --no-build)
            NO_BUILD=true
            shift
            ;;
        --build)
            BUILD_DEFAULT=true
            shift
            ;;
        --rebuild)
            REBUILD=true
            shift
            ;;
        --no-browser)
            NO_BROWSER=true
            shift
            ;;
        --desktop)
            DESKTOP_ACCESS=true
            shift
            ;;
        --no-desktop)
            DESKTOP_ACCESS=false
            shift
            ;;
        --sequential)
            PARALLEL_START=false
            shift
            ;;
        --no-status)
            SHOW_STATUS=false
            shift
            ;;
        --clean)
            CLEAN_SHUTDOWN=true
            shift
            ;;
        --stop)
            STOP_SERVICES=true
            shift
            ;;
        --restart)
            RESTART_SERVICES=true
            shift
            ;;
        --status)
            SHOW_STATUS_ONLY=true
            shift
            ;;
        --shutdown)
            SHUTDOWN_VMS=true
            shift
            ;;
        --force-env)
            FORCE_ENV="$2"
            shift 2
            ;;
        --help|-h)
            print_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# Override deployment mode if forced
if [ -n "$FORCE_ENV" ]; then
    DEPLOYMENT_MODE="$FORCE_ENV"
fi

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down AutoBot...${NC}"
    
    if [ ! -z "$BACKEND_PID" ]; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill -TERM $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
    fi
    
    if [ ! -z "$BROWSER_PID" ]; then
        echo "Closing browser (PID: $BROWSER_PID)..."
        kill -TERM $BROWSER_PID 2>/dev/null || true
    fi
    
    if [ ! -z "$VNC_PID" ]; then
        echo "Stopping VNC server (PID: $VNC_PID)..."
        kill -TERM $VNC_PID 2>/dev/null || true
    fi
    
    if [ "$CLEAN_SHUTDOWN" = true ] && [ "$DEPLOYMENT_MODE" = "native-vm" ]; then
        echo -e "${YELLOW}Performing clean shutdown of VM services...${NC}"
        stop_all_vm_services
    elif [ "$DEPLOYMENT_MODE" = "native-vm" ]; then
        echo -e "${YELLOW}Note: VM services continue running. Use --clean to stop all services.${NC}"
    fi
    
    echo -e "${GREEN}✅ AutoBot stopped cleanly${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

detect_environment() {
    echo -e "${BLUE}🔍 Detecting Environment...${NC}"
    
    # Check for native VM deployment
    if [ -f ".env.native-vm" ] && [ -f "$SSH_KEY" ]; then
        echo -e "${GREEN}✅ Native VM deployment detected${NC}"
        return 0
    fi
    
    # Check for Docker availability
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Docker available but native VM preferred${NC}"
        if [ "$DEPLOYMENT_MODE" = "docker" ]; then
            echo -e "${BLUE}ℹ️  Using Docker deployment (forced)${NC}"
            return 1
        fi
    fi
    
    echo -e "${RED}❌ Native VM deployment not properly configured${NC}"
    echo "Please run the deployment script first or use --force-env docker"
    exit 1
}

start_vnc_desktop() {
    if [ "$DESKTOP_ACCESS" = true ]; then
        echo -e "${CYAN}🖥️  Starting VNC Desktop Access...${NC}"
        
        # Check if VNC is already running
        if pgrep -f "x11vnc.*:0" >/dev/null 2>&1; then
            echo -e "${YELLOW}⚠️  VNC server already running${NC}"
            return 0
        fi
        
        # Start VNC server (adapted from previous scripts)
        if command -v kex >/dev/null 2>&1; then
            echo "Using Kali Win-KeX for VNC..."
            kex --win --start-client >/dev/null 2>&1 &
            VNC_PID=$!
        elif command -v x11vnc >/dev/null 2>&1; then
            echo "Using x11vnc for desktop access..."
            x11vnc -display :0 -noxdamage -forever -bg -rfbport 5900 >/dev/null 2>&1 &
            VNC_PID=$!
        else
            echo -e "${YELLOW}⚠️  No VNC server available${NC}"
            return 1
        fi
        
        sleep 2
        echo -e "${GREEN}✅ VNC Desktop available at: ${BLUE}http://localhost:6080/vnc.html${NC}"
    fi
}

check_vm_connectivity() {
    echo -e "${BLUE}🔗 Testing VM Connectivity...${NC}"
    local connectivity_failed=false
    
    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        echo -n "  Testing $vm_name ($vm_ip)... "
        
        if timeout 5 ssh -i "$SSH_KEY" -o ConnectTimeout=3 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Connected${NC}"
        else
            echo -e "${RED}❌ Failed${NC}"
            connectivity_failed=true
        fi
    done
    
    if [ "$connectivity_failed" = true ]; then
        echo -e "${RED}❌ Some VMs are not accessible via SSH${NC}"
        echo -e "${YELLOW}Please ensure all VMs are running and SSH keys are properly configured${NC}"
        if [ "$TEST_MODE" = false ]; then
            exit 1
        else
            echo -e "${YELLOW}⚠️  Continuing in test mode despite connectivity issues${NC}"
        fi
    fi
    
    echo -e "${GREEN}✅ All VMs are accessible${NC}"
}

start_vm_service() {
    local vm_name=$1
    local vm_ip=$2
    local service_name=$3
    
    if [ "$DEV_MODE" = true ]; then
        echo -e "${CYAN}🚀 [DEV] Starting $vm_name service with debugging...${NC}"
    else
        echo -e "${CYAN}🚀 Starting $vm_name service...${NC}"
    fi
    
    # Handle different build modes
    local service_action="start"
    if [ "$REBUILD" = true ]; then
        service_action="restart"
        echo "  🔄 Force restarting $service_name..."
    elif [ "$BUILD_DEFAULT" = true ]; then
        # Check if service is running
        if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
            "sudo systemctl is-active $service_name" >/dev/null 2>&1; then
            service_action="restart"
            echo "  🔄 Restarting running $service_name..."
        fi
    elif [ "$NO_BUILD" = true ]; then
        # Check if service is already running
        if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
            "sudo systemctl is-active $service_name" >/dev/null 2>&1; then
            echo -e "${YELLOW}⚠️  $vm_name service already running (skipped)${NC}"
            return 0
        fi
    fi
    
    # Start/restart the service
    local systemctl_output
    systemctl_output=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
        "sudo systemctl $service_action $service_name 2>&1 && sudo systemctl enable $service_name 2>&1" 2>/dev/null)
    local systemctl_result=$?
    
    if [ $systemctl_result -ne 0 ]; then
        # Get more specific error information
        local service_status=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
            "sudo systemctl is-active $service_name 2>/dev/null || echo 'inactive'")
        
        if [ "$service_status" = "active" ]; then
            echo -e "${BLUE}ℹ️  $vm_name service already active${NC}"
        else
            echo -e "${YELLOW}⚠️  $vm_name systemctl $service_action failed - checking status...${NC}"
        fi
    fi
    
    # Wait for service to initialize
    local wait_time=2
    if [ "$DEV_MODE" = true ]; then
        wait_time=5  # Longer wait in dev mode
    fi
    sleep $wait_time
    
    # Check final service status with detailed feedback
    local final_status=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
        "sudo systemctl is-active $service_name 2>/dev/null || echo 'unknown'")
    
    case "$final_status" in
        "active")
            echo -e "${GREEN}✅ $vm_name service running${NC}"
            
            # Show additional info in dev mode
            if [ "$DEV_MODE" = true ]; then
                local uptime=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
                    "sudo systemctl show $service_name --property=ActiveEnterTimestampMonotonic --value" 2>/dev/null || echo "Unknown")
                echo -e "${BLUE}   📊 Service active, uptime data available${NC}"
            fi
            return 0
            ;;
        "activating")
            echo -e "${CYAN}🔄 $vm_name service starting up...${NC}"
            return 0
            ;;
        "inactive"|"failed")
            echo -e "${RED}❌ $vm_name service $final_status - will verify via health check${NC}"
            return 1
            ;;
        *)
            echo -e "${BLUE}ℹ️  $vm_name systemctl status: $final_status - testing health endpoint${NC}"
            return 1
            ;;
    esac
}

start_services_parallel() {
    echo -e "${YELLOW}🌐 Starting Remote VM Services (Parallel)...${NC}"
    
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
    echo -e "${GREEN}✅ VM service startup phase completed${NC}"
    echo -e "${BLUE}ℹ️  Services may still be initializing - health checks will follow${NC}"
}

start_services_sequential() {
    echo -e "${YELLOW}🌐 Starting Remote VM Services (Sequential)...${NC}"
    
    # Start services in dependency order
    local service_order=("redis" "ai-stack" "npu-worker" "browser" "frontend")
    
    for vm_name in "${service_order[@]}"; do
        vm_ip=${VMS[$vm_name]}
        service_name=${SERVICES[$vm_name]}
        start_vm_service "$vm_name" "$vm_ip" "$service_name"
        echo ""
    done
}

check_and_manage_backend_process() {
    # Initialize reuse flag
    REUSED_EXISTING_BACKEND=false
    
    # Load environment first to get correct URLs
    if [ -f ".env.native-vm" ]; then
        set -a
        source ".env.native-vm"  
        set +a
    fi
    
    local backend_health_url="$(get_service_url "backend" 2>/dev/null || echo "http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}")/api/health"
    
    # Check if backend processes are already running
    local existing_pids=$(pgrep -f "fast_app_factory_fix" 2>/dev/null || pgrep -f "uvicorn.*api.main:app" 2>/dev/null || pgrep -f "uvicorn.*--port 8001" 2>/dev/null || true)
    
    if [ -n "$existing_pids" ]; then
        echo -e "${BLUE}🔍 Found existing backend process(es): $existing_pids${NC}"
        
        # Test if existing backend is healthy and responsive
        echo -n "  Testing existing backend health... "
        if timeout 5 curl -s "$backend_health_url" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Healthy${NC}"
            echo -e "${GREEN}🔄 Using existing healthy backend process${NC}"
            
            # Get the main PID for tracking
            BACKEND_PID=$(echo $existing_pids | awk '{print $1}')
            REUSED_EXISTING_BACKEND=true
            return 0
        else
            echo -e "${RED}❌ Unhealthy or unresponsive${NC}"
            echo -e "${YELLOW}🛑 Stopping unhealthy backend process(es)...${NC}"
            
            # Stop unhealthy processes
            for pid in $existing_pids; do
                echo "  Stopping PID $pid..."
                kill -TERM $pid 2>/dev/null || true
            done
            
            # Wait for processes to stop
            sleep 3
            
            # Force kill if still running
            local still_running=$(pgrep -f "fast_app_factory_fix" 2>/dev/null || pgrep -f "uvicorn.*api.main:app" 2>/dev/null || pgrep -f "uvicorn.*--port 8001" 2>/dev/null || true)
            if [ -n "$still_running" ]; then
                echo -e "${YELLOW}  Force killing remaining processes...${NC}"
                pkill -9 -f "fast_app_factory_fix" 2>/dev/null || true
                pkill -9 -f "uvicorn.*api.main:app" 2>/dev/null || true
                pkill -9 -f "uvicorn.*--port 8001" 2>/dev/null || true
                sleep 2
            fi
            
            echo -e "${GREEN}✅ Cleaned up unhealthy backend processes${NC}"
        fi
    else
        echo -e "${BLUE}🔍 No existing backend processes found${NC}"
    fi
    
    return 1  # Need to start new process
}

start_wsl_backend() {
    echo -e "${CYAN}🔧 Starting WSL Backend...${NC}"
    
    # Load native VM configuration
    local env_file=".env.native-vm"
    if [ "$DEV_MODE" = true ]; then
        echo -e "${BLUE}   🛠️  [DEV] Using development configuration${NC}"
        # Could switch to dev-specific env file if needed
    fi
    
    if [ -f "$env_file" ]; then
        set -a
        source "$env_file"
        set +a
    else
        echo -e "${RED}❌ Configuration file not found: $env_file${NC}"
        exit 1
    fi
    
    # Check if we can reuse an existing healthy backend process
    if check_and_manage_backend_process; then
        echo -e "${GREEN}✅ WSL Backend already running and healthy (PID: $BACKEND_PID)${NC}"
        return 0
    fi
    
    # Start new backend process
    echo -e "${BLUE}🚀 Starting new backend process...${NC}"
    
    # Choose backend startup method
    local backend_args=""
    if [ "$DEV_MODE" = true ]; then
        backend_args="--reload --log-level debug"
        echo -e "${BLUE}   🐛 [DEV] Starting backend with hot reload and debug logging${NC}"
    fi
    
    # Start backend
    if [ -f "backend/fast_app_factory_fix.py" ]; then
        echo "Using optimized backend startup..."
        cd backend && PYTHONPATH=/home/kali/Desktop/AutoBot python3 fast_app_factory_fix.py &
    else
        echo "Using standard backend startup..."
        backend_host=${AUTOBOT_BACKEND_HOST:-$(get_config "infrastructure.hosts.backend" 2>/dev/null || echo "172.16.168.20")}
        backend_port=${AUTOBOT_BACKEND_PORT:-8001}
        cd backend && PYTHONPATH=/home/kali/Desktop/AutoBot python3 -m uvicorn api.main:app --host "$backend_host" --port "$backend_port" $backend_args &
    fi
    
    BACKEND_PID=$!
    cd ..
    
    echo -e "${GREEN}✅ WSL Backend started (PID: $BACKEND_PID)${NC}"
    
    # Wait for backend to be ready
    echo -n "Waiting for backend to be ready"
    local max_wait=30
    if [ "$DEV_MODE" = true ]; then
        max_wait=60  # Longer wait in dev mode
    fi
    
    for i in $(seq 1 $max_wait); do
        backend_health_url="http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}/api/health"
        if curl -s "$backend_health_url" >/dev/null 2>&1; then
            echo -e " ${GREEN}✅ Ready!${NC}"
            return 0
        fi
        sleep 1
        echo -n "."
    done
    echo -e " ${YELLOW}⚠️  Backend may need more time${NC}"
}

test_service_health() {
    local vm_name=$1
    local health_url=$2
    
    echo -n "  $vm_name health check... "
    
    if [ "$vm_name" = "redis" ]; then
        # Special case for Redis (TCP connection)
        local redis_host=$(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23")
        local redis_port=$(get_config "infrastructure.ports.redis" 2>/dev/null || echo "6379")
        if echo "PING" | nc -w 2 "$redis_host" "$redis_port" | grep -q "PONG" 2>/dev/null; then
            echo -e "${GREEN}✅ Healthy${NC}"
            return 0
        else
            echo -e "${RED}❌ Unhealthy${NC}"
            return 1
        fi
    else
        # HTTP health check with response time in dev mode
        if [ "$DEV_MODE" = true ]; then
            local response_time=$(timeout 5 curl -w "%{time_total}" -s -o /dev/null "$health_url" 2>/dev/null || echo "timeout")
            if [ "$response_time" != "timeout" ]; then
                echo -e "${GREEN}✅ Healthy (${response_time}s)${NC}"
                return 0
            else
                echo -e "${RED}❌ Unhealthy (timeout)${NC}"
                return 1
            fi
        else
            if timeout 5 curl -s "$health_url" >/dev/null 2>&1; then
                echo -e "${GREEN}✅ Healthy${NC}"
                return 0
            else
                echo -e "${RED}❌ Unhealthy${NC}"
                return 1
            fi
        fi
    fi
}

launch_browser() {
    if [ "$NO_BROWSER" = false ]; then
        echo -e "${CYAN}🌐 Launching AutoBot Application...${NC}"
        
        # Construct the AutoBot application URL (not just frontend root)
        local frontend_base="$(get_service_url "frontend" 2>/dev/null || echo "http://172.16.168.21")"
        local browser_url="${frontend_base}/"  # AutoBot app loads at root
        local browser_args=""
        
        if [ "$DEV_MODE" = true ]; then
            echo -e "${BLUE}   🛠️  [DEV] Opening AutoBot with DevTools${NC}"
            browser_args="--auto-open-devtools-for-tabs"
        else
            echo -e "${BLUE}   🚀 Opening AutoBot interface${NC}"
        fi
        
        # Wait a moment after health checks to ensure frontend is fully ready
        echo -e "${BLUE}   ⏳ Ensuring frontend is ready for AutoBot...${NC}"
        sleep 3
        
        echo -e "${BLUE}   🌐 AutoBot URL: $browser_url${NC}"
        
        if command -v firefox >/dev/null 2>&1; then
            firefox $browser_args "$browser_url" >/dev/null 2>&1 &
            BROWSER_PID=$!
            echo -e "${GREEN}✅ Firefox opened with AutoBot application${NC}"
        elif command -v google-chrome >/dev/null 2>&1; then
            google-chrome $browser_args "$browser_url" >/dev/null 2>&1 &
            BROWSER_PID=$!
            echo -e "${GREEN}✅ Chrome opened with AutoBot application${NC}"
        else
            echo -e "${YELLOW}⚠️  No browser found. Please open AutoBot at: $browser_url${NC}"
        fi
    fi
}

stop_all_vm_services() {
    echo -e "${YELLOW}🛑 Stopping all VM services...${NC}"
    
    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        service_name=${SERVICES[$vm_name]}
        
        echo -n "  Stopping $vm_name ($vm_ip)... "
        
        # Check if VM is reachable first
        if ! timeout 3 ssh -i "$SSH_KEY" -o ConnectTimeout=2 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
            echo -e "${RED}❌ VM Unreachable${NC}"
            continue
        fi
        
        # Check current service status
        local service_status=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
            "sudo systemctl is-active $service_name 2>/dev/null || echo 'inactive'")
        
        if [ "$service_status" = "active" ]; then
            # Stop the service
            if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
                "sudo systemctl stop $service_name" 2>/dev/null; then
                echo -e "${GREEN}✅ Stopped${NC}"
                
                # Verify it stopped
                sleep 1
                local new_status=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
                    "sudo systemctl is-active $service_name 2>/dev/null || echo 'inactive'")
                if [ "$new_status" != "inactive" ]; then
                    echo -e "${YELLOW}    ⚠️  Service may still be stopping${NC}"
                fi
            else
                echo -e "${RED}❌ Stop Failed${NC}"
            fi
        elif [ "$service_status" = "inactive" ]; then
            echo -e "${BLUE}ℹ️  Already Stopped${NC}"
        else
            echo -e "${YELLOW}⚠️  Unknown Status: $service_status${NC}"
        fi
    done
}

stop_wsl_backend() {
    echo -e "${YELLOW}🛑 Stopping WSL Backend...${NC}"
    
    # Find all backend processes (comprehensive search)
    local existing_pids=$(pgrep -f "fast_app_factory_fix" 2>/dev/null || pgrep -f "uvicorn.*api.main:app" 2>/dev/null || pgrep -f "uvicorn.*--port 8001" 2>/dev/null || pgrep -f "python.*backend" 2>/dev/null | head -5 || true)
    
    if [ -n "$existing_pids" ]; then
        echo "  Found backend processes: $existing_pids"
        
        for pid in $existing_pids; do
            echo -n "  Stopping PID $pid... "
            if kill -TERM $pid 2>/dev/null; then
                echo -e "${GREEN}✅ Stopped${NC}"
            else
                echo -e "${YELLOW}⚠️  Already stopped${NC}"
            fi
        done
        
        # Wait for graceful shutdown
        sleep 3
        
        # Force kill if still running
        local still_running=$(pgrep -f "fast_app_factory_fix" 2>/dev/null || pgrep -f "uvicorn.*api.main:app" 2>/dev/null || pgrep -f "uvicorn.*--port 8001" 2>/dev/null || true)
        if [ -n "$still_running" ]; then
            echo -e "${YELLOW}  Force killing remaining processes...${NC}"
            pkill -9 -f "fast_app_factory_fix" 2>/dev/null || true
            pkill -9 -f "uvicorn.*api.main:app" 2>/dev/null || true
            pkill -9 -f "uvicorn.*--port 8001" 2>/dev/null || true
            sleep 1
        fi
        
        echo -e "${GREEN}✅ WSL Backend stopped${NC}"
    else
        echo -e "${BLUE}ℹ️  No WSL backend processes found${NC}"
    fi
}

stop_all_services() {
    echo -e "${RED}🛑 Stopping All AutoBot Services${NC}"
    echo -e "${BLUE}===============================${NC}"
    echo ""
    
    # Stop WSL backend first
    stop_wsl_backend
    echo ""
    
    # Stop VNC if running
    if [ -n "$VNC_PID" ] || pgrep -f "x11vnc.*:0" >/dev/null 2>&1; then
        echo -e "${YELLOW}🛑 Stopping VNC Desktop...${NC}"
        if [ -n "$VNC_PID" ]; then
            kill -TERM $VNC_PID 2>/dev/null || true
        fi
        pkill -f "x11vnc.*:0" 2>/dev/null || true
        pkill -f "kex.*--win" 2>/dev/null || true
        echo -e "${GREEN}✅ VNC Desktop stopped${NC}"
        echo ""
    fi
    
    # Check environment and stop VM services if available
    if [ -f ".env.native-vm" ] && [ -f "$SSH_KEY" ]; then
        echo -e "${BLUE}🔍 Native VM deployment detected${NC}"
        if check_vm_connectivity >/dev/null 2>&1; then
            stop_all_vm_services
        else
            echo -e "${YELLOW}⚠️  Some VMs not accessible, attempting to stop accessible ones${NC}"
            stop_all_vm_services
        fi
    else
        echo -e "${BLUE}ℹ️  Native VM deployment not configured${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}✅ All AutoBot Services Stopped${NC}"
}

restart_all_services() {
    echo -e "${CYAN}🔄 Restarting All AutoBot Services${NC}"
    echo -e "${BLUE}==================================${NC}"
    echo ""
    
    # First stop all services
    stop_all_services
    
    echo ""
    echo -e "${CYAN}⏳ Waiting 5 seconds before restart...${NC}"
    sleep 5
    
    echo ""
    echo -e "${GREEN}🚀 Starting AutoBot Services...${NC}"
    echo -e "${BLUE}==============================${NC}"
    
    # Reset flags for startup
    STOP_SERVICES=false
    RESTART_SERVICES=false
    
    # Continue with normal startup process
}

show_comprehensive_status() {
    echo -e "${BLUE}📊 AutoBot Service Status Report${NC}"
    echo -e "${BLUE}=================================${NC}"
    echo ""
    
    # WSL Backend Status
    echo -e "${CYAN}🖥️  WSL Backend:${NC}"
    local backend_pids=$(pgrep -f "fast_app_factory_fix" 2>/dev/null || pgrep -f "uvicorn.*api.main:app" 2>/dev/null || pgrep -f "uvicorn.*--port 8001" 2>/dev/null || true)
    if [ -n "$backend_pids" ]; then
        echo "  Process(es): $backend_pids"
        for pid in $backend_pids; do
            local cpu_mem=$(ps -p $pid -o pid,pcpu,pmem,etime,cmd --no-headers 2>/dev/null || echo "Process info unavailable")
            echo -e "${BLUE}    [$pid] $cpu_mem${NC}"
        done
        
        # Test backend health
        local backend_health_url="$(get_service_url "backend" 2>/dev/null || echo "http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}")/api/health"
        echo -n "  Health Check: "
        if timeout 5 curl -s "$backend_health_url" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Healthy${NC}"
        else
            echo -e "${RED}❌ Unhealthy${NC}"
        fi
    else
        echo -e "${YELLOW}  ⚠️  No backend processes found${NC}"
    fi
    echo ""
    
    # VM Services Status
    echo -e "${CYAN}🌐 Remote VM Services:${NC}"
    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        service_name=${SERVICES[$vm_name]}
        
        echo "  $vm_name ($vm_ip):"
        
        # VM connectivity
        echo -n "    Connectivity: "
        if timeout 3 ssh -i "$SSH_KEY" -o ConnectTimeout=2 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Reachable${NC}"
            
            # Service status
            local service_status=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
                "sudo systemctl is-active $service_name 2>/dev/null || echo 'unknown'")
            echo -n "    Service: "
            case "$service_status" in
                "active")
                    echo -e "${GREEN}✅ Running${NC}"
                    # Get service uptime
                    local uptime=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
                        "sudo systemctl show $service_name --property=ActiveEnterTimestamp --value" 2>/dev/null || echo "Unknown")
                    echo -e "${BLUE}      Started: $uptime${NC}"
                    ;;
                "inactive")
                    echo -e "${YELLOW}⚠️  Stopped${NC}"
                    ;;
                "failed")
                    echo -e "${RED}❌ Failed${NC}"
                    ;;
                *)
                    echo -e "${YELLOW}⚠️  $service_status${NC}"
                    ;;
            esac
            
            # System resource usage
            local resources=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
                "free -h | grep '^Mem:' && df -h / | tail -1" 2>/dev/null | tr '\n' ' ' || echo "Resource info unavailable")
            echo -e "${BLUE}      Resources: $resources${NC}"
            
            # Test health endpoint if available
            if [ -n "${HEALTH_URLS[$vm_name]:-}" ]; then
                echo -n "    Health: "
                test_service_health "$vm_name" "${HEALTH_URLS[$vm_name]}" | tail -1
            fi
            
        else
            echo -e "${RED}❌ Unreachable${NC}"
            echo -e "${YELLOW}      Service: Unknown (VM offline)${NC}"
        fi
        echo ""
    done
    
    # VNC Desktop Status
    echo -e "${CYAN}🖥️  VNC Desktop:${NC}"
    if pgrep -f "x11vnc.*:0" >/dev/null 2>&1 || pgrep -f "kex.*--win" >/dev/null 2>&1; then
        echo -e "${GREEN}  ✅ VNC Server Running${NC}"
        local vnc_pid=$(pgrep -f "x11vnc.*:0" 2>/dev/null || pgrep -f "kex.*--win" 2>/dev/null || echo "unknown")
        echo -e "${BLUE}    PID: $vnc_pid${NC}"
        echo -e "${BLUE}    URL: http://localhost:6080/vnc.html${NC}"
    else
        echo -e "${YELLOW}  ⚠️  VNC Server Not Running${NC}"
    fi
    echo ""
    
    # Summary
    local total_services=$((${#VMS[@]} + 1))  # VMs + WSL backend
    local healthy_count=0
    
    # Count healthy services
    if [ -n "$backend_pids" ]; then
        ((healthy_count++))
    fi
    
    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        service_name=${SERVICES[$vm_name]}
        if timeout 3 ssh -i "$SSH_KEY" -o ConnectTimeout=2 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
            "sudo systemctl is-active $service_name" >/dev/null 2>&1; then
            ((healthy_count++))
        fi
    done
    
    echo -e "${BLUE}📋 Summary: $healthy_count/$total_services services healthy${NC}"
    if [ $healthy_count -eq $total_services ]; then
        echo -e "${GREEN}🎉 All services are operational!${NC}"
    elif [ $healthy_count -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Some services need attention${NC}"
    else
        echo -e "${RED}❌ System appears to be down${NC}"
    fi
}

shutdown_remote_vms() {
    echo -e "${RED}⚠️  VM SHUTDOWN WARNING ⚠️${NC}"
    echo -e "${YELLOW}This will power off all remote VMs. They must be manually started again.${NC}"
    echo -e "${YELLOW}Services will stop and VMs will be completely powered down.${NC}"
    echo ""
    echo -n "Are you sure you want to shutdown all VMs? (type 'yes' to confirm): "
    read -r confirmation
    
    if [ "$confirmation" != "yes" ]; then
        echo -e "${BLUE}ℹ️  VM shutdown cancelled${NC}"
        return 0
    fi
    
    echo ""
    echo -e "${RED}🔌 Shutting Down Remote VMs${NC}"
    echo -e "${BLUE}===========================${NC}"
    echo ""
    
    # First stop services gracefully
    echo -e "${YELLOW}🛑 Stopping services before shutdown...${NC}"
    stop_all_vm_services
    echo ""
    
    # Wait a bit for services to stop
    echo -e "${CYAN}⏳ Waiting 10 seconds for services to stop cleanly...${NC}"
    sleep 10
    
    # Now shutdown VMs
    echo -e "${RED}🔌 Powering down VMs...${NC}"
    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        
        echo -n "  Shutting down $vm_name ($vm_ip)... "
        
        # Check if VM is still reachable
        if ! timeout 3 ssh -i "$SSH_KEY" -o ConnectTimeout=2 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
            echo -e "${YELLOW}⚠️  VM already unreachable${NC}"
            continue
        fi
        
        # Send shutdown command
        if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
            "sudo shutdown -h now" 2>/dev/null; then
            echo -e "${GREEN}✅ Shutdown Command Sent${NC}"
        else
            echo -e "${RED}❌ Shutdown Failed${NC}"
            echo -e "${YELLOW}      Trying alternative shutdown method...${NC}"
            ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
                "sudo poweroff" 2>/dev/null && \
            echo -e "${GREEN}      ✅ Alternative shutdown sent${NC}" || \
            echo -e "${RED}      ❌ All shutdown methods failed${NC}"
        fi
    done
    
    echo ""
    echo -e "${YELLOW}⏳ VMs are shutting down. This may take 1-2 minutes.${NC}"
    echo -e "${BLUE}ℹ️  To start VMs again, use your hypervisor or physical power buttons.${NC}"
    echo -e "${GREEN}✅ VM Shutdown Process Completed${NC}"
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
        echo -n "  Main Machine (WSL Backend) health check... "
        local backend_health_url="$(get_service_url "backend" 2>/dev/null || echo "http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}")/api/health"
        local backend_response=$(curl -s "$backend_health_url" 2>/dev/null || echo "")
        if [ -n "$backend_response" ]; then
            echo -e "${GREEN}✅ Healthy${NC}"
            if [ "$DEV_MODE" = true ]; then
                echo -e "${BLUE}     Response: ${backend_response}${NC}"
            fi
        else
            echo -e "${RED}❌ Unhealthy${NC}"
        fi
    fi
}

# Main execution starts here
echo -e "${GREEN}🚀 AutoBot - Unified Startup Script${NC}"
echo -e "${BLUE}====================================${NC}"

# Handle management operations first
if [ "$STOP_SERVICES" = true ]; then
    stop_all_services
    exit 0
fi

if [ "$SHOW_STATUS_ONLY" = true ]; then
    show_comprehensive_status
    exit 0
fi

if [ "$SHUTDOWN_VMS" = true ]; then
    shutdown_remote_vms
    exit 0
fi

if [ "$RESTART_SERVICES" = true ]; then
    restart_all_services
    # Continue with normal startup after restart
fi

if [ "$DEV_MODE" = true ]; then
    echo -e "${YELLOW}🛠️  Development Mode Enabled${NC}"
    echo -e "${BLUE}   - Hot reload enabled${NC}"
    echo -e "${BLUE}   - Debug logging enabled${NC}"
    echo -e "${BLUE}   - Browser DevTools enabled${NC}"
    echo -e "${BLUE}   - Extended timeouts${NC}"
    echo ""
fi

if [ "$TEST_MODE" = true ]; then
    echo -e "${YELLOW}🧪 Test Mode Enabled${NC}"
    echo -e "${BLUE}   - Minimal service validation${NC}"
    echo -e "${BLUE}   - Continue on non-critical errors${NC}"
    echo ""
fi

echo -e "${BLUE}📋 Deployment Mode: ${YELLOW}$DEPLOYMENT_MODE${NC}"
echo ""
echo -e "${CYAN}🖥️  Infrastructure Overview:${NC}"
echo -e "${BLUE}  📡 Main Machine (WSL):    $(get_config "infrastructure.hosts.backend" 2>/dev/null || echo "172.16.168.20") - Backend API${NC}"
echo -e "${BLUE}  🌐 Remote VMs:${NC}"
echo -e "${BLUE}    VM1 Frontend:    $(get_config "infrastructure.hosts.frontend" 2>/dev/null || echo "172.16.168.21") - Web interface${NC}"
echo -e "${BLUE}    VM2 NPU Worker:  $(get_config "infrastructure.hosts.npu_worker" 2>/dev/null || echo "172.16.168.22") - Hardware AI${NC}"
echo -e "${BLUE}    VM3 Redis:       $(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23") - Data layer${NC}"
echo -e "${BLUE}    VM4 AI Stack:    $(get_config "infrastructure.hosts.ai_stack" 2>/dev/null || echo "172.16.168.24") - AI processing${NC}"
echo -e "${BLUE}    VM5 Browser:     $(get_config "infrastructure.hosts.browser_service" 2>/dev/null || echo "172.16.168.25") - Web automation${NC}"
echo ""

# Environment detection and setup
if [ "$DEPLOYMENT_MODE" = "native-vm" ]; then
    detect_environment
    
    # Check prerequisites
    if [ ! -f "$SSH_KEY" ]; then
        echo -e "${RED}❌ SSH key not found: $SSH_KEY${NC}"
        echo "Please run the deployment script first to set up SSH keys."
        exit 1
    fi
    
    echo -e "${GREEN}✅ SSH key found${NC}"
    echo -e "${GREEN}✅ Configuration found${NC}"
    echo ""
    
    # Check VM connectivity
    check_vm_connectivity
    echo ""
    
    # Start VNC desktop if enabled
    start_vnc_desktop
    echo ""
    
    # Start VM services
    if [ "$PARALLEL_START" = true ]; then
        start_services_parallel
    else
        start_services_sequential
    fi
    
    echo ""
    
    # Start WSL backend
    echo -e "${CYAN}📡 Starting Main Machine (WSL) Services...${NC}"
    start_wsl_backend
    
    echo ""
    
    # Test all services health
    echo -e "${YELLOW}🏥 Final Health Verification Phase${NC}"
    health_wait=5
    if [ "$DEV_MODE" = true ]; then
        health_wait=10  # Longer wait in dev mode
        echo -e "${BLUE}   ⏳ Allowing ${health_wait}s for service initialization (dev mode)${NC}"
    else
        echo -e "${BLUE}   ⏳ Allowing ${health_wait}s for service initialization${NC}"
    fi
    sleep $health_wait
    echo -e "${CYAN}   🔍 Testing all service endpoints...${NC}"
    
    show_final_status
    
    echo ""
    
    # Launch browser AFTER all health checks are complete
    launch_browser
    
else
    echo -e "${RED}❌ Docker deployment not implemented in this version${NC}"
    echo "Use --native or remove --docker flag"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 AutoBot Started Successfully!${NC}"
echo -e "${BLUE}🌐 Service Access Points:${NC}"
echo -e "${CYAN}  📡 Main Machine (WSL):${NC}"
echo "    Backend API:  $(get_service_url "backend" 2>/dev/null || echo "http://172.16.168.20:8001")/"
if [ "$DESKTOP_ACCESS" = true ] && [ -n "$VNC_PID" ]; then
    echo "    VNC Desktop: http://localhost:6080/vnc.html"
fi
echo -e "${CYAN}  🌐 Remote VMs:${NC}"
echo "    Frontend:    $(get_service_url "frontend" 2>/dev/null || echo "http://172.16.168.21")/"
echo "    NPU Worker:  $(get_service_url "npu_worker" 2>/dev/null || echo "http://172.16.168.22:8081")/health"
echo "    Redis Stack: $(get_service_url "redis" 2>/dev/null || echo "redis://172.16.168.23:6379") (Data layer)"
echo "    AI Stack:    $(get_service_url "ai_stack" 2>/dev/null || echo "http://172.16.168.24:8080")/health"
echo "    Browser:     $(get_service_url "browser_service" 2>/dev/null || echo "http://172.16.168.25:3000")/health"

echo ""
echo -e "${CYAN}📊 Infrastructure Summary:${NC}"
echo -e "${BLUE}  Total Machines: 6 (1 Main WSL + 5 Remote VMs)${NC}"
echo -e "${BLUE}  Network Architecture: Distributed Multi-VM${NC}"
echo -e "${BLUE}  Configuration: Centralized (config/complete.yaml)${NC}"
echo ""
if [ "$DEV_MODE" = true ]; then
    echo -e "${CYAN}🛠️  Development Features Active:${NC}"
    echo "  - Backend hot reload enabled"
    echo "  - Browser DevTools opened"
    echo "  - Debug logging active"
    echo "  - Extended health monitoring"
    echo ""
fi

echo -e "${CYAN}ℹ️  VM services will continue running even after you stop this script${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop WSL backend (VM services will keep running)${NC}"
if [ "$CLEAN_SHUTDOWN" = true ]; then
    echo -e "${YELLOW}Clean shutdown enabled - all services will be stopped on exit${NC}"
fi

echo ""
if [ "$DEV_MODE" = true ]; then
    echo -e "${BLUE}📋 WSL Backend Development Logs (Ctrl+C to stop):${NC}"
else
    echo -e "${BLUE}📋 WSL Backend Logs (Ctrl+C to stop):${NC}"
fi
echo ""

# Wait for backend and show logs
if [ "$REUSED_EXISTING_BACKEND" = true ]; then
    # For reused processes, monitor them instead of waiting
    echo "Monitoring existing backend process (PID: $BACKEND_PID)..."
    while kill -0 $BACKEND_PID 2>/dev/null; do
        sleep 5
    done
    echo "Backend process (PID: $BACKEND_PID) has stopped"
else
    # For new processes started by this shell, we can use wait
    wait $BACKEND_PID
fi