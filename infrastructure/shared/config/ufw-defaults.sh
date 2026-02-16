#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# UFW Default Firewall Configuration for AutoBot Infrastructure
# Issue #887: UFW firewall blocks localhost connections - needs proper default rules
#
# USAGE:
#   sudo ./ufw-defaults.sh [reset|apply|status]
#
# COMMANDS:
#   reset   - Reset UFW to factory defaults, then apply AutoBot rules
#   apply   - Apply AutoBot firewall rules (preserves existing rules)
#   status  - Show current firewall status
#
# CRITICAL: This script configures UFW to allow:
#   1. SSH access (port 22) - CRITICAL to avoid lockout
#   2. Infrastructure subnet (172.16.168.0/24) - CRITICAL for VM communication
#   3. Service-specific ports - Backend, Frontend, Redis, etc.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Verify UFW is installed
check_ufw() {
    if ! command -v ufw &> /dev/null; then
        log_error "UFW is not installed. Install with: apt-get install ufw"
        exit 1
    fi
}

# Reset UFW to factory defaults
reset_ufw() {
    log_warning "Resetting UFW to factory defaults..."
    echo "y" | ufw --force reset
    log_success "UFW reset complete"
}

# Apply default policies
apply_policies() {
    log_info "Setting default policies..."
    ufw default deny incoming
    ufw default allow outgoing
    ufw default deny routed
    log_success "Default policies set (deny incoming, allow outgoing, deny routed)"
}

# Apply AutoBot firewall rules
apply_rules() {
    log_info "Applying AutoBot firewall rules..."

    # CRITICAL: Allow SSH first to prevent lockout
    log_info "  → Allowing SSH (port 22)"
    ufw allow 22/tcp comment 'SSH access'

    # CRITICAL: Allow infrastructure subnet (fixes Issue #887)
    log_info "  → Allowing infrastructure subnet (172.16.168.0/24)"
    ufw allow from 172.16.168.0/24 comment 'AutoBot infrastructure subnet'

    # Backend API (HTTPS)
    log_info "  → Allowing Backend API (port 8443)"
    ufw allow 8443/tcp comment 'AutoBot Backend API (HTTPS)'

    # Backend API (HTTP - legacy)
    log_info "  → Allowing Backend API legacy (port 8001)"
    ufw allow 8001/tcp comment 'AutoBot Backend API (HTTP)'

    # Redis Stack
    log_info "  → Allowing Redis Stack (port 6379)"
    ufw allow 6379/tcp comment 'Redis Stack'

    # PostgreSQL
    log_info "  → Allowing PostgreSQL (port 5432)"
    ufw allow 5432/tcp comment 'PostgreSQL'

    # Frontend (HTTPS)
    log_info "  → Allowing Frontend HTTPS (port 443)"
    ufw allow 443/tcp comment 'HTTPS Frontend'

    # Frontend (HTTP - redirects to HTTPS)
    log_info "  → Allowing Frontend HTTP (port 80)"
    ufw allow 80/tcp comment 'HTTP Frontend'

    # AI Stack
    log_info "  → Allowing AI Stack (port 8080)"
    ufw allow 8080/tcp comment 'AI Stack'

    # NPU Worker
    log_info "  → Allowing NPU Worker (port 8081)"
    ufw allow 8081/tcp comment 'NPU Worker'

    # Browser Worker
    log_info "  → Allowing Browser Worker (port 3000)"
    ufw allow 3000/tcp comment 'Browser Worker'

    # VNC/NoVNC
    log_info "  → Allowing VNC (port 5900)"
    ufw allow 5900/tcp comment 'VNC'
    log_info "  → Allowing NoVNC (port 6080)"
    ufw allow 6080/tcp comment 'NoVNC Web Console'

    # Monitoring - Prometheus
    log_info "  → Allowing Prometheus (port 9090)"
    ufw allow 9090/tcp comment 'Prometheus'

    # Monitoring - Grafana
    log_info "  → Allowing Grafana (port 3001)"
    ufw allow 3001/tcp comment 'Grafana'

    # Monitoring - Node Exporter
    log_info "  → Allowing Node Exporter (port 9100)"
    ufw allow 9100/tcp comment 'Node Exporter'

    # SLM Backend
    log_info "  → Allowing SLM Backend (port 8000)"
    ufw allow 8000/tcp comment 'SLM Backend'

    log_success "All firewall rules applied"
}

# Set logging level
set_logging() {
    log_info "Setting UFW logging to low..."
    ufw logging low
    log_success "UFW logging set to low"
}

# Enable firewall
enable_firewall() {
    log_info "Enabling UFW firewall..."
    echo "y" | ufw --force enable
    log_success "UFW firewall enabled"
}

# Show firewall status
show_status() {
    log_info "Current UFW firewall status:"
    echo ""
    ufw status verbose
    echo ""
    log_info "Recent UFW log entries (if any):"
    if [[ -f /var/log/ufw.log ]]; then
        tail -n 20 /var/log/ufw.log 2>/dev/null || log_warning "No recent UFW log entries"
    else
        log_warning "UFW log file not found at /var/log/ufw.log"
    fi
}

# Main execution
main() {
    local action="${1:-apply}"

    check_root
    check_ufw

    case "$action" in
        reset)
            log_warning "This will RESET all firewall rules to factory defaults!"
            read -p "Are you sure? (yes/no): " confirm
            if [[ "$confirm" != "yes" ]]; then
                log_info "Operation cancelled"
                exit 0
            fi
            reset_ufw
            apply_policies
            apply_rules
            set_logging
            enable_firewall
            show_status
            log_success "UFW reset and configured with AutoBot defaults"
            ;;
        apply)
            log_info "Applying AutoBot firewall rules (preserving existing rules)..."
            apply_policies
            apply_rules
            set_logging
            enable_firewall
            show_status
            log_success "AutoBot firewall rules applied"
            ;;
        status)
            show_status
            ;;
        *)
            log_error "Invalid action: $action"
            echo ""
            echo "Usage: $0 [reset|apply|status]"
            echo ""
            echo "Commands:"
            echo "  reset   - Reset UFW to factory defaults, then apply AutoBot rules"
            echo "  apply   - Apply AutoBot firewall rules (preserves existing rules)"
            echo "  status  - Show current firewall status"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
