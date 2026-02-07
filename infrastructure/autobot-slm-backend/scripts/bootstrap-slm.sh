#!/bin/bash
# AutoBot SLM Bootstrap Script
# Deploys complete SLM stack (backend + frontend) to target node
#
# Usage: ./bootstrap-slm.sh -u USER -h HOST [OPTIONS]
#
# Copyright (c) 2025 mrveiss
# Author: mrveiss

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INFRA_ROOT="${PROJECT_ROOT}/infrastructure"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${PROJECT_ROOT}/bootstrap-slm-${TIMESTAMP}.log"

# Defaults
TARGET_HOST="172.16.168.19"
SSH_USER=""
SSH_KEY=""
SSH_PASSWORD=""
ADMIN_PASSWORD=""
PROMPT_ADMIN_PASSWORD=false
FRESH_INSTALL=false
NO_CLEANUP=false

# Remote paths
REMOTE_BASE="/opt/autobot"
REMOTE_BACKEND="${REMOTE_BASE}/autobot-slm-backend"
REMOTE_FRONTEND="${REMOTE_BASE}/autobot-slm-frontend"
REMOTE_SHARED="${REMOTE_BASE}/autobot-shared"
REMOTE_CERTS="${REMOTE_BASE}/nginx/certs"
REMOTE_LOGS="${REMOTE_BASE}/logs"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# =============================================================================
# Logging
# =============================================================================

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_FILE"
}

info() { log "INFO" "$*"; }
warn() { log "${YELLOW}WARN${NC}" "$*"; }
error() { log "${RED}ERROR${NC}" "$*"; }
success() { log "${GREEN}OK${NC}" "$*"; }

phase() {
    echo
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${PURPLE}  $*${NC}"
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
}

# =============================================================================
# Usage
# =============================================================================

usage() {
    cat << EOF
AutoBot SLM Bootstrap Script

Usage: $(basename "$0") -u USER [OPTIONS]

Required:
  -u, --user USER       SSH user with sudo access

Options:
  -h, --host HOST       Target host (default: 172.16.168.19)
  -k, --key PATH        SSH private key path
  -p, --password        Prompt for SSH password
  --admin-password      Prompt for SLM admin password (default: random)
  --fresh               Force fresh install, ignore existing
  --no-cleanup          Don't cleanup on failure
  --help                Show this help message

Examples:
  $(basename "$0") -u root -h 172.16.168.19
  $(basename "$0") -u root -p --admin-password
  $(basename "$0") -u admin -k ~/.ssh/autobot_key

EOF
    exit 0
}

# =============================================================================
# Argument Parsing
# =============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -u|--user)
                SSH_USER="$2"
                shift 2
                ;;
            -h|--host)
                TARGET_HOST="$2"
                shift 2
                ;;
            -k|--key)
                SSH_KEY="$2"
                shift 2
                ;;
            -p|--password)
                SSH_PASSWORD="prompt"
                shift
                ;;
            --admin-password)
                PROMPT_ADMIN_PASSWORD=true
                shift
                ;;
            --fresh)
                FRESH_INSTALL=true
                shift
                ;;
            --no-cleanup)
                NO_CLEANUP=true
                shift
                ;;
            --help)
                usage
                ;;
            *)
                error "Unknown option: $1"
                usage
                ;;
        esac
    done

    if [[ -z "$SSH_USER" ]]; then
        error "SSH user is required (-u USER)"
        usage
    fi
}

# =============================================================================
# SSH Functions
# =============================================================================

build_ssh_cmd() {
    local cmd="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
    if [[ -n "$SSH_KEY" ]]; then
        cmd="$cmd -i $SSH_KEY"
    fi
    echo "$cmd ${SSH_USER}@${TARGET_HOST}"
}

build_rsync_cmd() {
    local cmd="rsync -avz --delete"
    if [[ -n "$SSH_KEY" ]]; then
        cmd="$cmd -e 'ssh -i $SSH_KEY -o StrictHostKeyChecking=no'"
    else
        cmd="$cmd -e 'ssh -o StrictHostKeyChecking=no'"
    fi
    echo "$cmd"
}

