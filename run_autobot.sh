#!/bin/bash

# AutoBot - Distributed VM Startup Script
# ONLY starts backend locally (172.16.168.20:8001)
# Connects to existing services running on distributed VMs

set -e

# Define color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
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
NO_BROWSER=false
DESKTOP_ACCESS=true  # Enable by default per CLAUDE.md guidelines
VNC_PID=""

# VM Configuration (Distributed Architecture)
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
${GREEN}AutoBot - Distributed VM Startup Script${NC}

${YELLOW}DISTRIBUTED ARCHITECTURE:${NC}
  This script ONLY starts the backend locally on WSL (172.16.168.20:8001)
  All other services run on separate VMs and must be started separately.

${YELLOW}VM Services:${NC}
  Frontend:   172.16.168.21:5173 (Vue.js)
  NPU Worker: 172.16.168.22:8081 (Hardware AI)
  Redis:      172.16.168.23:6379 (Database)
  AI Stack:   172.16.168.24:8080 (AI Processing)
  Browser:    172.16.168.25:3000 (Web Automation)

Usage: $0 [MODE] [OPTIONS]

${YELLOW}Modes:${NC}
  --dev               Development mode with auto-reload and debugging
  --prod              Production mode (default)

${YELLOW}Options:${NC}
  --no-browser        Don't launch browser automatically
  --desktop           Enable desktop access via VNC
  --no-desktop        Disable desktop access via VNC
  --build             Force build even if images exist
  --no-build          Skip Docker builds (fastest restart)
  --rebuild           Force rebuild everything (clean slate)
  --status            Show current system status
  --stop              Stop all AutoBot services (backend + VMs)
  --restart           Restart all services (backend + all VMs)
  --help              Show this help message

${BLUE}Examples:${NC}
  $0 --dev                    # Start backend in development mode
  $0 --prod                   # Start backend in production mode
  $0 --status                 # Show current distributed system status
  $0 --stop                   # Stop all AutoBot services
  $0 --restart                # Restart all services (backend + VMs)

${BLUE}VM Management:${NC}
  Use: bash scripts/vm-management/start-all-vms.sh    # Start all VM services
  Note: --stop now includes VM services automatically
  Use: bash scripts/vm-management/status-all-vms.sh   # Check all VM statuses

EOF
}

# VM service check function (moved here to be available before argument parsing)
check_vm_services() {
    echo -e "${BLUE}🏥 Checking VM Service Health...${NC}"
    
    # Check Frontend
    echo -n "  Frontend (${VMS["frontend"]}:$FRONTEND_PORT)... "
    if timeout 5 curl -s "http://${VMS["frontend"]}:$FRONTEND_PORT" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Running${NC}"
    else
        echo -e "${RED}❌ Not running${NC}"
        echo -e "${YELLOW}    Start with: ssh $SSH_USER@${VMS["frontend"]} 'sudo systemctl start autobot-frontend-dev'${NC}"
    fi
    
    # Check Redis
    echo -n "  Redis (${VMS["redis"]}:$REDIS_PORT)... "
    if timeout 3 redis-cli -h "${VMS["redis"]}" ping 2>/dev/null | grep -q PONG; then
        echo -e "${GREEN}✅ Running${NC}"
    else
        echo -e "${RED}❌ Not running${NC}"
        echo -e "${YELLOW}    Start with: ssh $SSH_USER@${VMS["redis"]} 'docker run -d --name autobot-redis-stack -p 6379:6379 -p 8001:8001 -v redis-data:/data redis/redis-stack:latest'${NC}"
    fi
    
    # Check other services
    local services=("npu-worker" "ai-stack" "browser")
    local ports=($NPU_WORKER_PORT $AI_STACK_PORT $BROWSER_PORT)
    
    for i in "${!services[@]}"; do
        local service="${services[$i]}"
        local port="${ports[$i]}"
        local vm_ip="${VMS[$service]}"
        
        echo -n "  $service ($vm_ip:$port)... "
        if timeout 5 curl -s "http://$vm_ip:$port/health" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Running${NC}"
        else
            echo -e "${RED}❌ Not running${NC}"
            echo -e "${YELLOW}    Start with scripts/vm-management/start-$service.sh${NC}"
        fi
    done
}

