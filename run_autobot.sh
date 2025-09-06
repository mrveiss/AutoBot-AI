#!/bin/bash
# AutoBot - Unified Startup Script
# Supports native VM deployment with all previous features
# Combines functionality from run_agent.sh, run_agent_unified.sh, and native VM scripts

set -e

# CRITICAL FIX: Force tf-keras usage to fix Transformers compatibility with Keras 3
export TF_USE_LEGACY_KERAS=1
export KERAS_BACKEND=tensorflow

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# VM Configuration for Native Mode
declare -A VMS
VMS[frontend]="172.16.168.21"
VMS[npu-worker]="172.16.168.22" 
VMS[redis]="172.16.168.23"
VMS[ai-stack]="172.16.168.24"
VMS[browser]="172.16.168.25"

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
DESKTOP_ACCESS=true  # Enable by default like before
PARALLEL_START=true
SHOW_STATUS=true
FORCE_ENV=""

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
    echo "  --desktop       Enable desktop access via VNC (default: enabled)"
    echo "  --no-desktop    Disable desktop access via VNC"
    echo ""
    echo -e "${YELLOW}Advanced Options:${NC}"
    echo "  --sequential    Start services sequentially instead of parallel"
    echo "  --no-status     Don't show service status after startup"
    echo "  --clean         Remove/stop all services on shutdown"
    echo "  --help          Show this help"
    echo ""
    echo -e "${BLUE}Native VM Architecture (Default):${NC}"
    echo "  Frontend:   172.16.168.21 (VM1) - Nginx + Vue.js"
    echo "  NPU Worker: 172.16.168.22 (VM2) - Hardware detection"
    echo "  Redis:      172.16.168.23 (VM3) - Data layer"
    echo "  AI Stack:   172.16.168.24 (VM4) - AI processing"
    echo "  Browser:    172.16.168.25 (VM5) - Web automation"
    echo "  Backend:    172.16.168.20 (WSL) - API server"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  $0                    # Standard native VM startup"
    echo "  $0 --dev              # Development mode with debugging"
    echo "  $0 --dev --no-desktop # Dev mode without VNC"
    echo "  $0 --rebuild          # Force restart all services"
    echo "  $0 --test-mode        # Minimal testing setup"
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
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
        "sudo systemctl $service_action $service_name && sudo systemctl enable $service_name" 2>/dev/null || {
        echo -e "${YELLOW}⚠️  Service may already be running or needs manual attention${NC}"
    }
    
    # Wait for service to initialize
    local wait_time=2
    if [ "$DEV_MODE" = true ]; then
        wait_time=5  # Longer wait in dev mode
    fi
    sleep $wait_time
    
    # Check service status
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
        "sudo systemctl is-active $service_name" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ $vm_name service started successfully${NC}"
        
        # Show additional info in dev mode
        if [ "$DEV_MODE" = true ]; then
            local memory=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
                "systemctl show $service_name --property=MemoryMax,MemoryCurrent" 2>/dev/null || echo "Memory info unavailable")
            echo -e "${BLUE}   📊 $memory${NC}"
        fi
        
        return 0
    else
        echo -e "${YELLOW}⚠️  $vm_name service status unclear, will test health endpoint${NC}"
        return 1
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

check_and_manage_backend_process() {
    # Initialize reuse flag
    REUSED_EXISTING_BACKEND=false
    
    # Load environment first to get correct URLs
    if [ -f ".env.native-vm" ]; then
        set -a
        source ".env.native-vm"  
        set +a
    fi
    
    local backend_health_url="http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}/api/health"
    
    # Check if backend processes are already running
    local existing_pids=$(pgrep -f "fast_app_factory_fix.py" 2>/dev/null || pgrep -f "uvicorn.*api.main:app" 2>/dev/null || true)
    
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
            local still_running=$(pgrep -f "fast_app_factory_fix.py" 2>/dev/null || pgrep -f "uvicorn.*api.main:app" 2>/dev/null || true)
            if [ -n "$still_running" ]; then
                echo -e "${YELLOW}  Force killing remaining processes...${NC}"
                pkill -9 -f "fast_app_factory_fix.py" 2>/dev/null || true
                pkill -9 -f "uvicorn.*api.main:app" 2>/dev/null || true
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
        backend_host=${AUTOBOT_BACKEND_HOST:-172.16.168.20}
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
        if echo "PING" | nc -w 2 172.16.168.23 6379 | grep -q "PONG" 2>/dev/null; then
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
        echo -e "${CYAN}🌐 Launching browser...${NC}"
        sleep 2  # Give services a moment to fully initialize
        
        local browser_url="http://172.16.168.21/"
        local browser_args=""
        
        if [ "$DEV_MODE" = true ]; then
            echo -e "${BLUE}   🛠️  [DEV] Opening browser with DevTools${NC}"
            browser_args="--auto-open-devtools-for-tabs"
        fi
        
        if command -v firefox >/dev/null 2>&1; then
            firefox $browser_args "$browser_url" >/dev/null 2>&1 &
            BROWSER_PID=$!
            echo -e "${GREEN}✅ Firefox launched${NC}"
        elif command -v google-chrome >/dev/null 2>&1; then
            google-chrome $browser_args "$browser_url" >/dev/null 2>&1 &
            BROWSER_PID=$!
            echo -e "${GREEN}✅ Chrome launched${NC}"
        else
            echo -e "${YELLOW}⚠️  No browser found. Please open $browser_url manually${NC}"
        fi
    fi
}

stop_all_vm_services() {
    echo -e "${YELLOW}🛑 Stopping all VM services...${NC}"
    
    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        service_name=${SERVICES[$vm_name]}
        
        echo -n "  Stopping $vm_name... "
        ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" \
            "sudo systemctl stop $service_name" 2>/dev/null && \
        echo -e "${GREEN}✅ Stopped${NC}" || \
        echo -e "${YELLOW}⚠️  May already be stopped${NC}"
    done
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
        local backend_health_url="http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}/api/health"
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
    start_wsl_backend
    
    echo ""
    
    # Test all services health
    echo -e "${YELLOW}🏥 Testing service health (waiting for initialization)...${NC}"
    health_wait=5
    if [ "$DEV_MODE" = true ]; then
        health_wait=10  # Longer wait in dev mode
    fi
    sleep $health_wait
    
    show_final_status
    
else
    echo -e "${RED}❌ Docker deployment not implemented in this version${NC}"
    echo "Use --native or remove --docker flag"
    exit 1
fi

echo ""

# Launch browser
launch_browser

echo ""
echo -e "${GREEN}🎉 AutoBot Started Successfully!${NC}"
echo -e "${BLUE}🌐 Access Points:${NC}"
echo "  Frontend:   http://172.16.168.21/"
echo "  Backend:    http://172.16.168.20:8001/"
echo "  AI Stack:   http://172.16.168.24:8080/health"
echo "  NPU Worker: http://172.16.168.22:8081/health"
echo "  Browser:    http://172.16.168.25:3000/health"

if [ "$DESKTOP_ACCESS" = true ] && [ -n "$VNC_PID" ]; then
    echo "  VNC Desktop: http://localhost:6080/vnc.html"
fi

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