#!/bin/bash

# AutoBot - Distributed VM Startup Script (Performance Optimized)
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
BACKEND_HOST=172.16.168.20
BACKEND_PORT=8001
FRONTEND_PORT=5173
REDIS_PORT=6379
BROWSER_PORT=3000
AI_STACK_PORT=8080
NPU_WORKER_PORT=8081

print_usage() {
    cat << EOF
${GREEN}AutoBot - Distributed VM Startup Script (Performance Optimized)${NC}

${YELLOW}DISTRIBUTED ARCHITECTURE:${NC}
  This script ONLY starts the backend locally on WSL (172.16.168.20:8001)
  All other services run on separate VMs and must be started separately.

${YELLOW}VM Services:${NC}
  Frontend:   172.16.168.21:5173 (Vue.js)
  NPU Worker: 172.16.168.22:8081 (Hardware AI)
  Redis:      172.16.168.23:6379 (Database)
  Browser:    172.16.168.25:3000 (Web Automation)

${YELLOW}Local Services (Main Machine):${NC}
  Backend:    172.16.168.20:8001 (FastAPI)
  Ollama:     localhost:11434 (AI LLM)

Usage: $0 [MODE] [OPTIONS]

${YELLOW}Modes:${NC}
  --dev               Development mode with auto-reload and debugging
  --prod              Production mode (default)

${YELLOW}Options:${NC}
  --no-browser        Don't launch browser automatically
  --desktop           Enable desktop access via VNC
  --no-desktop        Disable desktop access via VNC
  --status            Show current system status
  --stop              Stop all AutoBot services (backend + VMs)
  --restart           Fast, intelligent restart (< 1 minute)
  --help              Show this help message

${BLUE}Examples:${NC}
  $0 --dev                    # Development mode with debugging and hot reload
  $0 --prod                   # Production mode
  $0 --status                 # Show current distributed system status
  $0 --stop                   # Stop all AutoBot services
  $0 --restart                # Smart restart - backend only if VMs healthy, full if needed

${BLUE}VM Management:${NC}
  Use: bash scripts/vm-management/start-all-vms.sh    # Start all VM services
  Note: --stop now includes VM services automatically
  Use: bash scripts/vm-management/status-all-vms.sh   # Check all VM statuses

EOF
}

# Enhanced process killing function
kill_autobot_processes() {
    local timeout_seconds=${1:-10}
    log "Stopping AutoBot backend processes..."

    # More specific and comprehensive process patterns
    local backend_patterns=(
        "python.*backend/main.py"     # Direct execution
        "python -m backend.main"      # Module execution
        "python.*backend\.main"       # Alternative module execution
        "uvicorn.*backend"            # Uvicorn server
        "hypercorn.*backend"          # Hypercorn server
        "gunicorn.*backend"           # Gunicorn server
    )

    local killed_any=false
    for pattern in "${backend_patterns[@]}"; do
        local pids=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo "  Killing processes matching '$pattern': $pids"
            echo "$pids" | xargs -r kill -TERM 2>/dev/null || true
            killed_any=true
        fi
    done

    if [ "$killed_any" = true ]; then
        # Wait for graceful shutdown with timeout
        echo "  Waiting up to $timeout_seconds seconds for graceful shutdown..."
        local count=0
        while [ $count -lt $timeout_seconds ]; do
            local remaining_procs=""
            for pattern in "${backend_patterns[@]}"; do
                local pids=$(pgrep -f "$pattern" 2>/dev/null || true)
                if [ -n "$pids" ]; then
                    remaining_procs="$remaining_procs $pids"
                fi
            done

            if [ -z "$remaining_procs" ]; then
                success "All backend processes stopped gracefully"
                return 0
            fi

            sleep 1
            count=$((count + 1))
            echo -n "."
        done
        echo ""

        # Force kill remaining processes
        warning "Some processes didn't stop gracefully, force killing..."
        for pattern in "${backend_patterns[@]}"; do
            local pids=$(pgrep -f "$pattern" 2>/dev/null || true)
            if [ -n "$pids" ]; then
                echo "  Force killing: $pids"
                echo "$pids" | xargs -r kill -KILL 2>/dev/null || true
            fi
        done

        # Final verification
        sleep 1
        local still_running=""
        for pattern in "${backend_patterns[@]}"; do
            local pids=$(pgrep -f "$pattern" 2>/dev/null || true)
            if [ -n "$pids" ]; then
                still_running="$still_running $pids"
            fi
        done

        if [ -n "$still_running" ]; then
            error "Failed to kill some processes: $still_running"
            return 1
        else
            success "All backend processes stopped"
            return 0
        fi
    else
        info "No backend processes found running"
        return 0
    fi
}