# System status function (moved here to be available before argument parsing)
show_system_status() {
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}         AutoBot Distributed System      ${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    
    # Environment Info
    echo -e "${CYAN}🌍 Architecture: Distributed VM${NC}"
    echo -e "${BLUE}  Mode: $([ "$DEV_MODE" = true ] && echo "Development" || echo "Production")${NC}"
    echo ""
    
    # Backend Status (Local WSL)
    echo -e "${CYAN}🔧 Backend Service (WSL - 172.16.168.20):${NC}"
    if curl -s http://localhost:$BACKEND_PORT/api/health &> /dev/null; then
        echo -e "${GREEN}  ✅ Backend Running${NC}"
        echo -e "${BLUE}    URL: http://localhost:$BACKEND_PORT${NC}"
    else
        echo -e "${RED}  ❌ Backend Not Responding${NC}"
        echo -e "${YELLOW}    Start with: bash run_autobot.sh --dev${NC}"
    fi
    echo ""
    
    # VM Services Status
    check_vm_services
    echo ""
    
    # VNC Desktop Status
    echo -e "${CYAN}🖥️  VNC Desktop (WSL):${NC}"
    local xvfb_status=$(systemctl is-active xvfb@1 2>/dev/null || echo "inactive")
    local vnc_status=$(systemctl is-active vncserver@1 2>/dev/null || echo "inactive")
    local novnc_status=$(systemctl is-active novnc 2>/dev/null || echo "inactive")
    
    if [ "$xvfb_status" = "active" ] && [ "$vnc_status" = "active" ] && [ "$novnc_status" = "active" ]; then
        echo -e "${GREEN}  ✅ VNC Services Running${NC}"
        echo -e "${BLUE}    Web URL: http://localhost:6080/vnc.html${NC}"
    else
        echo -e "${YELLOW}  ⚠️  VNC Not Running${NC}"
        echo -e "${BLUE}    Start with: bash run_autobot.sh --desktop${NC}"
    fi
    echo ""
    
    # Access Points
    echo -e "${CYAN}🌐 Access Points:${NC}"
    echo -e "${BLUE}  Frontend:   http://${VMS["frontend"]}:$FRONTEND_PORT${NC}"
    echo -e "${BLUE}  Backend:    http://172.16.168.20:$BACKEND_PORT${NC}"
    echo -e "${BLUE}  Redis:      ${VMS["redis"]}:$REDIS_PORT${NC}"
    echo -e "${BLUE}  AI Stack:   http://${VMS["ai-stack"]}:$AI_STACK_PORT${NC}"
    echo -e "${BLUE}  NPU Worker: http://${VMS["npu-worker"]}:$NPU_WORKER_PORT${NC}"
    echo -e "${BLUE}  Browser:    http://${VMS["browser"]}:$BROWSER_PORT${NC}"
    echo ""
    
    echo -e "${BLUE}════════════════════════════════════════${NC}"
}

# Restart all services function (defined before argument parsing)
restart_all_services() {
    log "Restarting all AutoBot services (backend + VMs)..."
    
    # Stop all services first
    log "Step 1/3: Stopping all services..."
    
    # Stop backend processes
    log "Stopping AutoBot backend..."
    pkill -f "python.*backend" || true
    
    # Stop VNC services if running
    if systemctl is-active --quiet novnc || systemctl is-active --quiet vncserver@1 || systemctl is-active --quiet xvfb@1; then
        echo -e "${YELLOW}🛑 Stopping VNC Desktop...${NC}"
        sudo systemctl stop novnc vncserver@1 xvfb@1 2>/dev/null || true
    fi
    
    # Stop VM services if scripts exist
    if [ -f "scripts/vm-management/stop-all-vms.sh" ]; then
        log "Stopping VM services..."
        bash scripts/vm-management/stop-all-vms.sh
        sleep 5  # Wait for services to fully stop
    else
        warning "VM stop script not found. Manual VM restart may be required."
    fi
    
    # Start VM services
    log "Step 2/3: Starting VM services..."
    if [ -f "scripts/vm-management/start-all-vms.sh" ]; then
        bash scripts/vm-management/start-all-vms.sh
        sleep 10  # Wait for VM services to initialize
    else
        warning "VM start script not found. Please start VM services manually."
    fi
    
    # Start backend last
    log "Step 3/3: Starting backend..."
    
    # Set up Python environment
    export PYTHONPATH="$PWD"
    
    # Ensure logs directory exists
    mkdir -p logs
    
    # Start backend
    if [ "$DEV_MODE" = true ]; then
        log "Starting backend in development mode..."
        nohup python backend/fast_app_factory_fix.py > logs/backend.log 2>&1 &
    else
        log "Starting backend in production mode..."
        nohup python backend/fast_app_factory_fix.py > logs/backend.log 2>&1 &
    fi
    
    # Wait for backend to start
    log "Waiting for backend to be ready..."
    local backend_ready=false
    for i in {1..30}; do
        if curl -s http://localhost:8001/api/health > /dev/null 2>&1; then
            backend_ready=true
            break
        fi
        sleep 1
        echo -n "."
    done
    echo ""
    
    if [ "$backend_ready" = true ]; then
        success "All services restarted successfully!"
    else
        error "Backend failed to start or is not responding"
        echo -e "${YELLOW}Check logs: tail -f logs/backend.log${NC}"
        exit 1
    fi
    
    # Show final status
    log "Checking service health..."
    show_system_status
}

