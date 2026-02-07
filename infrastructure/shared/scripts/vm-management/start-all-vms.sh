#!/bin/bash
# AutoBot - Start All VM Services
# Starts all distributed VM services in the correct order

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

start_redis_vm() {
    log "Starting Redis service on VM (${VMS["redis"]})..."

    # Use the dedicated Redis startup script
    if bash "$(dirname "$0")/start-redis.sh"; then
        success "Redis VM service started"
    else
        error "Failed to start Redis VM service"
        return 1
    fi
}

start_frontend_vm() {
    log "Starting Frontend service on VM (${VMS["frontend"]})..."

    ssh -T -i "$SSH_KEY" "$SSH_USER@${VMS["frontend"]}" << 'EOF'
        # Check required packages and install if missing (requires passwordless sudo)
        if ! command -v nc >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1; then
            echo "Missing required packages. Attempting installation..."
            echo "NOTE: This requires passwordless sudo. Run scripts/utilities/setup-passwordless-sudo.sh first."

            # Try to install packages (will fail gracefully if sudo requires password)
            if sudo -n true 2>/dev/null; then
                echo "Installing required packages (netcat, nodejs, npm)..."
                sudo apt-get update -qq

                # Install Node.js 18.x for frontend
                curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - 2>/dev/null
                sudo apt-get install -y netcat-openbsd nodejs
                echo "Packages installed successfully"
            else
                echo "Cannot install packages: passwordless sudo not configured"
                echo "   Run: bash scripts/utilities/setup-passwordless-sudo.sh"
                echo "   Continuing without package installation..."
            fi
        fi

        # Create AutoBot directory structure if it doesn't exist
        if [ ! -d ~/AutoBot ]; then
            echo "Creating AutoBot directory structure..."
            mkdir -p ~/AutoBot
            echo "Note: AutoBot source code needs to be synced to this VM"
            echo "Run: bash scripts/utilities/sync-to-vm.sh frontend"
        fi

        cd ~/autobot-vue 2>/dev/null || {
            echo "AutoBot frontend directory not found. Creating placeholder..."
            mkdir -p ~/autobot-vue
            echo "Run sync script to deploy frontend: bash scripts/utilities/sync-to-vm.sh frontend"
            exit 1
        }

        # Stop existing frontend processes
        pkill -f "npm.*dev" || true

        # Set environment variables for backend connection
        export VITE_BACKEND_HOST=172.16.168.20
        export VITE_BACKEND_PORT=8001

        # Create logs directory
        mkdir -p logs

        # Start frontend
        nohup npm run dev -- --host 0.0.0.0 --port 5173 > logs/frontend.log 2>&1 &

        # Wait for frontend to be ready
        echo "Waiting for frontend to start..."
        for i in {1..30}; do
            if curl -s http://localhost:5173 >/dev/null 2>&1; then
                echo "Frontend is ready"
                exit 0
            fi
            sleep 1
        done
        echo "Warning: Frontend may need more time to start"
EOF

    if [ $? -eq 0 ]; then
        success "Frontend VM service started"
    else
        error "Failed to start Frontend VM service"
        return 1
    fi
}

start_npu_worker_vm() {
    log "Starting NPU Worker service on VM (${VMS["npu-worker"]})..."

    ssh -T -i "$SSH_KEY" "$SSH_USER@${VMS["npu-worker"]}" << 'EOF'
        # Check required packages and install if missing (requires passwordless sudo)
        if ! command -v python3 >/dev/null 2>&1; then
            echo "Missing Python3. Attempting installation..."
            if sudo -n true 2>/dev/null; then
                echo "Installing required packages (python3, venv)..."
                sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv python3-pip
                echo "Python packages installed successfully"
            else
                echo "Cannot install packages: passwordless sudo not configured"
                echo "   Run: bash scripts/utilities/setup-passwordless-sudo.sh"
                echo "   Continuing without package installation..."
            fi
        fi

        # Create AutoBot directory structure if it doesn't exist
        if [ ! -d ~/AutoBot ]; then
            echo "Creating AutoBot directory structure..."
            mkdir -p ~/AutoBot
            echo "Note: AutoBot source code needs to be synced to this VM"
            echo "Run: bash scripts/utilities/sync-to-vm.sh npu-worker"
        fi

        cd ~/AutoBot 2>/dev/null || {
            echo "AutoBot directory not found. Creating placeholder..."
            mkdir -p ~/AutoBot
            echo "Run sync script to deploy backend: bash scripts/utilities/sync-to-vm.sh npu-worker"
            exit 1
        }

        # Create or activate virtual environment
        if [ ! -d "venv" ]; then
            echo "Creating Python virtual environment..."
            python3 -m venv venv
            source venv/bin/activate
            pip install --upgrade pip

            # Install basic dependencies for NPU worker
            pip install fastapi uvicorn requests aiohttp
        else
            source venv/bin/activate
        fi

        # Stop existing NPU worker processes
        pkill -f "npu.*worker" || true

        # Set environment variables
        export PYTHONPATH="$(pwd)"
        export AUTOBOT_NPU_WORKER_HOST=0.0.0.0
        export AUTOBOT_NPU_WORKER_PORT=8081

        # Create logs directory
        mkdir -p logs

        # Start NPU worker (placeholder - replace with actual NPU worker startup)
        nohup python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'healthy', 'service': 'npu-worker'}).encode())
        else:
            self.send_response(404)
            self.end_headers()

