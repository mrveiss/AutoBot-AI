#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Prometheus + Grafana + AlertManager Installation Script (Epic #80)
# Installs complete monitoring stack on VM3 (Redis VM - 172.16.168.23)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/ssot-config.sh" 2>/dev/null || true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
PROMETHEUS_VERSION="2.47.0"
ALERTMANAGER_VERSION="0.26.0"
GRAFANA_VERSION="10.2.0"

TARGET_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
TARGET_USER="${AUTOBOT_SSH_USER:-autobot}"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"

# Logging functions
log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Check SSH connectivity
check_connection() {
    log "Checking connection to $TARGET_HOST..."
    if ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$TARGET_USER@$TARGET_HOST" "echo 'Connection OK'" > /dev/null 2>&1; then
        success "Connected to $TARGET_HOST"
    else
        error "Cannot connect to $TARGET_HOST"
        exit 1
    fi
}

# Install Prometheus
install_prometheus() {
    log "Installing Prometheus $PROMETHEUS_VERSION on $TARGET_HOST..."

    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" << 'ENDSSH'
        set -e

        # Download and extract Prometheus
        cd /tmp
        wget -q https://github.com/prometheus/prometheus/releases/download/v2.47.0/prometheus-2.47.0.linux-amd64.tar.gz
        tar xzf prometheus-2.47.0.linux-amd64.tar.gz

        # Create directories
        sudo mkdir -p /etc/prometheus /var/lib/prometheus

        # Copy binaries
        cd prometheus-2.47.0.linux-amd64
        sudo cp prometheus promtool /usr/local/bin/
        sudo cp -r consoles/ console_libraries/ /etc/prometheus/

        # Set ownership
        sudo useradd --no-create-home --shell /bin/false prometheus 2>/dev/null || true
        sudo chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus

        # Cleanup
        cd /tmp
        rm -rf prometheus-2.47.0.linux-amd64*

        echo "Prometheus installed successfully"
ENDSSH

    success "Prometheus installed"
}

# Install AlertManager
install_alertmanager() {
    log "Installing AlertManager $ALERTMANAGER_VERSION on $TARGET_HOST..."

    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" << 'ENDSSH'
        set -e

        # Download and extract AlertManager
        cd /tmp
        wget -q https://github.com/prometheus/alertmanager/releases/download/v0.26.0/alertmanager-0.26.0.linux-amd64.tar.gz
        tar xzf alertmanager-0.26.0.linux-amd64.tar.gz

        # Create directories
        sudo mkdir -p /etc/alertmanager /var/lib/alertmanager

        # Copy binaries
        cd alertmanager-0.26.0.linux-amd64
        sudo cp alertmanager amtool /usr/local/bin/

        # Set ownership
        sudo useradd --no-create-home --shell /bin/false alertmanager 2>/dev/null || true
        sudo chown -R alertmanager:alertmanager /etc/alertmanager /var/lib/alertmanager

        # Cleanup
        cd /tmp
        rm -rf alertmanager-0.26.0.linux-amd64*

        echo "AlertManager installed successfully"
ENDSSH

    success "AlertManager installed"
}

# Install Grafana
install_grafana() {
    log "Installing Grafana $GRAFANA_VERSION on $TARGET_HOST..."

    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" << 'ENDSSH'
        set -e

        # Add Grafana APT repository
        sudo apt-get install -y apt-transport-https software-properties-common wget
        sudo mkdir -p /etc/apt/keyrings/
        wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
        echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list

        # Install Grafana
        sudo apt-get update
        sudo apt-get install -y grafana

        echo "Grafana installed successfully"
ENDSSH

    success "Grafana installed"
}

# Copy configuration files
copy_configs() {
    log "Copying configuration files to $TARGET_HOST..."

    # Copy Prometheus config
    scp -i "$SSH_KEY" /home/kali/Desktop/AutoBot/config/prometheus/prometheus.yml \
        "$TARGET_USER@$TARGET_HOST:/tmp/prometheus.yml"
    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" "sudo mv /tmp/prometheus.yml /etc/prometheus/prometheus.yml && sudo chown prometheus:prometheus /etc/prometheus/prometheus.yml"

    # Copy AlertManager config
    scp -i "$SSH_KEY" /home/kali/Desktop/AutoBot/config/prometheus/alertmanager.yml \
        "$TARGET_USER@$TARGET_HOST:/tmp/alertmanager.yml"
    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" "sudo mv /tmp/alertmanager.yml /etc/alertmanager/alertmanager.yml && sudo chown alertmanager:alertmanager /etc/alertmanager/alertmanager.yml"

    # Copy AlertManager rules
    scp -i "$SSH_KEY" /home/kali/Desktop/AutoBot/config/prometheus/alertmanager_rules.yml \
        "$TARGET_USER@$TARGET_HOST:/tmp/alertmanager_rules.yml"
    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" "sudo mv /tmp/alertmanager_rules.yml /etc/prometheus/alertmanager_rules.yml && sudo chown prometheus:prometheus /etc/prometheus/alertmanager_rules.yml"

    # Copy Grafana datasource config
    scp -i "$SSH_KEY" /home/kali/Desktop/AutoBot/config/grafana/provisioning/datasources/prometheus.yml \
        "$TARGET_USER@$TARGET_HOST:/tmp/prometheus_datasource.yml"
    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" "sudo mkdir -p /etc/grafana/provisioning/datasources && sudo mv /tmp/prometheus_datasource.yml /etc/grafana/provisioning/datasources/prometheus.yml"

    success "Configuration files copied"
}