stop_backend() {
    log "Stopping all AutoBot services (backend + VMs)..."
    
    # Stop local backend processes first
    log "Stopping local backend..."
    pkill -f "python.*backend" || true
    
    # Stop VNC services
    if systemctl is-active --quiet novnc || systemctl is-active --quiet vncserver@1 || systemctl is-active --quiet xvfb@1; then
        echo -e "${YELLOW}🛑 Stopping VNC Desktop...${NC}"
        sudo systemctl stop novnc vncserver@1 xvfb@1 2>/dev/null || true
    fi
    
    # Stop all remote VM services
    log "Stopping remote VM services..."
    if [ -f "scripts/vm-management/stop-all-vms.sh" ]; then
        bash scripts/vm-management/stop-all-vms.sh
    else
        warning "VM stop script not found at scripts/vm-management/stop-all-vms.sh"
    fi
    
    success "All AutoBot services stopped (backend + VMs)"
    echo ""
    echo -e "${YELLOW}💡 Tip: For smoother service management, configure passwordless sudo:${NC}"
    echo -e "${CYAN}  bash scripts/utilities/batch-configure-vms.sh sudo${NC}"
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
        --status)
            show_system_status
            exit 0
            ;;
        --stop)
            stop_backend
            exit 0
            ;;
        --restart)
            restart_all_services
            exit 0
            ;;
        --build)
            BUILD=true
            NO_BUILD=false
            shift
            ;;
        --no-build)
            NO_BUILD=true
            BUILD=false
            shift
            ;;
        --rebuild)
            REBUILD=true
            BUILD=true
            NO_BUILD=false
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
    log "Shutting down AutoBot backend..."
    
    # Stop VNC services
    if systemctl is-active --quiet novnc || systemctl is-active --quiet vncserver@1 || systemctl is-active --quiet xvfb@1; then
        echo -e "${YELLOW}🛑 Stopping VNC Desktop...${NC}"
        sudo systemctl stop novnc 2>/dev/null || true
        sudo systemctl stop vncserver@1 2>/dev/null || true
        echo -e "${GREEN}✅ VNC Desktop stopped${NC}"
    fi
    
    if [ ! -z "$VNC_PID" ]; then
        echo "Stopping VNC server (PID: $VNC_PID)..."
        kill -TERM $VNC_PID 2>/dev/null || true
    fi
    
    # Stop backend
    pkill -f "python.*backend/fast_app_factory_fix.py" || true
    
    success "AutoBot backend stopped"
    echo -e "${CYAN}VM services continue running. Use scripts/vm-management/stop-all-vms.sh to stop them.${NC}"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

check_prerequisites() {
    log "Checking prerequisites..."
    
    local missing_deps=()
    
    # Check essential commands
    for cmd in python3 curl redis-cli ssh; do
        if ! command -v $cmd &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        error "Missing required dependencies: ${missing_deps[*]}"
        echo "Please install missing dependencies and try again"
        exit 1
    fi
    
    # Check SSH key for VM connectivity
    if [ ! -f "$SSH_KEY" ]; then
        warning "SSH key not found: $SSH_KEY"
        echo "VM connectivity checks will be skipped"
    fi
    
    success "All prerequisites satisfied"
}