httpd = HTTPServer(('0.0.0.0', 8081), HealthHandler)
print('NPU Worker mock service running on port 8081')
httpd.serve_forever()
" > logs/npu-worker.log 2>&1 &

        echo "NPU Worker service started"
EOF

    if [ $? -eq 0 ]; then
        success "NPU Worker VM service started"
    else
        error "Failed to start NPU Worker VM service"
        return 1
    fi
}

start_ai_stack_vm() {
    log "Starting AI Stack service on VM (${VMS["ai-stack"]})..."

    ssh -T -i "$SSH_KEY" "$SSH_USER@${VMS["ai-stack"]}" << 'EOF'
        # Ensure required packages are installed
        if ! command -v python3 >/dev/null 2>&1; then
            echo "Installing required packages (python3, venv)..."
            sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
        fi

        # Create AutoBot directory structure if it doesn't exist
        if [ ! -d ~/AutoBot ]; then
            echo "Creating AutoBot directory structure..."
            mkdir -p ~/AutoBot
            echo "Note: AutoBot source code needs to be synced to this VM"
            echo "Run: bash scripts/utilities/sync-to-vm.sh ai-stack"
        fi

        cd ~/AutoBot 2>/dev/null || {
            echo "AutoBot directory not found. Creating placeholder..."
            mkdir -p ~/AutoBot
            echo "Run sync script to deploy backend: bash scripts/utilities/sync-to-vm.sh ai-stack"
            exit 1
        }

        # Create or activate virtual environment
        if [ ! -d "venv" ]; then
            echo "Creating Python virtual environment..."
            python3 -m venv venv
            source venv/bin/activate
            pip install --upgrade pip

            # Install basic dependencies for AI stack
            pip install fastapi uvicorn requests aiohttp
        else
            source venv/bin/activate
        fi

        # Stop existing AI stack processes
        pkill -f "ai.*stack" || true

        # Set environment variables
        export PYTHONPATH="$(pwd)"
        export AUTOBOT_AI_STACK_HOST=0.0.0.0
        export AUTOBOT_AI_STACK_PORT=8080

        # Create logs directory
        mkdir -p logs

        # Start AI stack (placeholder - replace with actual AI stack startup)
        nohup python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'healthy', 'service': 'ai-stack'}).encode())
        else:
            self.send_response(404)
            self.end_headers()

httpd = HTTPServer(('0.0.0.0', 8080), HealthHandler)
print('AI Stack mock service running on port 8080')
httpd.serve_forever()
" > logs/ai-stack.log 2>&1 &

        echo "AI Stack service started"
EOF

    if [ $? -eq 0 ]; then
        success "AI Stack VM service started"
    else
        error "Failed to start AI Stack VM service"
        return 1
    fi
}

start_browser_vm() {
    log "Starting Browser service on VM (${VMS["browser"]})..."

    ssh -T -i "$SSH_KEY" "$SSH_USER@${VMS["browser"]}" << 'EOF'
        # Ensure required packages are installed (including Xvfb for headless browser)
        if ! command -v python3 >/dev/null 2>&1 || ! command -v Xvfb >/dev/null 2>&1; then
            echo "Installing required packages (python3, venv, xvfb)..."
            sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip xvfb
        fi

        # Create AutoBot directory structure if it doesn't exist
        if [ ! -d ~/AutoBot ]; then
            echo "Creating AutoBot directory structure..."
            mkdir -p ~/AutoBot
            echo "Note: AutoBot source code needs to be synced to this VM"
            echo "Run: bash scripts/utilities/sync-to-vm.sh browser"
        fi

        cd ~/AutoBot 2>/dev/null || {
            echo "AutoBot directory not found. Creating placeholder..."
            mkdir -p ~/AutoBot
            echo "Run sync script to deploy browser service: bash scripts/utilities/sync-to-vm.sh browser"
            exit 1
        }

        # Create or activate virtual environment
        if [ ! -d "venv" ]; then
            echo "Creating Python virtual environment..."
            python3 -m venv venv
            source venv/bin/activate
            pip install --upgrade pip

            # Install basic dependencies for browser service
            pip install fastapi uvicorn requests aiohttp playwright

            # Install Playwright browsers if needed
            playwright install chromium
        else
            source venv/bin/activate
        fi

        # Stop existing browser service processes
        pkill -f "browser.*service" || true

        # Set environment variables
        export PYTHONPATH="$(pwd)"
        export AUTOBOT_BROWSER_SERVICE_HOST=0.0.0.0
        export AUTOBOT_BROWSER_SERVICE_PORT=3000
        export DISPLAY=:99

        # Create logs directory
        mkdir -p logs

        # Start Xvfb for headless browser
        Xvfb :99 -screen 0 1920x1080x24 &

        # Start browser service (placeholder - replace with actual browser service startup)
        nohup python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'healthy', 'service': 'browser-automation'}).encode())
        else:
            self.send_response(404)
            self.end_headers()