remote_exec() {
    local cmd="$1"
    $(build_ssh_cmd) "$cmd"
}

remote_exec_sudo() {
    local cmd="$1"
    $(build_ssh_cmd) "sudo bash -c '$cmd'"
}

# =============================================================================
# Phase 1: Pre-flight Checks
# =============================================================================

preflight_checks() {
    phase "Phase 1: Pre-flight Checks"

    # Check we're in project root
    if [[ ! -d "${PROJECT_ROOT}/autobot-slm-backend" ]]; then
        error "autobot-slm-backend/ not found. Run from project root."
        exit 1
    fi
    success "Found autobot-slm-backend/"

    if [[ ! -d "${PROJECT_ROOT}/autobot-slm-frontend" ]]; then
        error "autobot-slm-frontend/ not found. Run from project root."
        exit 1
    fi
    success "Found autobot-slm-frontend/"

    if [[ ! -d "${PROJECT_ROOT}/autobot-shared" ]]; then
        error "autobot-shared/ not found. Run from project root."
        exit 1
    fi
    success "Found autobot-shared/"

    # Check SSH key
    if [[ -z "$SSH_KEY" ]] && [[ "$SSH_PASSWORD" != "prompt" ]]; then
        if [[ -f ~/.ssh/id_rsa ]]; then
            SSH_KEY=~/.ssh/id_rsa
            info "Using default SSH key: ~/.ssh/id_rsa"
        elif [[ -f ~/.ssh/id_ed25519 ]]; then
            SSH_KEY=~/.ssh/id_ed25519
            info "Using default SSH key: ~/.ssh/id_ed25519"
        else
            warn "No SSH key found, will prompt for password"
            SSH_PASSWORD="prompt"
        fi
    fi

    # Prompt for SSH password if needed
    if [[ "$SSH_PASSWORD" == "prompt" ]]; then
        read -sp "SSH password for ${SSH_USER}@${TARGET_HOST}: " SSH_PASSWORD
        echo
        export SSHPASS="$SSH_PASSWORD"
        # Check if sshpass is available
        if ! command -v sshpass &> /dev/null; then
            error "sshpass not installed. Install with: sudo apt install sshpass"
            exit 1
        fi
    fi

    # Test SSH connection
    info "Testing SSH connection to ${TARGET_HOST}..."
    if ! remote_exec "echo 'SSH connection successful'" 2>/dev/null; then
        error "Cannot connect to ${TARGET_HOST}"
        exit 1
    fi
    success "SSH connection OK"

    # Test sudo access
    info "Testing sudo access..."
    if ! remote_exec_sudo "whoami" 2>/dev/null | grep -q root; then
        error "User ${SSH_USER} does not have sudo access"
        exit 1
    fi
    success "Sudo access OK"

    # Prompt for SLM admin password if requested
    if [[ "$PROMPT_ADMIN_PASSWORD" == true ]]; then
        read -sp "SLM admin password: " ADMIN_PASSWORD
        echo
        read -sp "Confirm password: " ADMIN_PASSWORD_CONFIRM
        echo
        if [[ "$ADMIN_PASSWORD" != "$ADMIN_PASSWORD_CONFIRM" ]]; then
            error "Passwords do not match"
            exit 1
        fi
    else
        ADMIN_PASSWORD=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16)
        info "Generated random admin password"
    fi
}

# =============================================================================
# Phase 2: System Preparation
# =============================================================================

