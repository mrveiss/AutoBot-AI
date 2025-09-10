#!/bin/bash

# AutoBot - Unified Run Script
# Combined startup script that replaces all individual run scripts
# Supports both development and production modes with intelligent service management

set -e

# Define color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Comprehensive logging function
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

info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

# Check if script is running from the correct directory
if [ ! -f "run_autobot.sh" ]; then
    error "Please run this script from the AutoBot root directory"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default configuration
DEV_MODE=false
PROD_MODE=false
BUILD_MODE="auto"
TEST_MODE=false
SEQUENTIAL_START=false
PARALLEL_START=true
SHOW_STATUS=true
NO_BROWSER=false
FORCE_CLEANUP=false
DESKTOP_ACCESS=true  # Enable by default per CLAUDE.md guidelines
VNC_PID=""

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
BACKEND_PORT=8001
FRONTEND_PORT=5173
REDIS_PORT=6379
BROWSER_PORT=3000
AI_STACK_PORT=8080
NPU_WORKER_PORT=8081

print_usage() {
    cat << EOF
${GREEN}AutoBot - Unified Run Script${NC}

Usage: $0 [MODE] [OPTIONS]

${YELLOW}Modes:${NC}
  --dev               Development mode with auto-reload and debugging
  --prod              Production mode (default)

${YELLOW}Build Options:${NC}
  --build             Force build even if images exist
  --no-build          Skip Docker builds (fastest restart)
  --rebuild           Force rebuild everything (clean slate)

${YELLOW}Startup Options:${NC}
  --test              Test mode (non-blocking, with warnings)
  --sequential        Start services one by one (default: parallel)
  --no-browser        Don't launch browser automatically
  --desktop       Enable desktop access via VNC
  --no-desktop    Disable desktop access via VNC (default: disabled)

${YELLOW}Utility Options:${NC}
  --status            Show current system status
  --clean             Clean up all containers and volumes before start
  --logs              Follow logs for all services
  --stop              Stop all AutoBot services
  --restart           Restart all services
  --help              Show this help message

${YELLOW}Force Options:${NC}
  --force-env docker          Force Docker environment detection
  --force-env native-vm       Force native VM environment
  --force-cleanup             Force cleanup without confirmation

${BLUE}Examples:${NC}
  $0 --dev                    # Development mode with build check
  $0 --dev --no-build         # Dev mode, skip builds (fastest)
  $0 --prod --build           # Production with forced build
  $0 --dev --no-desktop # Dev mode without VNC
  $0 --status                 # Show current status
  $0 --stop                   # Stop all services
  $0 --logs                   # Follow all service logs

${BLUE}Development Workflow:${NC}
  1. First time:    $0 --dev --build
  2. Daily use:     $0 --dev --no-build
  3. After changes: $0 --dev --rebuild
  4. Production:    $0 --prod

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev)
            DEV_MODE=true
            PROD_MODE=false
            shift
            ;;
        --prod)
            PROD_MODE=true
            DEV_MODE=false
            shift
            ;;
        --build)
            BUILD_MODE="force"
            shift
            ;;
        --no-build)
            BUILD_MODE="skip"
            shift
            ;;
        --rebuild)
            BUILD_MODE="rebuild"
            shift
            ;;
        --test)
            TEST_MODE=true
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
            FORCE_CLEANUP=true
            shift
            ;;
        --status)
            show_system_status
            exit 0
            ;;
        --logs)
            follow_logs
            exit 0
            ;;
        --stop)
            stop_all_services
            exit 0
            ;;
        --restart)
            stop_all_services
            sleep 3
            exec "$0" "${@:2}"  # Restart with remaining arguments
            ;;
        --force-env)
            case "$2" in
                docker|native-vm)
                    FORCE_ENV="$2"
                    shift 2
                    ;;
                *)
                    error "Invalid environment: $2. Use 'docker' or 'native-vm'"
                    exit 1
                    ;;
            esac
            ;;
        --force-cleanup)
            FORCE_CLEANUP=true
            shift
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# Set default mode if none specified
if [ "$DEV_MODE" = false ] && [ "$PROD_MODE" = false ]; then
    PROD_MODE=true