# Fast VM health check
check_vm_health() {
    log "Quick VM health check..."
    local healthy_vms=0
    local total_vms=5

    # Parallel health checks using background processes
    local health_results=()

    # Frontend
    (timeout 3 curl -s "http://${VMS["frontend"]}:$FRONTEND_PORT" >/dev/null 2>&1 && echo "frontend:healthy" || echo "frontend:unhealthy") &
    health_results+=($!)

    # Redis
    (timeout 2 redis-cli -h "${VMS["redis"]}" ping 2>/dev/null | grep -q PONG && echo "redis:healthy" || echo "redis:unhealthy") &
    health_results+=($!)

    # NPU Worker
    (timeout 3 curl -s "http://${VMS["npu-worker"]}:$NPU_WORKER_PORT" >/dev/null 2>&1 && echo "npu:healthy" || echo "npu:unhealthy") &
    health_results+=($!)

    # AI Stack (Ollama) - Running locally on main machine, not on remote VM
    # Removed health check since it's a local service, not a VM service

    # Browser
    (timeout 3 curl -s "http://${VMS["browser"]}:$BROWSER_PORT" >/dev/null 2>&1 && echo "browser:healthy" || echo "browser:unhealthy") &
    health_results+=($!)

    # Wait for all checks and collect results
    for pid in "${health_results[@]}"; do
        local result=$(wait "$pid" && echo "" || echo "")
    done

    # Collect results synchronously with timeout
    sleep 4  # Max wait time for all checks

    # Re-run checks synchronously for accurate results
    echo -n "  Frontend... "
    if timeout 3 curl -s "http://${VMS["frontend"]}:$FRONTEND_PORT" >/dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
        healthy_vms=$((healthy_vms + 1))
    else
        echo -e "${RED}❌${NC}"
    fi

    echo -n "  Redis... "
    if timeout 2 redis-cli -h "${VMS["redis"]}" ping 2>/dev/null | grep -q PONG; then
        echo -e "${GREEN}✅${NC}"
        healthy_vms=$((healthy_vms + 1))
    else
        echo -e "${RED}❌${NC}"
    fi

    echo -n "  NPU Worker... "
    if timeout 3 curl -s "http://${VMS["npu-worker"]}:$NPU_WORKER_PORT" >/dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
        healthy_vms=$((healthy_vms + 1))
    else
        echo -e "${RED}❌${NC}"
    fi

    # AI Stack (Ollama) - Running locally on main machine, skipping VM check
    # Ollama is checked as part of backend health, not as a separate VM

    echo -n "  Browser... "
    if timeout 3 curl -s "http://${VMS["browser"]}:$BROWSER_PORT" >/dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
        healthy_vms=$((healthy_vms + 1))
    else
        echo -e "${RED}❌${NC}"
    fi

    local health_percentage=$((healthy_vms * 100 / total_vms))
    log "VM Health: $healthy_vms/$total_vms services healthy ($health_percentage%)"

    # Return success if >= 80% of services are healthy
    if [ $health_percentage -ge 80 ]; then
        return 0
    else
        return 1
    fi
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
        if [ "$DEV_MODE" = true ]; then
            echo -e "${YELLOW}    Start with: ssh $SSH_USER@${VMS["frontend"]} 'cd autobot-vue && npm run dev -- --host 0.0.0.0 --port 5173'${NC}"
        else
            echo -e "${YELLOW}    Start with: ssh $SSH_USER@${VMS["frontend"]} 'sudo systemctl start nginx'${NC}"
        fi
    fi

    # Check Redis
    echo -n "  Redis (${VMS["redis"]}:$REDIS_PORT)... "
    if timeout 3 redis-cli -h "${VMS["redis"]}" ping 2>/dev/null | grep -q PONG; then
        echo -e "${GREEN}✅ Running${NC}"
    else
        echo -e "${RED}❌ Not running${NC}"
        echo -e "${YELLOW}    Start with: bash scripts/vm-management/start-redis.sh${NC}"
    fi

    # Check other services
    local services=("npu-worker" "ai-stack" "browser")
    local ports=($NPU_WORKER_PORT $AI_STACK_PORT $BROWSER_PORT)

    for i in "${!services[@]}"; do
        local service="${services[$i]}"
        local port="${ports[$i]}"
        local vm_ip="${VMS[$service]}"

        echo -n "  $service ($vm_ip:$port)... "
        # Use service-specific health checks based on setup.sh implementation
        case $service in
            "npu-worker")
                if timeout 5 curl -s "http://$vm_ip:$port" >/dev/null 2>&1; then
                    echo -e "${GREEN}✅ Running${NC}"
                else
                    echo -e "${RED}❌ Not running${NC}"
                    echo -e "${YELLOW}    Start with: ssh $SSH_USER@$vm_ip 'cd npu-worker && python simple_npu_worker.py'${NC}"
                fi
                ;;
            "ai-stack")
                # AI Stack (Ollama) runs locally on main machine (172.16.168.20), not on this VM
                echo -e "${CYAN}ℹ️  Ollama runs locally on backend machine${NC}"
                ;;
            "browser")
                if timeout 5 curl -s "http://$vm_ip:$port" >/dev/null 2>&1; then
                    echo -e "${GREEN}✅ Running${NC}"
                else
                    echo -e "${RED}❌ Not running${NC}"
                    echo -e "${YELLOW}    Start with: ssh $SSH_USER@$vm_ip 'cd browser && node playwright-server.js'${NC}"
                fi
                ;;
        esac
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
    if curl -s http://$BACKEND_HOST:$BACKEND_PORT/api/health &> /dev/null; then
        echo -e "${GREEN}  ✅ Backend Running${NC}"
        echo -e "${BLUE}    URL: http://$BACKEND_HOST:$BACKEND_PORT${NC}"
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
    echo -e "${BLUE}  Ollama:     http://localhost:11434 (Local AI)${NC}"
    echo -e "${BLUE}  NPU Worker: http://${VMS["npu-worker"]}:$NPU_WORKER_PORT${NC}"
    echo -e "${BLUE}  Browser:    http://${VMS["browser"]}:$BROWSER_PORT${NC}"
    echo ""

    echo -e "${BLUE}════════════════════════════════════════${NC}"
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
            sleep 2  # Reduced from 3 seconds
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