# Create systemd services
create_services() {
    log "Creating systemd services on $TARGET_HOST..."

    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" << 'ENDSSH'
        # Prometheus service
        sudo tee /etc/systemd/system/prometheus.service > /dev/null << 'EOF'
[Unit]
Description=Prometheus Monitoring System
Documentation=https://prometheus.io/docs/introduction/overview/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=prometheus
Group=prometheus
ExecStart=/usr/local/bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus/ \
  --storage.tsdb.retention.time=30d \
  --web.console.templates=/etc/prometheus/consoles \
  --web.console.libraries=/etc/prometheus/console_libraries \
  --web.listen-address=0.0.0.0:9090 \
  --web.enable-lifecycle

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

        # AlertManager service
        sudo tee /etc/systemd/system/alertmanager.service > /dev/null << 'EOF'
[Unit]
Description=Prometheus AlertManager
Documentation=https://prometheus.io/docs/alerting/alertmanager/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=alertmanager
Group=alertmanager
ExecStart=/usr/local/bin/alertmanager \
  --config.file=/etc/alertmanager/alertmanager.yml \
  --storage.path=/var/lib/alertmanager/ \
  --web.listen-address=0.0.0.0:9093

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

        sudo systemctl daemon-reload
        echo "Systemd services created"
ENDSSH

    success "Systemd services created"
}

# Start services
start_services() {
    log "Starting services on $TARGET_HOST..."

    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" << 'ENDSSH'
        # Enable and start Prometheus
        sudo systemctl enable prometheus
        sudo systemctl start prometheus

        # Enable and start AlertManager
        sudo systemctl enable alertmanager
        sudo systemctl start alertmanager

        # Enable and start Grafana
        sudo systemctl enable grafana-server
        sudo systemctl start grafana-server

        echo "All services started"
ENDSSH

    success "All services started"
}

# Verify installation
verify_installation() {
    log "Verifying installation on $TARGET_HOST..."

    sleep 5  # Give services time to start

    # Check Prometheus
    if curl -s http://$TARGET_HOST:9090/-/healthy | grep -q "Prometheus is Healthy"; then
        success "Prometheus is running (http://$TARGET_HOST:9090)"
    else
        warning "Prometheus may not be running correctly"
    fi

    # Check AlertManager
    if curl -s http://$TARGET_HOST:9093/-/healthy | grep -q "OK"; then
        success "AlertManager is running (http://$TARGET_HOST:9093)"
    else
        warning "AlertManager may not be running correctly"
    fi

    # Check Grafana
    if curl -s http://$TARGET_HOST:3000/api/health | grep -q "ok"; then
        success "Grafana is running (http://$TARGET_HOST:3000)"
    else
        warning "Grafana may not be running correctly"
    fi
}

# Main installation
main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Prometheus + Grafana + AlertManager${NC}"
    echo -e "${GREEN}Installation Script (Epic #80)${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Target: $TARGET_HOST ($TARGET_USER)"
    echo "Components:"
    echo "  - Prometheus $PROMETHEUS_VERSION"
    echo "  - AlertManager $ALERTMANAGER_VERSION"
    echo "  - Grafana $GRAFANA_VERSION"
    echo ""

    read -p "Continue with installation? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi

    check_connection
    install_prometheus
    install_alertmanager
    install_grafana
    copy_configs
    create_services
    start_services
    verify_installation

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Installation Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "✅ Prometheus: http://$TARGET_HOST:9090"
    echo "✅ AlertManager: http://$TARGET_HOST:9093"
    echo "✅ Grafana: http://$TARGET_HOST:3000"
    echo ""
    echo "Default Grafana credentials:"
    echo "  Username: admin"
    echo "  Password: admin (change on first login)"
    echo ""
    echo "Next steps:"
    echo "  1. Access Grafana at http://$TARGET_HOST:3000"
    echo "  2. Import AutoBot dashboards from config/grafana/"
    echo "  3. Access dashboards in AutoBot UI: http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}/monitoring/dashboards"
    echo ""
}

main "$@"
