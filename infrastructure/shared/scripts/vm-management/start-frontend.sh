#!/bin/bash
# AutoBot - Start Frontend Service on VM
# Starts only the frontend service on 172.16.168.21

set -e

# Source SSOT configuration (#808)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${AUTOBOT_SSH_USER:-autobot}"
FRONTEND_IP="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

main() {
    echo -e "${GREEN}🌐 Starting Frontend Service${NC}"
    echo -e "${BLUE}VM: $FRONTEND_IP${NC}"
    echo ""

    if [ ! -f "$SSH_KEY" ]; then
        error "SSH key not found: $SSH_KEY"
        echo "Run: bash setup.sh ssh-keys"
        exit 1
    fi

    log "Connecting to Frontend VM..."

    ssh -i "$SSH_KEY" "$SSH_USER@$FRONTEND_IP" << 'EOF'
        cd ~/AutoBot/autobot-slm-frontend || {
            echo "Error: AutoBot frontend directory not found"
            exit 1
        }

        echo "Stopping existing frontend processes..."
        pkill -f "npm.*dev" || true
        pkill -f "node.*vite" || true

        # Wait for processes to stop
        sleep 2

        # Set environment variables for backend connection
        export VITE_BACKEND_HOST=${AUTOBOT_BACKEND_HOST:-172.16.168.20}
        export VITE_BACKEND_PORT=8001

        echo "Starting frontend service..."
        mkdir -p logs
        nohup npm run dev -- --host 0.0.0.0 --port 5173 > logs/frontend.log 2>&1 &

        # Wait for frontend to start
        echo "Waiting for frontend to be ready..."
        for i in {1..30}; do
            if curl -s http://localhost:5173 >/dev/null 2>&1; then
                echo "Frontend is ready!"
                break
            fi
            sleep 1
            echo -n "."
        done

        echo ""
        echo "Frontend service started successfully"
EOF

    if [ $? -eq 0 ]; then
        success "Frontend service started on $FRONTEND_IP:5173"
        echo ""
        echo -e "${CYAN}Access URL: http://$FRONTEND_IP:5173${NC}"
        echo -e "${BLUE}Check logs: ssh $SSH_USER@$FRONTEND_IP 'tail -f ~/AutoBot/autobot-slm-frontend/logs/frontend.log'${NC}"
    else
        error "Failed to start frontend service"
        exit 1
    fi
}

main