# Smart restart function - single optimized restart with intelligent VM handling
smart_restart() {
    local start_time=$(date +%s)
    log "🚀 Smart restart - analyzing system and restarting optimally..."

    # Step 1: Quick VM health assessment (5 seconds max)
    echo -e "${CYAN}Step 1/3: Assessing system health...${NC}"
    local vm_restart_needed=false

    if check_vm_health; then
        success "VMs are healthy - performing fast backend-only restart"
        vm_restart_needed=false
    else
        warning "Some VMs are unhealthy - will include VM restart"
        vm_restart_needed=true
    fi

    # Step 2: Stop services (5-15 seconds depending on path)
    echo -e "${CYAN}Step 2/3: Stopping services...${NC}"

    # Always stop backend with fast timeout
    kill_autobot_processes 5

    # Stop VNC if running
    if systemctl is-active --quiet novnc || systemctl is-active --quiet vncserver@1 || systemctl is-active --quiet xvfb@1; then
        echo -e "${YELLOW}🛑 Stopping VNC Desktop...${NC}"
        sudo systemctl stop novnc vncserver@1 xvfb@1 2>/dev/null || true
    fi

    # Stop VMs if needed (parallel execution for speed)
    if [ "$vm_restart_needed" = true ]; then
        if [ -f "scripts/vm-management/stop-all-vms.sh" ]; then
            log "Stopping VM services (optimized timeout)..."
            timeout 30 bash scripts/vm-management/stop-all-vms.sh || warning "VM stop took longer than expected"
            sleep 1  # Minimal wait
        else
            warning "VM stop script not found. Manual VM restart may be required."
        fi
    fi

    # Step 3: Start services (15-30 seconds depending on path)
    echo -e "${CYAN}Step 3/3: Starting services...${NC}"

    # Start VMs first if needed
    if [ "$vm_restart_needed" = true ]; then
        if [ -f "scripts/vm-management/start-all-vms.sh" ]; then
            log "Starting VM services (optimized timeout)..."
            timeout 60 bash scripts/vm-management/start-all-vms.sh || warning "VM start took longer than expected"
            sleep 2  # Reduced wait time
        else
            warning "VM start script not found. Please start VM services manually."
        fi
    fi

    # Start backend with optimized timing
    log "Starting backend..."
    start_backend_optimized

    # Start VNC if needed
    if [ "$DESKTOP_ACCESS" = true ]; then
        start_vnc_desktop
    fi

    # Calculate and report completion time
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [ "$vm_restart_needed" = true ]; then
        success "Full system restart completed in ${duration} seconds (including VMs)"
    else
        success "Fast backend restart completed in ${duration} seconds"
    fi

    # Show final status
    echo ""
    log "Checking final system health..."
    show_system_status
}