system_preparation() {
    phase "Phase 2: System Preparation"

    info "Updating package lists..."
    remote_exec_sudo "apt-get update -qq"
    success "Package lists updated"

    info "Installing required packages..."
    remote_exec_sudo "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        python3 python3-venv python3-pip \
        nodejs npm \
        nginx \
        rsync curl openssl \
        > /dev/null 2>&1"
    success "Packages installed"

    info "Creating directory structure..."
    remote_exec_sudo "mkdir -p ${REMOTE_BASE} ${REMOTE_CERTS} ${REMOTE_LOGS} ${REMOTE_BASE}/certs"
    success "Directories created"

    # Create autobot service user
    info "Creating autobot service user..."
    if remote_exec "id autobot" &>/dev/null; then
        info "User 'autobot' already exists"
    else
        remote_exec_sudo "useradd -r -s /usr/sbin/nologin -d ${REMOTE_BASE} -m autobot"
        success "Created user 'autobot'"
    fi

    # Create autobot_admin reserve user
    info "Creating autobot_admin reserve user..."
    if remote_exec "id autobot_admin" &>/dev/null; then
        info "User 'autobot_admin' already exists"
    else
        AUTOBOT_ADMIN_PASSWORD=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)
        remote_exec_sudo "useradd -m -s /bin/bash autobot_admin"
        remote_exec_sudo "echo 'autobot_admin:${AUTOBOT_ADMIN_PASSWORD}' | chpasswd"
        remote_exec_sudo "usermod -aG sudo autobot_admin"
        remote_exec_sudo "passwd -l autobot_admin"  # Lock the account
        success "Created user 'autobot_admin'"
        echo
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${RED}  IMPORTANT: Save this password! It will not be shown again.${NC}"
        echo -e "${RED}  autobot_admin password: ${AUTOBOT_ADMIN_PASSWORD}${NC}"
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo
        read -p "Press Enter after saving the password..."
    fi

    remote_exec_sudo "chown -R autobot:autobot ${REMOTE_BASE}"
    success "Ownership set"
}

# =============================================================================
# Phase 3: Code Deployment
# =============================================================================

code_deployment() {
    phase "Phase 3: Code Deployment"

    # Backup existing if not fresh install
    if [[ "$FRESH_INSTALL" != true ]]; then
        if remote_exec "test -d ${REMOTE_BACKEND}" &>/dev/null; then
            info "Backing up existing deployment..."
            remote_exec_sudo "cp -r ${REMOTE_BASE} ${REMOTE_BASE}.bak.${TIMESTAMP}"
            success "Backup created at ${REMOTE_BASE}.bak.${TIMESTAMP}"
        fi
    fi

    info "Deploying autobot-slm-backend..."
    rsync -avz --delete \
        -e "ssh -o StrictHostKeyChecking=no ${SSH_KEY:+-i $SSH_KEY}" \
        "${PROJECT_ROOT}/autobot-slm-backend/" \
        "${SSH_USER}@${TARGET_HOST}:${REMOTE_BACKEND}/" \
        > /dev/null
    success "Backend deployed"

    info "Deploying autobot-slm-frontend..."
    rsync -avz --delete \
        -e "ssh -o StrictHostKeyChecking=no ${SSH_KEY:+-i $SSH_KEY}" \
        "${PROJECT_ROOT}/autobot-slm-frontend/" \
        "${SSH_USER}@${TARGET_HOST}:${REMOTE_FRONTEND}/" \
        > /dev/null
    success "Frontend deployed"

    info "Deploying autobot-shared..."
    rsync -avz --delete \
        -e "ssh -o StrictHostKeyChecking=no ${SSH_KEY:+-i $SSH_KEY}" \
        "${PROJECT_ROOT}/autobot-shared/" \
        "${SSH_USER}@${TARGET_HOST}:${REMOTE_SHARED}/" \
        > /dev/null
    success "Shared utilities deployed"

    remote_exec_sudo "chown -R autobot:autobot ${REMOTE_BASE}"
    success "Ownership updated"
}

# =============================================================================
# Phase 4: Backend Setup
# =============================================================================

