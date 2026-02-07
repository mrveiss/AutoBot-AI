#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Node Exporter Installation Script
# Installs node_exporter on all VMs for per-machine system metrics

set -e

# =============================================================================
# SSOT Configuration - Issue #694
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/ssot-config.sh" 2>/dev/null || source "$SCRIPT_DIR/../lib/ssot-config.sh" 2>/dev/null || {
    # Fallback if lib not found
    PROJECT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
    [ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }
}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
NODE_EXPORTER_VERSION="1.7.0"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${AUTOBOT_SSH_USER:-autobot}"

# VM configuration using SSOT variables
declare -A VMS=(
    ["main"]="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
    ["frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

# Logging functions
log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

install_node_exporter() {
    local vm_name=$1
    local vm_ip=$2

    log "Installing node_exporter on $vm_name ($vm_ip)..."

    if [ "$vm_name" = "main" ]; then
        # Install locally on main machine
        echo "Installing on main machine (localhost)..."

        # Download and extract
        cd /tmp
        wget -q https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
        tar xzf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz

        # Copy binary
        sudo cp node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter /usr/local/bin/

        # Create user
        sudo useradd --no-create-home --shell /bin/false node_exporter 2>/dev/null || true

        # Create systemd service
        sudo tee /etc/systemd/system/node_exporter.service > /dev/null << 'EOF'
[Unit]
Description=Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=node_exporter
Group=node_exporter
ExecStart=/usr/local/bin/node_exporter \
  --web.listen-address=0.0.0.0:9100

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

        # Enable and start
        sudo systemctl daemon-reload
        sudo systemctl enable node_exporter
        sudo systemctl start node_exporter

        # Cleanup
        cd /tmp
        rm -rf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64*

        success "Main machine node_exporter installed"
    else
        # Install on remote VM
        ssh -i "$SSH_KEY" "$SSH_USER@$vm_ip" << ENDSSH
            set -e

            # Download and extract
            cd /tmp
            wget -q https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
            tar xzf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz

            # Copy binary
            sudo cp node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter /usr/local/bin/

            # Create user
            sudo useradd --no-create-home --shell /bin/false node_exporter 2>/dev/null || true

            # Create systemd service
            sudo tee /etc/systemd/system/node_exporter.service > /dev/null << 'EOF'
[Unit]
Description=Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=node_exporter
Group=node_exporter
ExecStart=/usr/local/bin/node_exporter \\
  --web.listen-address=0.0.0.0:9100

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

            # Enable and start
            sudo systemctl daemon-reload
            sudo systemctl enable node_exporter
            sudo systemctl start node_exporter

            # Cleanup
            cd /tmp
            rm -rf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64*

            echo "Node exporter installed on $vm_name"
ENDSSH

        success "$vm_name node_exporter installed"
    fi
}

verify_installation() {
    local vm_name=$1
    local vm_ip=$2

    echo -n "  Verifying $vm_name ($vm_ip)... "
    if timeout 3 curl -s "http://$vm_ip:9100/metrics" | grep -q "node_cpu_seconds_total"; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}Failed${NC}"
        return 1
    fi
}

main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Node Exporter Installation (All VMs)${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "This will install node_exporter v${NODE_EXPORTER_VERSION} on:"
    for vm_name in "${!VMS[@]}"; do
        echo "  - $vm_name (${VMS[$vm_name]})"
    done
    echo ""

    read -p "Continue with installation? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi

    # Install on all VMs
    for vm_name in "${!VMS[@]}"; do
        install_node_exporter "$vm_name" "${VMS[$vm_name]}"
    done

    echo ""
    log "Waiting for services to start..."
    sleep 3

    echo ""
    log "Verifying installations..."
    for vm_name in "${!VMS[@]}"; do
        verify_installation "$vm_name" "${VMS[$vm_name]}"
    done

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Installation Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Node exporters running on all machines"
    echo ""
    echo "Metrics available at:"
    for vm_name in "${!VMS[@]}"; do
        echo "  http://${VMS[$vm_name]}:9100/metrics"
    done
    echo ""
    echo "Next steps:"
    echo "  1. Prometheus will automatically start scraping these endpoints"
    echo "  2. Wait ~30 seconds for first scrape"
    echo "  3. View per-machine metrics in Grafana dashboards"
    echo ""
}

main "$@"