# Optimized backend startup
start_backend_optimized() {
    log "Starting AutoBot backend (172.16.168.20:8001)..."

    # Set up Python environment
    export PYTHONPATH="$PWD"

    # Activate virtual environment if it exists (from setup.sh)
    if [ -d "venv" ]; then
        log "Activating Python virtual environment..."
        source venv/bin/activate
    fi

    # Ensure logs directory exists
    mkdir -p logs

    # Start backend with proper error handling
    if [ "$DEV_MODE" = true ]; then
        log "Starting backend in development mode..."
        nohup python backend/main.py > logs/backend.log 2>&1 &
    else
        log "Starting backend in production mode..."
        nohup python backend/main.py > logs/backend.log 2>&1 &
    fi

    # Signal-based backend readiness check - wait for process signal
    log "Waiting for backend to signal ready (AI models loading...)..."
    local backend_pid=$(pgrep -f "python.*backend/main.py")

    if [ -z "$backend_pid" ]; then
        error "Backend process failed to start"
        echo "Check logs: tail -f logs/backend.log"
        exit 1
    fi

    # Wait for backend to signal ready via health endpoint
    # Process exists, so wait for health endpoint to respond (no timeout)
    while true; do
        if curl -s http://$BACKEND_HOST:$BACKEND_PORT/api/health > /dev/null 2>&1; then
            success "Backend started successfully on port $BACKEND_PORT"
            break
        fi

        # Check if process still exists
        if ! kill -0 "$backend_pid" 2>/dev/null; then
            error "Backend process died during startup"
            echo "Check logs: tail -f logs/backend.log"
            exit 1
        fi

        sleep 1
        echo -n "."
    done
    echo ""
}