httpd = HTTPServer(('0.0.0.0', 3000), HealthHandler)
print('Browser service mock running on port 3000')
httpd.serve_forever()
" > logs/browser-service.log 2>&1 &

        echo "Browser service started"
EOF

    if [ $? -eq 0 ]; then
        success "Browser VM service started"
    else
        error "Failed to start Browser VM service"
        return 1
    fi
}

check_ssh_connectivity() {
    log "Checking SSH connectivity to all VMs..."

    if [ ! -f "$SSH_KEY" ]; then
        error "SSH key not found: $SSH_KEY"
        echo "Run: bash setup.sh ssh-keys"
        exit 1
    fi

    local failed_vms=()

    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        echo -n "  Testing $vm_name ($vm_ip)... "

        if timeout 5 ssh -T -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "echo 'ok'" >/dev/null 2>&1; then
            echo -e "${GREEN}Connected${NC}"
        else
            echo -e "${RED}Failed${NC}"
            failed_vms+=("$vm_name")
        fi
    done

    if [ ${#failed_vms[@]} -gt 0 ]; then
        error "Cannot connect to VMs: ${failed_vms[*]}"
        echo "Please ensure VMs are running and SSH keys are configured"
        exit 1
    fi

    success "All VMs are accessible"
}

main() {
    echo -e "${GREEN}AutoBot - Starting All VM Services${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo ""

    # Ensure netcat is installed on local machine for health checks
    if ! command -v nc >/dev/null 2>&1; then
        echo "Installing netcat on local machine for health checks..."
        sudo apt-get update && sudo apt-get install -y netcat-openbsd
    fi

    # Check SSH connectivity first
    check_ssh_connectivity
    echo ""

    # Start services in dependency order
    log "Starting VM services in dependency order..."
    echo ""

    # 1. Redis (required by all other services)
    start_redis_vm
    echo ""

    # 2. AI Stack and NPU Worker (can start in parallel)
    start_ai_stack_vm &
    start_npu_worker_vm &
    wait
    echo ""

    # 3. Browser service
    start_browser_vm
    echo ""

    # 4. Frontend (should start last to ensure backend connectivity)
    start_frontend_vm
    echo ""

    # Wait for all services to initialize
    log "Waiting for all services to initialize..."
    sleep 10

    # Check service health
    log "Checking service health..."

    echo -n "  Redis... "
    if echo "PING" | nc -w 2 "${VMS["redis"]}" "$AUTOBOT_REDIS_PORT" | grep -q "PONG" 2>/dev/null; then
        echo -e "${GREEN}Healthy${NC}"
    else
        echo -e "${RED}Unhealthy${NC}"
    fi

    echo -n "  Frontend... "
    if timeout 3 curl -s "http://${VMS["frontend"]}:$AUTOBOT_FRONTEND_PORT" >/dev/null 2>&1; then
        echo -e "${GREEN}Healthy${NC}"
    else
        echo -e "${RED}Unhealthy${NC}"
    fi

    echo -n "  NPU Worker... "
    if timeout 3 curl -s "http://${VMS["npu-worker"]}:$AUTOBOT_NPU_WORKER_PORT/health" >/dev/null 2>&1; then
        echo -e "${GREEN}Healthy${NC}"
    else
        echo -e "${RED}Unhealthy${NC}"
    fi

    echo -n "  AI Stack... "
    if timeout 3 curl -s "http://${VMS["ai-stack"]}:$AUTOBOT_AI_STACK_PORT/health" >/dev/null 2>&1; then
        echo -e "${GREEN}Healthy${NC}"
    else
        echo -e "${RED}Unhealthy${NC}"
    fi

    echo -n "  Browser... "
    if timeout 3 curl -s "http://${VMS["browser"]}:$AUTOBOT_BROWSER_SERVICE_PORT/health" >/dev/null 2>&1; then
        echo -e "${GREEN}Healthy${NC}"
    else
        echo -e "${RED}Unhealthy${NC}"
    fi

    echo ""
    success "VM services startup completed!"
    echo ""
    echo -e "${BLUE}Access Points:${NC}"
    echo -e "${CYAN}  Frontend:   http://${VMS["frontend"]}:$AUTOBOT_FRONTEND_PORT${NC}"
    echo -e "${CYAN}  Redis:      ${VMS["redis"]}:$AUTOBOT_REDIS_PORT${NC}"
    echo -e "${CYAN}  AI Stack:   http://${VMS["ai-stack"]}:$AUTOBOT_AI_STACK_PORT/health${NC}"
    echo -e "${CYAN}  NPU Worker: http://${VMS["npu-worker"]}:$AUTOBOT_NPU_WORKER_PORT/health${NC}"
    echo -e "${CYAN}  Browser:    http://${VMS["browser"]}:$AUTOBOT_BROWSER_SERVICE_PORT/health${NC}"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo -e "${CYAN}  1. Start backend: bash run_autobot.sh --dev${NC}"
    echo -e "${CYAN}  2. Check full status: bash run_autobot.sh --status${NC}"
    echo ""
}

main