check_vm_connectivity() {
    echo -e "${BLUE}🔗 Testing VM Connectivity...${NC}"
    
    if [ ! -f "$SSH_KEY" ]; then
        warning "SSH key not found - skipping VM connectivity checks"
        return 0
    fi
    
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
        warning "Some VMs are not accessible"
        echo -e "${YELLOW}Use: bash setup.sh initial --distributed  # To configure VM connectivity${NC}"
        echo -e "${CYAN}Backend will start anyway, but VM services may not be available${NC}"
    else
        success "All VMs are accessible"
    fi
}

start_frontend_dev() {
    if [ "$DEV_MODE" = true ]; then
        echo -e "${CYAN}🔧 Starting Frontend Development Mode...${NC}"
        
        # Check if we have Ansible connectivity
        if command -v ansible &> /dev/null && [ -f "ansible/inventory/production.yml" ]; then
            echo "  📡 Managing frontend development service on VM..."
            
            # Restart the systemd service for development mode
            ansible frontend -i ansible/inventory/production.yml -m systemd -a "name=autobot-frontend-dev state=restarted enabled=yes daemon_reload=yes" -b 2>/dev/null
            
            echo "  ⏳ Waiting for frontend service to start..."
            sleep 8
            
            # Check if frontend is now running
            if timeout 15 curl -s "http://${VMS["frontend"]}:$FRONTEND_PORT" >/dev/null 2>&1; then
                echo -e "${GREEN}  ✅ Frontend development service started successfully${NC}"
                echo -e "${BLUE}  🌐 Frontend URL: http://172.16.168.21:5173${NC}"
                echo -e "${CYAN}  🔧 Native Vite dev server with hot reload enabled${NC}"
                
                # Show service status
                echo "  📋 Service status:"
                ansible frontend -i ansible/inventory/production.yml -m shell -a "systemctl is-active autobot-frontend-dev" -b 2>/dev/null | grep -v "CHANGED" | sed 's/^/    /'
            else
                echo -e "${RED}  ❌ Frontend failed to start${NC}"
                echo -e "${YELLOW}  💡 Check service: ansible frontend -i ansible/inventory/production.yml -m shell -a 'systemctl status autobot-frontend-dev' -b${NC}"
                echo -e "${YELLOW}  💡 Check logs: ansible frontend -i ansible/inventory/production.yml -m shell -a 'journalctl -u autobot-frontend-dev -n 20' -b${NC}"
            fi
        else
            warning "Ansible not available. Cannot start remote frontend development mode."
            echo -e "${YELLOW}  Manual start: ssh autobot@172.16.168.21 'sudo systemctl start autobot-frontend-dev'${NC}"
            echo -e "${YELLOW}  Check status: ssh autobot@172.16.168.21 'sudo systemctl status autobot-frontend-dev'${NC}"
        fi
    fi
}

start_vnc_desktop() {
    if [ "$DESKTOP_ACCESS" = true ]; then
        echo -e "${CYAN}🖥️  Starting VNC Desktop Access...${NC}"
        
        # Check if VNC services are already running
        if systemctl is-active --quiet xvfb@1 && systemctl is-active --quiet vncserver@1 && systemctl is-active --quiet novnc; then
            echo -e "${YELLOW}⚠️  VNC services already running${NC}"
            return 0
        fi
        
        # Check if VNC installation exists
        if [ ! -f "scripts/setup/install-vnc-headless.sh" ]; then
            echo -e "${YELLOW}⚠️  VNC not configured. Run: ${BLUE}bash setup.sh desktop${NC}"
            echo -e "${CYAN}ℹ️  Continuing without VNC desktop...${NC}"
            DESKTOP_ACCESS=false
            return 0
        fi
        
        # Start VNC services using systemd
        echo "Starting VNC services..."
        
        if sudo systemctl start xvfb@1 vncserver@1 novnc 2>/dev/null; then
            sleep 3
            if systemctl is-active --quiet xvfb@1 && systemctl is-active --quiet vncserver@1 && systemctl is-active --quiet novnc; then
                echo -e "${GREEN}✅ VNC Desktop available at: ${BLUE}http://localhost:6080/vnc.html${NC}"
            else
                echo -e "${YELLOW}⚠️  VNC services partially started. Check: ${BLUE}sudo systemctl status xvfb@1 vncserver@1 novnc${NC}"
            fi
        else
            echo -e "${YELLOW}⚠️  VNC services not available. Run: ${BLUE}bash setup.sh desktop${NC}"
            DESKTOP_ACCESS=false
        fi
    fi
}

