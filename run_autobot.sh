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

# =============================================================================
# SSOT Configuration - Load from .env file (Single Source of Truth)
# Issue: #604 - SSOT Phase 4 Cleanup
# =============================================================================
if [ -f ".env" ]; then
    set -a  # Automatically export all variables
    source .env
    set +a
else
    warning ".env file not found - using fallback defaults"
fi

# Default configuration
DEV_MODE=false
PROD_MODE=false
NO_BROWSER=false
DESKTOP_ACCESS=true  # Enable by default per CLAUDE.md guidelines
VNC_PID=""

# VM Configuration (Distributed Architecture) - Using SSOT env vars
SSH_KEY="$HOME/.ssh/autobot_key"
SSH_USER="autobot"
declare -A VMS=(
    ["frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

# Service ports - Using SSOT env vars with fallbacks
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"
FRONTEND_PORT="${AUTOBOT_FRONTEND_PORT:-5173}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
BROWSER_PORT="${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"
AI_STACK_PORT="${AUTOBOT_AI_STACK_PORT:-8080}"
NPU_WORKER_PORT="${AUTOBOT_NPU_WORKER_PORT:-8081}"

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
        "celery.*backend.celery_app"  # Celery worker
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
    local total_required_vms=4  # Frontend, Redis, Browser, AI-stack (NPU is optional)

    # Parallel health checks using background processes
    local health_results=()

    # Frontend
    (timeout 3 curl -s "http://${VMS["frontend"]}:$FRONTEND_PORT" >/dev/null 2>&1 && echo "frontend:healthy" || echo "frontend:unhealthy") &
    health_results+=($!)

    # Redis
    (timeout 2 redis-cli -h "${VMS["redis"]}" ping 2>/dev/null | grep -q PONG && echo "redis:healthy" || echo "redis:unhealthy") &
    health_results+=($!)

    # Browser
    (timeout 3 curl -s "http://${VMS["browser"]}:$BROWSER_PORT" >/dev/null 2>&1 && echo "browser:healthy" || echo "browser:unhealthy") &
    health_results+=($!)

    # AI-stack
    (timeout 3 curl -s "http://${VMS["ai-stack"]}:$AI_STACK_PORT" >/dev/null 2>&1 && echo "ai-stack:healthy" || echo "ai-stack:unhealthy") &
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

    echo -n "  Browser... "
    if timeout 3 curl -s "http://${VMS["browser"]}:$BROWSER_PORT" >/dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
        healthy_vms=$((healthy_vms + 1))
    else
        echo -e "${RED}❌${NC}"
    fi

    echo -n "  AI-stack... "
    if timeout 3 curl -s "http://${VMS["ai-stack"]}:$AI_STACK_PORT" >/dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
        healthy_vms=$((healthy_vms + 1))
    else
        echo -e "${RED}❌${NC}"
    fi

    # NPU Worker - Optional, check but don't count against health
    echo -n "  NPU Worker (optional)... "
    if timeout 3 curl -s "http://${VMS["npu-worker"]}:$NPU_WORKER_PORT" >/dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${YELLOW}⚠️ Not running${NC}"
    fi

    local health_percentage=$((healthy_vms * 100 / total_required_vms))
    log "VM Health: $healthy_vms/$total_required_vms required services healthy ($health_percentage%)"

    # Return success if >= 75% of required services are healthy (3 out of 4)
    if [ $health_percentage -ge 75 ]; then
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

    # Check Redis (with authentication if password is set)
    echo -n "  Redis (${VMS["redis"]}:$REDIS_PORT)... "
    if timeout 3 redis-cli -h "${VMS["redis"]}" -a "${AUTOBOT_REDIS_PASSWORD:-}" --no-auth-warning ping 2>/dev/null | grep -q PONG; then
        echo -e "${GREEN}✅ Running${NC}"
    else
        echo -e "${RED}❌ Not running${NC}"
        echo -e "${YELLOW}    Start with: bash scripts/vm-management/start-redis.sh${NC}"
    fi

    # Check Grafana dashboards sync (Issue #697)
    echo -n "  Grafana Dashboards (${VMS["redis"]})... "
    if [ -f "scripts/utilities/sync-grafana-dashboards.sh" ]; then
        if ./scripts/utilities/sync-grafana-dashboards.sh --check --quiet 2>/dev/null; then
            echo -e "${GREEN}✅ Synced${NC}"
        else
            echo -e "${YELLOW}⚠️ Out of sync${NC}"
            echo -e "${YELLOW}    Sync with: ./scripts/utilities/sync-grafana-dashboards.sh${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️ Sync script not found${NC}"
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
                    echo -e "${YELLOW}⚠️ Not running (optional - AI acceleration helper)${NC}"
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

        # Start VNC services using systemd (non-blocking - don't fail if VNC has issues)
        echo "Starting VNC services..."

        # Use || true to prevent set -e from exiting on VNC failures
        # VNC is optional - backend should start regardless
        if sudo systemctl start xvfb@1 vncserver@1 novnc 2>/dev/null || true; then
            sleep 2  # Reduced from 3 seconds
            if systemctl is-active --quiet xvfb@1 && systemctl is-active --quiet vncserver@1 && systemctl is-active --quiet novnc; then
                echo -e "${GREEN}✅ VNC Desktop available at: ${BLUE}http://localhost:6080/vnc.html${NC}"
            else
                echo -e "${YELLOW}⚠️  VNC services partially started or failed. Check: ${BLUE}sudo systemctl status xvfb@1 vncserver@1 novnc${NC}"
                echo -e "${CYAN}ℹ️  Continuing without VNC desktop - backend will still start${NC}"
                DESKTOP_ACCESS=false
            fi
        else
            echo -e "${YELLOW}⚠️  VNC services not available. Run: ${BLUE}bash setup.sh desktop${NC}"
            echo -e "${CYAN}ℹ️  Continuing without VNC desktop - backend will still start${NC}"
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

    # Set TensorFlow environment variables to suppress warnings (PRODUCTION MODE ONLY)
    # In dev mode, show all warnings/errors for debugging
    if [ "$DEV_MODE" = false ]; then
        export TF_CPP_MIN_LOG_LEVEL=2              # Suppress INFO and WARNING logs
        export TF_ENABLE_ONEDNN_OPTS=0             # Disable oneDNN custom operations message
        export GRPC_VERBOSITY=ERROR                # Reduce gRPC logging
        log "TensorFlow warnings suppressed (production mode)"
    else
        export TF_CPP_MIN_LOG_LEVEL=0              # Show all logs in dev mode
        log "TensorFlow warnings enabled (development mode)"
    fi

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

    # Start Celery worker for async task processing (RBAC, background jobs, etc.)
    log "Starting Celery worker for async task processing..."
    nohup celery -A backend.celery_app worker --loglevel=info > logs/celery.log 2>&1 &
    local celery_pid=$!

    # Brief wait to verify Celery started
    sleep 2
    if kill -0 "$celery_pid" 2>/dev/null; then
        success "Celery worker started (PID: $celery_pid)"
    else
        warning "Celery worker may have failed to start. Check logs: tail -f logs/celery.log"
    fi
}

stop_backend() {
    log "Stopping all AutoBot services (backend + Celery + VMs)..."

    # Stop local backend and Celery processes with verification
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
    log "Shutting down AutoBot backend and Celery worker..."

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

    # Stop backend and Celery with improved process matching
    kill_autobot_processes 5

    success "AutoBot backend and Celery worker stopped"
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
    local optional_services=("npu-worker")  # Services that don't block startup

    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        echo -n "  Testing $vm_name ($vm_ip)... "

        # Check if this is the local backend host (skip SSH check for local services)
        if [ "$vm_ip" = "$BACKEND_HOST" ]; then
            echo -e "${CYAN}⚡ Local service${NC}"
            continue
        fi

        if timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Connected${NC}"
        else
            # Check if this is an optional service
            local is_optional=false
            for opt_svc in "${optional_services[@]}"; do
                if [ "$vm_name" = "$opt_svc" ]; then
                    is_optional=true
                    break
                fi
            done

            if [ "$is_optional" = true ]; then
                echo -e "${YELLOW}⚠️ Not available (optional)${NC}"
            else
                echo -e "${RED}❌ Failed${NC}"
                connectivity_failed=true
            fi
        fi
    done

    if [ "$connectivity_failed" = true ]; then
        warning "Some required VMs are not accessible"
        echo -e "${YELLOW}Use: bash setup.sh initial --distributed  # To configure VM connectivity${NC}"
        echo -e "${CYAN}Backend will start anyway, but some VM services may not be available${NC}"
    else
        success "All required VMs are accessible"
    fi
}

verify_redis_permissions() {
    log "Verifying Redis directory permissions..."

    if [ ! -f "$SSH_KEY" ]; then
        warning "SSH key not found - skipping permission verification"
        return 0
    fi

    timeout 10 ssh -i "$SSH_KEY" "$SSH_USER@${VMS["redis"]}" << 'EOF'
        # Check if directories exist before checking ownership
        if [ ! -d /var/lib/redis-stack ]; then
            echo "ℹ️  Redis data directory not yet created - will be created on first start"
            exit 0
        fi

        if [ ! -d /var/log/redis-stack ]; then
            echo "ℹ️  Redis log directory not yet created - will be created on first start"
            exit 0
        fi

        # Check /var/lib/redis-stack ownership
        REDIS_DATA_OWNER=$(stat -c '%U:%G' /var/lib/redis-stack 2>/dev/null)
        REDIS_LOG_OWNER=$(stat -c '%U:%G' /var/log/redis-stack 2>/dev/null)

        if [ "$REDIS_DATA_OWNER" != "autobot:autobot" ]; then
            echo "⚠️  WARNING: Redis data directory ownership incorrect: $REDIS_DATA_OWNER"
            echo "🔧 Correcting ownership to autobot:autobot..."
            if ! sudo chown -R autobot:autobot /var/lib/redis-stack; then
                echo "❌ ERROR: Failed to change ownership of Redis data directory"
                exit 1
            fi
        else
            echo "✅ Redis data directory ownership correct: $REDIS_DATA_OWNER"
        fi

        if [ "$REDIS_LOG_OWNER" != "autobot:autobot" ]; then
            echo "⚠️  WARNING: Redis log directory ownership incorrect: $REDIS_LOG_OWNER"
            echo "🔧 Correcting ownership to autobot:autobot..."
            if ! sudo chown -R autobot:autobot /var/log/redis-stack; then
                echo "❌ ERROR: Failed to change ownership of Redis log directory"
                exit 1
            fi
        else
            echo "✅ Redis log directory ownership correct: $REDIS_LOG_OWNER"
        fi
EOF

    if [ $? -eq 0 ]; then
        success "Redis permissions verified and corrected"
    else
        warning "Redis permission verification failed"
    fi
}

start_redis_stack() {
    log "Starting Redis Stack service on VM3..."

    # Load Redis password from .env for authentication
    if [ -f ".env" ]; then
        set -a  # Export all variables
        source .env
        set +a  # Disable export
    fi

    if [ ! -f "$SSH_KEY" ]; then
        warning "SSH key not found - skipping Redis Stack auto-start"
        return 0
    fi

    # Check if Redis Stack is already running
    echo -n "  Checking Redis Stack status... "
    if timeout 3 redis-cli -h "${VMS["redis"]}" -a "${AUTOBOT_REDIS_PASSWORD:-}" --no-auth-warning ping 2>/dev/null | grep -q PONG; then
        echo -e "${GREEN}✅ Already running${NC}"
        return 0
    fi
    echo -e "${YELLOW}⚠️  Not running${NC}"

    # Start Redis Stack via systemd on VM3
    log "Starting Redis Stack systemd service on ${VMS["redis"]}..."

    timeout 15 ssh -i "$SSH_KEY" "$SSH_USER@${VMS["redis"]}" << 'EOF'
        # Check if service exists
        if ! systemctl list-unit-files redis-stack-server.service >/dev/null 2>&1; then
            echo "⚠️  WARNING: redis-stack-server.service not found"
            echo "Run: bash scripts/vm-management/start-redis.sh"
            exit 1
        fi

        # Start the service
        echo "Starting redis-stack-server service..."
        if ! sudo systemctl start redis-stack-server; then
            echo "❌ ERROR: Failed to start redis-stack-server service"
            exit 1
        fi

        echo "Service start command sent, waiting for Redis to be ready..."

        # Wait for Redis to be ready (up to 10 seconds)
        for i in {1..10}; do
            if redis-cli ping 2>/dev/null | grep -q PONG; then
                echo "✅ Redis Stack is ready"
                exit 0
            fi
            sleep 1
            echo -n "."
        done

        echo ""
        echo "⚠️  Redis Stack service started but may still be loading dataset"
        echo "This is normal for large datasets. Backend will wait for Redis to be ready."
        exit 0
EOF

    local ssh_status=$?

    if [ $ssh_status -eq 0 ]; then
        success "Redis Stack service started successfully"

        # Wait for Redis to complete loading dataset (critical for backend startup)
        log "Waiting for Redis to complete dataset loading..."
        local retries=0
        local max_retries=600  # Up to 10 minutes for large datasets (3+ GB)
        while [ $retries -lt $max_retries ]; do
            local redis_response=$(timeout 2 redis-cli -h "${VMS["redis"]}" -a "${AUTOBOT_REDIS_PASSWORD:-}" --no-auth-warning ping 2>&1 || true)

            # Check if Redis is ready (responds with PONG)
            if echo "$redis_response" | grep -q "^PONG$"; then
                echo ""
                success "Redis fully ready - dataset loaded successfully"
                return 0
            fi

            # Check if Redis is still loading
            if echo "$redis_response" | grep -q "LOADING"; then
                if [ $((retries % 10)) -eq 0 ]; then
                    echo ""
                    info "Redis loading dataset... ($retries seconds elapsed)"
                fi
                echo -n "."
            fi

            sleep 1
            retries=$((retries + 1))
        done
        echo ""
        error "Redis failed to complete loading after $max_retries seconds"
        error "Backend startup ABORTED - Redis must be fully loaded"
        echo -e "${YELLOW}Check Redis status: ssh autobot@${VMS["redis"]} 'redis-cli INFO persistence'${NC}"
        exit 1
    else
        error "Redis Stack auto-start failed"
        echo -e "${YELLOW}Manual start: bash scripts/vm-management/start-redis.sh${NC}"
        exit 1
    fi
}

start_frontend_dev() {
    if [ "$DEV_MODE" = true ]; then
        echo -e "${CYAN}🔧 Starting Frontend Development Mode...${NC}"

        # Development mode: Sync code to VM (sync script handles: Stop → Clean → Sync → Start)
        echo "  📦 Syncing frontend code to VM..."
        echo "  🔄 Process: Stop Vite → Clear cache → Sync files → Start Vite"

        # Check if sync script exists and run it
        if [ -f "scripts/utilities/sync-frontend.sh" ]; then
            ./scripts/utilities/sync-frontend.sh all
        elif [ -f "sync-frontend.sh" ]; then
            ./sync-frontend.sh all
        else
            echo -e "${YELLOW}  ⚠️  Sync script not found - code may be outdated on frontend VM${NC}"
            echo -e "${YELLOW}  ⚠️  Attempting manual frontend startup...${NC}"

            # Fallback: manual startup if sync script missing
            timeout 3 ssh -T -i "$SSH_KEY" "$SSH_USER@${VMS["frontend"]}" "pkill -f 'npm.*dev' 2>/dev/null || true; pkill -f 'vite.*5173' 2>/dev/null || true" 2>/dev/null
            sleep 1
            timeout 5 ssh -T -i "$SSH_KEY" "$SSH_USER@${VMS["frontend"]}" "cd autobot-vue && VITE_BACKEND_HOST=$BACKEND_HOST VITE_BACKEND_PORT=$BACKEND_PORT nohup npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT > /tmp/vite.log 2>&1 < /dev/null &"
        fi

        # Wait for Vite to start
        echo "  ⏳ Waiting for Vite to start..."
        sleep 3

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

    # Verify Redis permissions
    verify_redis_permissions

    # Start Redis Stack service automatically
    start_redis_stack

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

    # Sync Grafana dashboards (Issue #697)
    if [ -f "scripts/utilities/sync-grafana-dashboards.sh" ]; then
        log "Syncing Grafana dashboards..."
        ./scripts/utilities/sync-grafana-dashboards.sh --quiet || true
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