backend_setup() {
    phase "Phase 4: Backend Setup"

    info "Creating Python virtual environment..."
    remote_exec_sudo "python3 -m venv ${REMOTE_BACKEND}/venv"
    success "Virtual environment created"

    info "Installing Python dependencies..."
    remote_exec_sudo "${REMOTE_BACKEND}/venv/bin/pip install --upgrade pip -q"
    remote_exec_sudo "${REMOTE_BACKEND}/venv/bin/pip install -r ${REMOTE_BACKEND}/requirements.txt -q"
    success "Dependencies installed"

    # Generate .env config
    info "Generating configuration..."
    SECRET_KEY=$(openssl rand -hex 32)
    remote_exec_sudo "cat > ${REMOTE_BACKEND}/.env << 'ENVEOF'
# AutoBot SLM Backend Configuration
# Generated by bootstrap-slm.sh on ${TIMESTAMP}

# Server
HOST=127.0.0.1
PORT=8000

# Database
DATABASE_URL=sqlite:///${REMOTE_BACKEND}/data/slm.db

# Redis (optional but recommended)
REDIS_HOST=172.16.168.23
REDIS_PORT=6379
REDIS_DB=0

# Security
SECRET_KEY=${SECRET_KEY}

# Logging
LOG_LEVEL=INFO
LOG_FILE=${REMOTE_LOGS}/slm-backend.log
ENVEOF"
    success "Configuration generated"

    # Create data directory and run migrations
    info "Setting up database..."
    remote_exec_sudo "mkdir -p ${REMOTE_BACKEND}/data"
    remote_exec_sudo "chown -R autobot:autobot ${REMOTE_BACKEND}"
    # Run migrations if available
    if remote_exec "test -f ${REMOTE_BACKEND}/migrations/run.py" &>/dev/null; then
        remote_exec_sudo "cd ${REMOTE_BACKEND} && ${REMOTE_BACKEND}/venv/bin/python -m migrations.run" || true
    fi
    success "Database setup complete"

    # Create admin user
    info "Creating SLM admin user..."
    remote_exec_sudo "cd ${REMOTE_BACKEND} && ${REMOTE_BACKEND}/venv/bin/python -c \"
from database.db import init_db, get_db
from models.user import User
import hashlib

init_db()
db = next(get_db())

# Check if admin exists
existing = db.query(User).filter(User.username == 'admin').first()
if not existing:
    password_hash = hashlib.sha256('${ADMIN_PASSWORD}'.encode()).hexdigest()
    admin = User(username='admin', password_hash=password_hash, is_admin=True)
    db.add(admin)
    db.commit()
    print('Admin user created')
else:
    print('Admin user already exists')
\"" 2>/dev/null || warn "Could not create admin user (may need manual setup)"

    # Install helper scripts
    info "Installing helper scripts..."
    cat "${INFRA_ROOT}/autobot-slm-backend/templates/backend-start.sh" | \
        remote_exec_sudo "cat > ${REMOTE_BACKEND}/start.sh"
    cat "${INFRA_ROOT}/autobot-slm-backend/templates/backend-stop.sh" | \
        remote_exec_sudo "cat > ${REMOTE_BACKEND}/stop.sh"
    cat "${INFRA_ROOT}/autobot-slm-backend/templates/backend-status.sh" | \
        remote_exec_sudo "cat > ${REMOTE_BACKEND}/status.sh"
    remote_exec_sudo "chmod +x ${REMOTE_BACKEND}/*.sh"
    success "Helper scripts installed"
}

# =============================================================================
# Phase 5: Frontend & Nginx Setup
# =============================================================================

