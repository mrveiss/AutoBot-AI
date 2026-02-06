#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Jaeger Setup Script for AutoBot Distributed Tracing (Issue #57)
# Installs and configures Jaeger on the Redis VM (172.16.168.23)
# Does NOT use Docker - native binary installation

set -e

# Configuration
JAEGER_VERSION="${JAEGER_VERSION:-1.53.0}"
JAEGER_USER="${JAEGER_USER:-autobot}"
JAEGER_INSTALL_DIR="/opt/jaeger"
JAEGER_DATA_DIR="/var/lib/jaeger"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on correct VM
check_vm() {
    local current_ip=$(hostname -I | awk '{print $1}')
    if [[ "$current_ip" != "172.16.168.23" ]]; then
        log_warn "This script is designed for the Redis VM (172.16.168.23)"
        log_warn "Current IP: $current_ip"
        read -p "Continue anyway? (y/N): " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            log_error "Aborted"
            exit 1
        fi
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check for wget or curl
    if ! command -v wget &> /dev/null && ! command -v curl &> /dev/null; then
        log_error "Neither wget nor curl found. Please install one of them."
        exit 1
    fi

    # Check for tar
    if ! command -v tar &> /dev/null; then
        log_error "tar not found. Please install tar."
        exit 1
    fi

    # Check for systemctl
    if ! command -v systemctl &> /dev/null; then
        log_error "systemctl not found. This script requires systemd."
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Download Jaeger
download_jaeger() {
    log_info "Downloading Jaeger v${JAEGER_VERSION}..."

    local download_url="https://github.com/jaegertracing/jaeger/releases/download/v${JAEGER_VERSION}/jaeger-${JAEGER_VERSION}-linux-amd64.tar.gz"
    local temp_dir=$(mktemp -d)
    local archive="${temp_dir}/jaeger.tar.gz"

    if command -v wget &> /dev/null; then
        wget -q --show-progress -O "$archive" "$download_url"
    else
        curl -L -o "$archive" "$download_url"
    fi

    if [[ ! -f "$archive" ]]; then
        log_error "Failed to download Jaeger"
        exit 1
    fi

    log_info "Extracting Jaeger..."
    tar -xzf "$archive" -C "$temp_dir"

    # Move to installation directory
    sudo rm -rf "$JAEGER_INSTALL_DIR"
    sudo mv "${temp_dir}/jaeger-${JAEGER_VERSION}-linux-amd64" "$JAEGER_INSTALL_DIR"

    # Cleanup
    rm -rf "$temp_dir"

    log_success "Jaeger downloaded and extracted to $JAEGER_INSTALL_DIR"
}

# Create data directory
create_data_dir() {
    log_info "Creating data directory..."

    sudo mkdir -p "$JAEGER_DATA_DIR"
    sudo chown -R "$JAEGER_USER:$JAEGER_USER" "$JAEGER_DATA_DIR"

    log_success "Data directory created: $JAEGER_DATA_DIR"
}

# Create systemd service
create_systemd_service() {
    log_info "Creating systemd service..."

    sudo tee /etc/systemd/system/jaeger.service > /dev/null << EOF
[Unit]
Description=Jaeger All-in-One - AutoBot Distributed Tracing
Documentation=https://www.jaegertracing.io/docs/
After=network.target

[Service]
Type=simple
User=${JAEGER_USER}
Group=${JAEGER_USER}

# Jaeger All-in-One with OTLP enabled
ExecStart=${JAEGER_INSTALL_DIR}/jaeger-all-in-one \\
    --collector.otlp.enabled=true \\
    --collector.otlp.grpc.host-port=0.0.0.0:4317 \\
    --collector.otlp.http.host-port=0.0.0.0:4318 \\
    --query.http-server.host-port=0.0.0.0:16686 \\
    --query.grpc-server.host-port=0.0.0.0:16685 \\
    --memory.max-traces=100000 \\
    --log-level=info

# Restart configuration
Restart=always
RestartSec=5
TimeoutStartSec=30
TimeoutStopSec=30

# Resource limits
LimitNOFILE=65535
LimitNPROC=4096

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${JAEGER_DATA_DIR}

# Environment
Environment="SPAN_STORAGE_TYPE=memory"

[Install]
WantedBy=multi-user.target
EOF

    log_success "Systemd service created"
}

# Enable and start service
start_service() {
    log_info "Starting Jaeger service..."

    sudo systemctl daemon-reload
    sudo systemctl enable jaeger
    sudo systemctl start jaeger

    # Wait for startup
    sleep 3

    if sudo systemctl is-active --quiet jaeger; then
        log_success "Jaeger service started successfully"
    else
        log_error "Failed to start Jaeger service"
        sudo systemctl status jaeger
        exit 1
    fi
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."

    # Check service status
    if ! sudo systemctl is-active --quiet jaeger; then
        log_error "Jaeger service is not running"
        exit 1
    fi

    # Wait for ports to be ready
    sleep 2

    # Check Jaeger UI
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:16686" | grep -q "200"; then
        log_success "Jaeger UI is accessible at http://172.16.168.23:16686"
    else
        log_warn "Jaeger UI not responding yet (may still be starting)"
    fi

    # Check OTLP HTTP endpoint
    local otlp_response=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:4318" 2>/dev/null || echo "000")
    if [[ "$otlp_response" != "000" ]]; then
        log_success "OTLP HTTP endpoint listening on port 4318"
    fi

    log_info "OTLP gRPC endpoint listening on port 4317"
}

# Configure firewall (if ufw is installed)
configure_firewall() {
    if command -v ufw &> /dev/null; then
        log_info "Configuring firewall rules..."

        # Allow from AutoBot network (172.16.168.0/24)
        sudo ufw allow from 172.16.168.0/24 to any port 4317 proto tcp comment "Jaeger OTLP gRPC"
        sudo ufw allow from 172.16.168.0/24 to any port 4318 proto tcp comment "Jaeger OTLP HTTP"
        sudo ufw allow from 172.16.168.0/24 to any port 16686 proto tcp comment "Jaeger UI"
        sudo ufw allow from 172.16.168.0/24 to any port 16685 proto tcp comment "Jaeger gRPC"

        log_success "Firewall rules configured"
    else
        log_info "ufw not found, skipping firewall configuration"
    fi
}

# Print summary
print_summary() {
    echo ""
    echo "=============================================="
    echo "       Jaeger Installation Complete"
    echo "=============================================="
    echo ""
    echo "Version:     ${JAEGER_VERSION}"
    echo "Install Dir: ${JAEGER_INSTALL_DIR}"
    echo ""
    echo "Endpoints:"
    echo "  - Jaeger UI:   http://172.16.168.23:16686"
    echo "  - OTLP gRPC:   http://172.16.168.23:4317"
    echo "  - OTLP HTTP:   http://172.16.168.23:4318"
    echo ""
    echo "Service Management:"
    echo "  - Status:  sudo systemctl status jaeger"
    echo "  - Start:   sudo systemctl start jaeger"
    echo "  - Stop:    sudo systemctl stop jaeger"
    echo "  - Restart: sudo systemctl restart jaeger"
    echo "  - Logs:    sudo journalctl -u jaeger -f"
    echo ""
    echo "Configuration for AutoBot backend:"
    echo "  export AUTOBOT_JAEGER_ENDPOINT=http://172.16.168.23:4317"
    echo ""
    echo "=============================================="
}

# Uninstall function
uninstall() {
    log_info "Uninstalling Jaeger..."

    # Stop and disable service
    sudo systemctl stop jaeger 2>/dev/null || true
    sudo systemctl disable jaeger 2>/dev/null || true

    # Remove files
    sudo rm -f /etc/systemd/system/jaeger.service
    sudo rm -rf "$JAEGER_INSTALL_DIR"
    sudo rm -rf "$JAEGER_DATA_DIR"

    sudo systemctl daemon-reload

    log_success "Jaeger uninstalled successfully"
}

# Main
main() {
    echo "=============================================="
    echo "  AutoBot Jaeger Setup (Issue #57)"
    echo "  Distributed Tracing Infrastructure"
    echo "=============================================="
    echo ""

    case "${1:-install}" in
        install)
            check_vm
            check_prerequisites
            download_jaeger
            create_data_dir
            create_systemd_service
            start_service
            verify_installation
            configure_firewall
            print_summary
            ;;
        uninstall)
            uninstall
            ;;
        status)
            sudo systemctl status jaeger
            ;;
        *)
            echo "Usage: $0 {install|uninstall|status}"
            exit 1
            ;;
    esac
}

main "$@"