stop_backend() {
    log "Stopping all AutoBot services (backend + VMs)..."

    # Stop local backend processes with verification
    kill_autobot_processes 10

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
            smart_restart
            exit 0
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

    # Stop backend with improved process matching
    kill_autobot_processes 5

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

        if timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
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

        # Development mode: Sync code and start Vite dev server manually
        echo "  📦 Syncing frontend code to VM..."

        # Check if sync script exists
        if [ -f "scripts/utilities/sync-frontend.sh" ]; then
            ./scripts/utilities/sync-frontend.sh
        elif [ -f "sync-frontend.sh" ]; then
            ./sync-frontend.sh
        else
            echo -e "${YELLOW}  ⚠️  Sync script not found - code may be outdated on frontend VM${NC}"
        fi

        # Check if frontend is already running
        if timeout 5 curl -s "http://${VMS["frontend"]}:$FRONTEND_PORT" >/dev/null 2>&1; then
            echo -e "${GREEN}  ✅ Frontend development server already running${NC}"
            echo -e "${BLUE}  🌐 Frontend URL: http://172.16.168.21:5173${NC}"
            echo -e "${CYAN}  📝 Logs: ssh autobot@172.16.168.21 'tail -f /tmp/vite.log'${NC}"
            return 0
        fi

        # Optimized process cleanup
        echo "  🧹 Cleaning up existing processes..."
        timeout 3 ssh -T -i "$SSH_KEY" "$SSH_USER@${VMS["frontend"]}" "pkill -f 'npm.*dev' 2>/dev/null || true; pkill -f 'vite.*5173' 2>/dev/null || true" 2>/dev/null || echo "    Process cleanup completed"
        sleep 1  # Reduced from 2 seconds

        # Start Vite dev server in background
        echo "  🚀 Starting Vite dev server on frontend VM..."

        # Start Vite with optimized timing
        timeout 5 ssh -T -i "$SSH_KEY" "$SSH_USER@${VMS["frontend"]}" "cd autobot-vue && VITE_BACKEND_HOST=$BACKEND_HOST VITE_BACKEND_PORT=$BACKEND_PORT nohup npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT > /tmp/vite.log 2>&1 < /dev/null & sleep 1" || echo "  📤 Vite startup command sent"

        # Optimized wait times
        echo "  ⏳ Starting npm process..."
        sleep 1  # Reduced from 2 seconds
        echo "  📦 Loading dependencies and building..."
        sleep 2  # Reduced from 3 seconds
        echo "  🔍 Testing server response..."

        # Check if frontend is now running with reduced timeout
        if timeout 10 bash -c 'while ! curl -s "http://172.16.168.21:5173" >/dev/null 2>&1; do sleep 0.5; done'; then
            echo -e "${GREEN}  ✅ Frontend development server started successfully${NC}"
            echo -e "${BLUE}  🌐 Frontend URL: http://172.16.168.21:5173${NC}"
            echo -e "${CYAN}  🔧 Native Vite dev server with hot reload enabled${NC}"
            echo -e "${CYAN}  📝 Logs: ssh autobot@172.16.168.21 'tail -f /tmp/vite.log'${NC}"
        else
            echo -e "${RED}  ❌ Frontend failed to start${NC}"
            echo -e "${YELLOW}  💡 Check logs: ssh autobot@172.16.168.21 'tail -f /tmp/vite.log'${NC}"
            echo -e "${YELLOW}  💡 Manual start: ssh autobot@172.16.168.21 'cd autobot-vue && npm run dev -- --host 0.0.0.0 --port 5173'${NC}"
        fi
    fi
}

start_backend() {
    log "Starting AutoBot backend (172.16.168.20:8001)..."

    # Check if backend is already running and kill if needed
    if pgrep -f "python.*backend" > /dev/null || pgrep -f "python -m backend.main" > /dev/null; then
        warning "Backend already running, stopping first..."
        kill_autobot_processes 5
    fi

    # Use optimized backend startup
    start_backend_optimized
}

launch_browser() {
    if [ "$NO_BROWSER" = true ]; then
        log "Browser launch disabled by --no-browser flag"
        return
    fi

    log "Launching browser..."

    local frontend_url="http://${VMS["frontend"]}:$FRONTEND_PORT"

    # Wait a moment for services to be ready
    sleep 1  # Reduced from 2 seconds

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
    echo -e "${GREEN}🤖 AutoBot - Distributed VM Backend Startup (Performance Optimized)${NC}"
    echo -e "${BLUE}=================================================================${NC}"
    echo ""

    # Show configuration
    log "Configuration:"
    log "  Mode: $([ "$DEV_MODE" = true ] && echo "Development" || echo "Production")"
    log "  Architecture: Distributed VM"
    log "  Backend: 172.16.168.20:$BACKEND_PORT (Local WSL)"
    log "  Desktop: $([ "$DESKTOP_ACCESS" = true ] && echo "Enabled" || echo "Disabled")"
    log "  Performance: Optimized startup with reduced wait times"
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

    # Wait for backend to be fully ready (reduced time)
    sleep 1  # Reduced from 3 seconds

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
    echo -e "${CYAN}  Start all VMs:    bash scripts/vm-management/start-all-vms.sh${NC}"
    echo -e "${CYAN}  Stop all VMs:     bash scripts/vm-management/stop-all-vms.sh${NC}"
    echo -e "${CYAN}  Check status:     bash scripts/vm-management/status-all-vms.sh${NC}"
    echo -e "${CYAN}  Smart restart:    bash run_autobot.sh --restart${NC}"
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