start_backend() {
    log "Starting AutoBot backend (172.16.168.20:8001)..."
    
    # Check if backend is already running
    if pgrep -f "python.*backend/fast_app_factory_fix.py" > /dev/null; then
        warning "Backend already running, stopping first..."
        pkill -f "python.*backend/fast_app_factory_fix.py" || true
        sleep 2
    fi
    
    # Set up Python environment
    export PYTHONPATH="$PWD"
    
    # Ensure logs directory exists
    mkdir -p logs
    
    # Start backend with proper error handling
    if [ "$DEV_MODE" = true ]; then
        log "Starting backend in development mode..."
        nohup python backend/fast_app_factory_fix.py > logs/backend.log 2>&1 &
    else
        log "Starting backend in production mode..."
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
        echo "Check logs: tail -f logs/backend.log"
        exit 1
    fi
}

launch_browser() {
    if [ "$NO_BROWSER" = true ]; then
        log "Browser launch disabled by --no-browser flag"
        return
    fi
    
    log "Launching browser..."
    
    local frontend_url="http://${VMS["frontend"]}:$FRONTEND_PORT"
    
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

main() {
    echo -e "${GREEN}🤖 AutoBot - Distributed VM Backend Startup${NC}"
    echo -e "${BLUE}=============================================${NC}"
    echo ""
    
    # Show configuration
    log "Configuration:"
    log "  Mode: $([ "$DEV_MODE" = true ] && echo "Development" || echo "Production")"
    log "  Architecture: Distributed VM"
    log "  Backend: 172.16.168.20:$BACKEND_PORT (Local WSL)"
    log "  Desktop: $([ "$DESKTOP_ACCESS" = true ] && echo "Enabled" || echo "Disabled")"
    echo ""
    
    # Prerequisites check
    check_prerequisites
    
    # Check VM connectivity
    check_vm_connectivity
    
    # Check if VM services are running
    check_vm_services
    echo ""
    
    # Start VNC desktop if enabled
    start_vnc_desktop
    
    # Start backend (the only service we manage locally)
    start_backend
    
    # Start frontend in dev mode if requested
    if [ "$DEV_MODE" = true ]; then
        start_frontend_dev
    fi
    
    # Wait for backend to be fully ready
    sleep 3
    
    # Launch browser if not disabled
    launch_browser
    
    # Show status
    echo ""
    show_system_status
    
    # Final status
    echo ""
    success "AutoBot backend startup completed!"
    echo ""
    echo -e "${BLUE}🌐 Access Points:${NC}"
    echo -e "${CYAN}  Frontend:   http://${VMS["frontend"]}:$FRONTEND_PORT${NC}"
    echo -e "${CYAN}  Backend:    http://172.16.168.20:$BACKEND_PORT${NC}"
    echo ""
    
    if [ "$DESKTOP_ACCESS" = true ] && systemctl is-active --quiet novnc; then
        echo -e "${CYAN}  VNC Desktop: http://localhost:6080/vnc.html${NC}"
        echo ""
    fi
    
    echo -e "${YELLOW}📋 VM Management Commands:${NC}"
    echo -e "${CYAN}  Start all VMs:  bash scripts/vm-management/start-all-vms.sh${NC}"
    echo -e "${CYAN}  Stop all VMs:   bash scripts/vm-management/stop-all-vms.sh${NC}"
    echo -e "${CYAN}  Check status:   bash scripts/vm-management/status-all-vms.sh${NC}"
    echo ""
    
    log "Press Ctrl+C to stop backend (VM services will keep running)"
    
    # Keep script running to handle cleanup
    while true; do
        sleep 10
        # Optional: Add health checks here
    done
}

# Run main function
main