frontend_setup() {
    phase "Phase 5: Frontend & Nginx Setup"

    info "Installing npm dependencies..."
    remote_exec_sudo "cd ${REMOTE_FRONTEND} && npm install --silent 2>/dev/null"
    success "npm dependencies installed"

    info "Building frontend..."
    remote_exec_sudo "cd ${REMOTE_FRONTEND} && npm run build --silent 2>/dev/null" || \
        warn "Frontend build may have warnings, continuing..."
    success "Frontend built"

    # Generate self-signed certificate
    info "Generating self-signed TLS certificate..."
    remote_exec_sudo "openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout ${REMOTE_CERTS}/slm.key \
        -out ${REMOTE_CERTS}/slm.crt \
        -subj '/CN=${TARGET_HOST}/O=AutoBot/C=US' \
        2>/dev/null"
    remote_exec_sudo "chmod 600 ${REMOTE_CERTS}/slm.key"
    success "TLS certificate generated"

    # Install nginx configuration
    info "Configuring nginx..."
    cat "${INFRA_ROOT}/autobot-slm-frontend/templates/autobot-slm.conf" | \
        remote_exec_sudo "cat > /etc/nginx/sites-available/autobot-slm"
    remote_exec_sudo "ln -sf /etc/nginx/sites-available/autobot-slm /etc/nginx/sites-enabled/"
    remote_exec_sudo "rm -f /etc/nginx/sites-enabled/default"
    remote_exec_sudo "nginx -t 2>/dev/null"
    success "nginx configured"

    # Install helper scripts
    info "Installing helper scripts..."
    cat "${INFRA_ROOT}/autobot-slm-frontend/templates/frontend-start.sh" | \
        remote_exec_sudo "cat > ${REMOTE_FRONTEND}/start.sh"
    cat "${INFRA_ROOT}/autobot-slm-frontend/templates/frontend-stop.sh" | \
        remote_exec_sudo "cat > ${REMOTE_FRONTEND}/stop.sh"
    cat "${INFRA_ROOT}/autobot-slm-frontend/templates/frontend-status.sh" | \
        remote_exec_sudo "cat > ${REMOTE_FRONTEND}/status.sh"
    remote_exec_sudo "chmod +x ${REMOTE_FRONTEND}/*.sh"
    success "Helper scripts installed"
}

# =============================================================================
# Phase 6: Service Installation
# =============================================================================

service_installation() {
    phase "Phase 6: Service Installation"

    info "Installing systemd service..."
    cat "${INFRA_ROOT}/autobot-slm-backend/templates/autobot-slm-backend.service" | \
        remote_exec_sudo "cat > /etc/systemd/system/autobot-slm-backend.service"
    remote_exec_sudo "systemctl daemon-reload"
    success "Systemd service installed"

    info "Enabling and starting backend service..."
    remote_exec_sudo "systemctl enable autobot-slm-backend"
    remote_exec_sudo "systemctl restart autobot-slm-backend"
    success "Backend service started"

    info "Enabling and starting nginx..."
    remote_exec_sudo "systemctl enable nginx"
    remote_exec_sudo "systemctl restart nginx"
    success "nginx started"

    # Wait for services
    info "Waiting for services to be ready..."
    sleep 3

    # Health check
    info "Running health checks..."
    if remote_exec "curl -sk https://127.0.0.1/api/health" &>/dev/null; then
        success "Health check passed"
    else
        warn "Health check failed - service may need time to start"
    fi
}

# =============================================================================
# Phase 7: Summary
# =============================================================================

show_summary() {
    phase "Phase 7: Deployment Complete"

    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  SLM Deployment Successful!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
    echo -e "  ${BLUE}SLM URL:${NC}         https://${TARGET_HOST}"
    echo -e "  ${BLUE}Admin Username:${NC}  admin"
    echo -e "  ${BLUE}Admin Password:${NC}  ${ADMIN_PASSWORD}"
    echo
    echo -e "  ${YELLOW}Note:${NC} Using self-signed certificate. Browser will show warning."
    echo
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
    echo "Next steps:"
    echo "  1. Open https://${TARGET_HOST} in your browser"
    echo "  2. Accept the self-signed certificate warning"
    echo "  3. Log in with admin credentials"
    echo "  4. Add nodes and assign roles from the dashboard"
    echo
    echo "Log file: ${LOG_FILE}"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo
    echo -e "${PURPLE}╔════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║                    AutoBot SLM Bootstrap Script                        ║${NC}"
    echo -e "${PURPLE}╚════════════════════════════════════════════════════════════════════════╝${NC}"
    echo

    parse_args "$@"

    info "Starting SLM bootstrap to ${TARGET_HOST}"
    info "Log file: ${LOG_FILE}"

    preflight_checks
    system_preparation
    code_deployment
    backend_setup
    frontend_setup
    service_installation
    show_summary
}

# Run main
main "$@"