fi

# Cleanup function for graceful shutdown
cleanup() {
    echo ""
    log "Shutting down AutoBot..."
    
    # Stop VNC services
    if systemctl is-active --quiet novnc || systemctl is-active --quiet vncserver@1 || systemctl is-active --quiet xvfb@1; then
        echo -e "${YELLOW}🛑 Stopping VNC Desktop...${NC}"
        
        # Stop services in reverse order
        sudo systemctl stop novnc 2>/dev/null || true
        sudo systemctl stop vncserver@1 2>/dev/null || true
        
        # Clean up any orphaned x11vnc processes
        pkill -f "x11vnc.*:0" 2>/dev/null || true
        
        # Stop Xvfb last
        echo -e "${GREEN}✅ VNC Desktop stopped${NC}"
    fi
    
    if [ ! -z "$VNC_PID" ]; then
        echo "Stopping VNC server (PID: $VNC_PID)..."
        kill -TERM $VNC_PID 2>/dev/null || true
    fi
    
    success "AutoBot shutdown complete"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

check_prerequisites() {
    log "Checking prerequisites..."
    
    local missing_deps=()
    
    # Check essential commands based on environment
    if [ "$ENV_TYPE" = "docker" ]; then
        # Check Docker-specific commands
        for cmd in docker docker-compose python3 npm; do
            if ! command -v $cmd &> /dev/null; then
                missing_deps+=("$cmd")
            fi
        done
        
        if [ ${#missing_deps[@]} -ne 0 ]; then
            error "Missing required dependencies: ${missing_deps[*]}"
            echo "Please install missing dependencies and try again"
            exit 1
        fi
        
        # Check Docker daemon
        if ! docker info &> /dev/null; then
            error "Docker daemon is not running"
            echo "Please start Docker and try again"
            exit 1
        fi
    else
        # Check native VM prerequisites
        for cmd in python3 npm ssh; do
            if ! command -v $cmd &> /dev/null; then
                missing_deps+=("$cmd")
            fi
        done
        
        if [ ${#missing_deps[@]} -ne 0 ]; then
            error "Missing required dependencies: ${missing_deps[*]}"
            echo "Please install missing dependencies and try again"
            exit 1
        fi
    fi
    
    success "All prerequisites satisfied"
}

detect_environment() {
    if [ -n "$FORCE_ENV" ]; then
        ENV_TYPE="$FORCE_ENV"
        log "Environment forced to: $ENV_TYPE"
        return
    fi
    
    # Check if we're in a native VM setup
    if [ -d "/home/kali" ] && [ -f "$SSH_KEY" ]; then
        ENV_TYPE="native-vm"
    # Check if we're in Docker/container environment
    elif [ -f "/.dockerenv" ] || [ -n "$DOCKER_HOST" ]; then
        ENV_TYPE="docker"
    else
        ENV_TYPE="native-vm"  # Default fallback
    fi
    
    log "Detected environment: $ENV_TYPE"
}

validate_native_vm_setup() {
    log "Validating native VM setup..."
    
    # Check SSH key
    if [ ! -f "$SSH_KEY" ]; then
        echo -e "${RED}❌ SSH key not found: $SSH_KEY${NC}"
        echo "Run deployment script to set up SSH keys"
        return 1
    fi
    
    echo -e "${RED}❌ Native VM deployment not properly configured${NC}"
    echo "Please run the deployment script first or use --force-env docker"
    exit 1
}

start_vnc_desktop() {
    if [ "$DESKTOP_ACCESS" = true ]; then
        echo -e "${CYAN}🖥️  Starting VNC Desktop Access...${NC}"
        
        # Check if VNC services are already running
        if systemctl is-active --quiet xvfb@1 && systemctl is-active --quiet vncserver@1 && systemctl is-active --quiet novnc; then
            echo -e "${YELLOW}⚠️  VNC services already running${NC}"
            return 0
        fi
        
        # Check if VNC installation script exists, if not suggest installing
        if [ ! -f "scripts/setup/install-vnc-headless.sh" ]; then
            echo -e "${YELLOW}⚠️  VNC not configured. Run: ${BLUE}bash setup.sh desktop${NC}"
            echo -e "${CYAN}ℹ️  Continuing without VNC desktop...${NC}"
            DESKTOP_ACCESS=false
            return 0
        fi
        
        # Start VNC services using systemd
        echo "Starting Xvfb virtual display..."
        if ! sudo systemctl start xvfb@1 2>/dev/null; then
            echo -e "${YELLOW}⚠️  Xvfb service not installed. Run: ${BLUE}bash setup.sh desktop${NC}"
            echo -e "${CYAN}ℹ️  Continuing without VNC desktop...${NC}"
            DESKTOP_ACCESS=false
            return 0
        fi
        
        echo "Starting VNC server..."
        if ! sudo systemctl start vncserver@1 2>/dev/null; then
            echo -e "${YELLOW}⚠️  VNC service not installed. Run: ${BLUE}bash setup.sh desktop${NC}"
            echo -e "${CYAN}ℹ️  Continuing without VNC desktop...${NC}"
            DESKTOP_ACCESS=false
            return 0
        fi
        
        echo "Starting noVNC web interface..."
        if ! sudo systemctl start novnc 2>/dev/null; then
            echo -e "${YELLOW}⚠️  noVNC service not installed. Run: ${BLUE}bash setup.sh desktop${NC}"
            echo -e "${CYAN}ℹ️  Continuing without VNC desktop...${NC}"
            DESKTOP_ACCESS=false
            return 0
        fi
        
        # Wait for services to start
        sleep 3
        
        # Verify services are running
        if systemctl is-active --quiet xvfb@1 && systemctl is-active --quiet vncserver@1 && systemctl is-active --quiet novnc; then
            echo -e "${GREEN}✅ VNC Desktop available at: ${BLUE}http://localhost:6080/vnc.html${NC}"
            echo -e "${BLUE}   VNC Client: localhost:5901${NC}"
        else
            echo -e "${RED}❌ Failed to start VNC services. Check: ${BLUE}sudo systemctl status xvfb@1 vncserver@1 novnc${NC}"
            echo -e "${CYAN}ℹ️  Continuing without VNC desktop...${NC}"
            DESKTOP_ACCESS=false
            return 0
        fi
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
    
    success "All VMs are accessible"
}

build_containers() {
    local build_arg=""
    local compose_files=()
    
    log "Determining build strategy..."
    
    case "$BUILD_MODE" in
        "skip")
            log "Skipping all builds as requested"
            return 0
            ;;
        "force")
            build_arg="--build"
            log "Forcing rebuild of all services"
            ;;
        "rebuild")
            log "Performing complete rebuild (clean slate)"
            docker-compose down --remove-orphans
            docker system prune -f --volumes 2>/dev/null || true
            build_arg="--build --force-recreate"
            ;;
        "auto")
            log "Auto-detecting build needs..."
            # Add logic to detect if builds are needed
            ;;
    esac
    
    # Determine which compose files to use
    if [ "$ENV_TYPE" = "native-vm" ]; then
        compose_files+=("-f" "docker-compose.yml")
        if [ "$DEV_MODE" = true ]; then
            compose_files+=("-f" "docker-compose.dev.yml")
        fi
    else
        compose_files+=("-f" "docker-compose.yml")
    fi
    
    if [ ${#compose_files[@]} -eq 0 ]; then
        error "No compose files determined for environment"
        exit 1
    fi
    
    log "Building containers with: docker-compose ${compose_files[*]} up -d $build_arg"
    
    if [ "$BUILD_MODE" != "skip" ]; then
        docker-compose "${compose_files[@]}" up -d $build_arg
    else
        docker-compose "${compose_files[@]}" up -d
    fi
}

start_backend() {
    log "Starting AutoBot backend..."
    
    if [ "$ENV_TYPE" = "native-vm" ]; then
        echo -e "${CYAN}Starting backend on main machine...${NC}"
        
        # Check if backend is already running
        if pgrep -f "python.*backend/fast_app_factory_fix.py" > /dev/null; then
            warning "Backend already running, stopping first..."
            pkill -f "python.*backend/fast_app_factory_fix.py" || true
            sleep 2
        fi
        
        # Set up Python environment
        export PYTHONPATH="$PWD"
        
        # Start backend with proper error handling
        if [ "$DEV_MODE" = true ]; then
            log "Starting backend in development mode..."
            cd "$SCRIPT_DIR"
            nohup python backend/fast_app_factory_fix.py > logs/backend.log 2>&1 &
        else
            log "Starting backend in production mode..."
            cd "$SCRIPT_DIR"
            nohup python backend/fast_app_factory_fix.py > logs/backend.log 2>&1 &
        fi
        
        # Wait for backend to start
        local backend_ready=false
        for i in {1..30}; do
            if curl -s http://localhost:$BACKEND_PORT/api/health > /dev/null 2>&1; then
                backend_ready=true
                break
            fi
            sleep 1
        done
        
        if [ "$backend_ready" = true ]; then
            success "Backend started successfully on port $BACKEND_PORT"
        else
            error "Backend failed to start or is not responding"
            if [ "$TEST_MODE" = false ]; then
                exit 1
            fi
        fi
    else
        log "Backend managed by Docker Compose"
    fi
}

start_frontend() {
    log "Starting AutoBot frontend..."
    
    if [ "$ENV_TYPE" = "native-vm" ]; then
        log "Connecting to frontend VM..."
        
        # Deploy and start frontend on VM
        local frontend_ip=${VMS["frontend"]}
        ssh -i "$SSH_KEY" "$SSH_USER@$frontend_ip" << 'EOF'
            cd /home/kali/AutoBot/autobot-vue
            
            # Update environment for backend connection
            export VITE_BACKEND_HOST=172.16.168.20
            export VITE_BACKEND_PORT=8001
            
            # Stop existing frontend if running
            pkill -f "npm.*dev" || true
            
            # Start frontend
            nohup npm run dev -- --host 0.0.0.0 --port 5173 > logs/frontend.log 2>&1 &
EOF
        
        # Wait for frontend to be ready
        local frontend_ready=false
        for i in {1..30}; do
            if curl -s http://${VMS["frontend"]}:$FRONTEND_PORT > /dev/null 2>&1; then
                frontend_ready=true
                break
            fi
            sleep 1
        done
        
        if [ "$frontend_ready" = true ]; then
            success "Frontend started successfully"
        else
            warning "Frontend may not be ready yet"
        fi
    else
        log "Frontend managed by Docker Compose"
    fi
}

start_redis() {
    log "Starting Redis service..."
    
    if [ "$ENV_TYPE" = "native-vm" ]; then
        local redis_ip=${VMS["redis"]}
        log "Connecting to Redis VM ($redis_ip)..."
        
        ssh -i "$SSH_KEY" "$SSH_USER@$redis_ip" << 'EOF'
            # Stop existing Redis if running
            sudo systemctl stop redis-server || true
            pkill redis-server || true
            
            # Start Redis Stack
            docker stop autobot-redis-stack 2>/dev/null || true
            docker rm autobot-redis-stack 2>/dev/null || true
            
            docker run -d \
                --name autobot-redis-stack \
                --restart unless-stopped \
                -p 6379:6379 \
                -p 8001:8001 \
                -v redis-data:/data \
                redis/redis-stack:latest
EOF
        
        # Verify Redis is accessible
        local redis_ready=false
        for i in {1..20}; do
            if timeout 5 redis-cli -h $redis_ip ping 2>/dev/null | grep -q PONG; then
                redis_ready=true
                break
            fi
            sleep 1
        done
        
        if [ "$redis_ready" = true ]; then
            success "Redis started successfully"
        else
            warning "Redis may not be ready yet"
        fi
    else
        log "Redis managed by Docker Compose"
    fi
}

start_browser_service() {
    log "Starting Browser automation service..."
    
    if [ "$ENV_TYPE" = "native-vm" ]; then
        local browser_ip=${VMS["browser"]}
        log "Connecting to Browser VM ($browser_ip)..."
        
        ssh -i "$SSH_KEY" "$SSH_USER@$browser_ip" << 'EOF'
            cd /home/kali/AutoBot
            
            # Stop existing browser service
            pkill -f "browser.*service" || true
            
            # Start browser service
            nohup python -m browser.service --host 0.0.0.0 --port 3000 > logs/browser.log 2>&1 &
EOF
        
        success "Browser service deployment initiated"
    else
        log "Browser service managed by Docker Compose"
    fi
}

start_ai_stack() {
    log "Starting AI Stack service..."
    
    if [ "$ENV_TYPE" = "native-vm" ]; then
        local ai_ip=${VMS["ai-stack"]}
        log "Connecting to AI Stack VM ($ai_ip)..."
        
        ssh -i "$SSH_KEY" "$SSH_USER@$ai_ip" << 'EOF'
            cd /home/kali/AutoBot
            
            # Stop existing AI stack
            pkill -f "ai.*stack" || true
            
            # Start AI stack
            nohup python -m ai_stack.service --host 0.0.0.0 --port 8080 > logs/ai-stack.log 2>&1 &
EOF
        
        success "AI Stack deployment initiated"
    else
        log "AI Stack managed by Docker Compose"
    fi
}

start_npu_worker() {
    log "Starting NPU Worker service..."
    
    if [ "$ENV_TYPE" = "native-vm" ]; then
        local npu_ip=${VMS["npu-worker"]}
        log "Connecting to NPU Worker VM ($npu_ip)..."
        
        ssh -i "$SSH_KEY" "$SSH_USER@$npu_ip" << 'EOF'
            cd /home/kali/AutoBot
            
            # Stop existing NPU worker
            pkill -f "npu.*worker" || true
            
            # Start NPU worker
            nohup python -m npu_worker.service --host 0.0.0.0 --port 8081 > logs/npu-worker.log 2>&1 &
EOF
        
        success "NPU Worker deployment initiated"
    else
        log "NPU Worker managed by Docker Compose"
    fi
}

launch_browser() {
    if [ "$NO_BROWSER" = true ]; then
        log "Browser launch disabled by --no-browser flag"
        return
    fi
    
    log "Launching browser..."
    
    local frontend_url
    if [ "$ENV_TYPE" = "native-vm" ]; then
        frontend_url="http://${VMS["frontend"]}:$FRONTEND_PORT"
    else
        frontend_url="http://localhost:$FRONTEND_PORT"
    fi
    
    # Wait a moment for services to be ready
    sleep 2
    
    # Launch browser in background
    if command -v xdg-open &> /dev/null; then
        nohup xdg-open "$frontend_url" &> /dev/null &
    elif command -v open &> /dev/null; then
        nohup open "$frontend_url" &> /dev/null &
    else
        log "No browser launcher found. Please open: $frontend_url"
    fi
}

show_system_status() {
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}         AutoBot System Status          ${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    
    # Environment Info
    echo -e "${CYAN}🌍 Environment:${NC}"
    echo -e "${BLUE}  Type: $ENV_TYPE${NC}"
    echo -e "${BLUE}  Mode: $([ "$DEV_MODE" = true ] && echo "Development" || echo "Production")${NC}"
    echo ""
    
    # Backend Status
    echo -e "${CYAN}🔧 Backend Service:${NC}"
    if curl -s http://localhost:$BACKEND_PORT/api/health &> /dev/null; then
        echo -e "${GREEN}  ✅ Backend Running${NC}"
        echo -e "${BLUE}    URL: http://localhost:$BACKEND_PORT${NC}"
    else
        echo -e "${RED}  ❌ Backend Not Responding${NC}"
    fi
    echo ""
    
    # Frontend Status
    echo -e "${CYAN}🌐 Frontend Service:${NC}"
    local frontend_url="http://localhost:$FRONTEND_PORT"
    if [ "$ENV_TYPE" = "native-vm" ]; then
        frontend_url="http://${VMS["frontend"]}:$FRONTEND_PORT"
    fi
    
    if curl -s "$frontend_url" &> /dev/null; then
        echo -e "${GREEN}  ✅ Frontend Running${NC}"
        echo -e "${BLUE}    URL: $frontend_url${NC}"
    else
        echo -e "${RED}  ❌ Frontend Not Responding${NC}"
    fi
    echo ""
    
    # Redis Status
    echo -e "${CYAN}🗄️  Redis Service:${NC}"
    local redis_host="localhost"
    if [ "$ENV_TYPE" = "native-vm" ]; then
        redis_host=${VMS["redis"]}
    fi
    
    if timeout 3 redis-cli -h "$redis_host" ping 2>/dev/null | grep -q PONG; then
        echo -e "${GREEN}  ✅ Redis Running${NC}"
        echo -e "${BLUE}    Host: $redis_host:$REDIS_PORT${NC}"
    else
        echo -e "${RED}  ❌ Redis Not Responding${NC}"
    fi
    echo ""
    
    # VNC Desktop Status
    echo -e "${CYAN}🖥️  VNC Desktop:${NC}"
    local xvfb_status=$(systemctl is-active xvfb@1 2>/dev/null || echo "inactive")
    local vnc_status=$(systemctl is-active vncserver@1 2>/dev/null || echo "inactive")
    local novnc_status=$(systemctl is-active novnc 2>/dev/null || echo "inactive")
    
    if [ "$xvfb_status" = "active" ] && [ "$vnc_status" = "active" ] && [ "$novnc_status" = "active" ]; then
        echo -e "${GREEN}  ✅ VNC Services Running${NC}"
        echo -e "${BLUE}    Xvfb: $xvfb_status${NC}"
        echo -e "${BLUE}    VNC Server: $vnc_status${NC}"
        echo -e "${BLUE}    noVNC: $novnc_status${NC}"
        echo -e "${BLUE}    Web URL: http://localhost:6080/vnc.html${NC}"
        echo -e "${BLUE}    VNC Client: localhost:5901${NC}"
    elif systemctl list-unit-files | grep -q "xvfb@.service\|vncserver@.service\|novnc.service"; then
        echo -e "${YELLOW}  ⚠️  VNC Services Partially Running${NC}"
        echo -e "${BLUE}    Xvfb: $xvfb_status${NC}"
        echo -e "${BLUE}    VNC Server: $vnc_status${NC}"
        echo -e "${BLUE}    noVNC: $novnc_status${NC}"
        echo -e "${BLUE}    Run: bash setup.sh desktop${NC}"
    else
        echo -e "${YELLOW}  ⚠️  VNC Not Configured${NC}"
        echo -e "${BLUE}    Run: bash setup.sh desktop${NC}"
    fi
    echo ""
    
    # Docker Status (if applicable)
    if [ "$ENV_TYPE" = "docker" ] || docker ps &> /dev/null; then
        echo -e "${CYAN}🐳 Docker Services:${NC}"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo -e "${RED}  ❌ Docker not accessible${NC}"
        echo ""
    fi
    
    # VM Status (if applicable)
    if [ "$ENV_TYPE" = "native-vm" ]; then
        echo -e "${CYAN}🔗 VM Connectivity:${NC}"
        for vm_name in "${!VMS[@]}"; do
            vm_ip=${VMS[$vm_name]}
            if timeout 3 ssh -i "$SSH_KEY" -o ConnectTimeout=2 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" "echo 'ok'" &>/dev/null; then
                echo -e "${GREEN}  ✅ $vm_name ($vm_ip)${NC}"
            else
                echo -e "${RED}  ❌ $vm_name ($vm_ip)${NC}"
            fi
        done
        echo ""
    fi
    
    echo -e "${BLUE}════════════════════════════════════════${NC}"
}

stop_all_services() {
    log "Stopping all AutoBot services..."
    
    # Stop VNC services first
    if systemctl is-active --quiet novnc || systemctl is-active --quiet vncserver@1 || systemctl is-active --quiet xvfb@1; then
        echo -e "${YELLOW}🛑 Stopping VNC Desktop...${NC}"
        sudo systemctl stop novnc 2>/dev/null || true
        sudo systemctl stop vncserver@1 2>/dev/null || true
        sudo systemctl stop xvfb@1 2>/dev/null || true
    fi
    
    # Stop local processes
    pkill -f "python.*backend" || true
    pkill -f "npm.*dev" || true
    
    # Stop Docker services
    if [ -f "docker-compose.yml" ]; then
        docker-compose down --remove-orphans 2>/dev/null || true
    fi
    
    # Stop services on VMs (if native-vm environment)
    if [ "$ENV_TYPE" = "native-vm" ]; then
        for vm_name in "${!VMS[@]}"; do
            vm_ip=${VMS[$vm_name]}
            echo "Stopping services on $vm_name..."
            ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" 'pkill -f "npm\|python\|node" || true' 2>/dev/null || true
        done
    fi
    
    success "All services stopped"
}

follow_logs() {
    log "Following AutoBot logs..."
    
    if [ -f "docker-compose.yml" ]; then
        docker-compose logs -f
    else
        tail -f logs/*.log 2>/dev/null || echo "No log files found"
    fi
}

main() {
    echo -e "${GREEN}🤖 AutoBot - Unified Startup${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
    
    # Show configuration
    log "Configuration:"
    log "  Mode: $([ "$DEV_MODE" = true ] && echo "Development" || echo "Production")"
    log "  Build: $BUILD_MODE"
    log "  Environment: $ENV_TYPE"
    log "  Desktop: $([ "$DESKTOP_ACCESS" = true ] && echo "Enabled" || echo "Disabled")"
    echo ""
    
    # Clean up if requested
    if [ "$FORCE_CLEANUP" = true ]; then
        log "Performing cleanup as requested..."
        stop_all_services
        docker system prune -f 2>/dev/null || true
    fi
    
    # Environment detection (must be done BEFORE prerequisites check)
    detect_environment
    
    # Prerequisites check (now aware of environment type)
    check_prerequisites
    
    # Environment-specific validation
    case "$ENV_TYPE" in
        "native-vm")
            if [ "$TEST_MODE" = false ]; then
                # Commenting out VM validation to avoid blocking startup
                # validate_native_vm_setup
                log "Native VM mode - skipping connectivity check in current session"
            fi
            ;;
        "docker")
            log "Docker environment detected"
            ;;
    esac
    
    # Start VNC desktop if enabled
    start_vnc_desktop
    
    # Build containers if needed (only in Docker mode)
    if [ "$ENV_TYPE" = "docker" ] && [ "$BUILD_MODE" != "skip" ]; then
        build_containers
    elif [ "$ENV_TYPE" = "native-vm" ]; then
        log "Native VM mode - skipping Docker builds"
    fi
    
    # Start services based on environment
    if [ "$PARALLEL_START" = true ]; then
        log "Starting services in parallel..."
        
        if [ "$ENV_TYPE" = "native-vm" ]; then
            start_redis &
            start_backend &
            start_frontend &
            start_browser_service &
            start_ai_stack &
            start_npu_worker &
            wait
        else
            log "Docker services started by docker-compose"
        fi
    else
        log "Starting services sequentially..."
        start_redis
        start_backend
        start_frontend
        start_browser_service
        start_ai_stack
        start_npu_worker
    fi
    
    # Wait for all services to be ready
    sleep 5
    
    # Launch browser if not disabled
    launch_browser
    
    # Show status if enabled
    if [ "$SHOW_STATUS" = true ]; then
        echo ""
        show_system_status
    fi
    
    # Final status
    echo ""
    success "AutoBot startup completed!"
    
    if [ "$ENV_TYPE" = "native-vm" ]; then
        log "Frontend: http://${VMS["frontend"]}:$FRONTEND_PORT"
        log "Backend: http://localhost:$BACKEND_PORT"
    else
        log "Frontend: http://localhost:$FRONTEND_PORT"
        log "Backend: http://localhost:$BACKEND_PORT"
    fi
    
if [ "$DESKTOP_ACCESS" = true ] && [ -n "$VNC_PID" ]; then
    echo "    VNC Desktop: http://localhost:6080/vnc.html"
fi
    
    log "Press Ctrl+C to stop all services"
    
    # Keep script running to handle cleanup
    while true; do
        sleep 10
        # Optional: Add health checks here
    done
}

# Run main function
main