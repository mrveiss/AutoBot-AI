#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot SLM Bootstrap Script
# Deploys complete SLM stack (backend + frontend) to target node
#
# Usage: ./bootstrap-slm.sh -u USER -h HOST [OPTIONS]
#
# Author: mrveiss

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# #14041: capture what the operator actually exported for AUTOBOT_REDIS_HOST
# *before* sourcing the SSOT library below, which -- now that it exists --
# fills in a 127.0.0.1 default when the caller left it unset. Line ~406 below
# depends on being able to tell "the operator set it" from "the library
# defaulted it": #2224 made an unset AUTOBOT_REDIS_HOST fail loudly on purpose,
# because this script bakes the value into a REMOTE node's generated .env, and
# a loopback default there silently points a distributed Redis at the wrong
# host. Do not fold this into the library's own defaulting.
_OPERATOR_REDIS_HOST="${AUTOBOT_REDIS_HOST:-}"
# shellcheck source=/dev/null
source "$PROJECT_ROOT/autobot-infrastructure/shared/scripts/lib/ssot-config.sh" || {
    echo "FATAL: $PROJECT_ROOT/autobot-infrastructure/shared/scripts/lib/ssot-config.sh could not be sourced -- refusing to run on hardcoded config fallbacks (#14172)" >&2
    return 1 2>/dev/null || exit 1
}
INFRA_ROOT="${PROJECT_ROOT}/autobot-infrastructure"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${PROJECT_ROOT}/bootstrap-slm-${TIMESTAMP}.log"

# Defaults
TARGET_HOST="${AUTOBOT_SLM_HOST:-localhost}"
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
REMOTE_SHARED="${REMOTE_BASE}/autobot_shared"
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
  -h, --host HOST       Target host (default: ${AUTOBOT_SLM_HOST})
  -k, --key PATH        SSH private key path
  -p, --password        Prompt for SSH password
  --admin-password      Prompt for SLM admin password (default: random)
  --fresh               Force fresh install, ignore existing
  --no-cleanup          Don't cleanup on failure
  --help                Show this help message

Examples:
  $(basename "$0") -u root -h ${AUTOBOT_SLM_HOST}
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
    local cmd="ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
    if [[ -n "$SSH_KEY" ]]; then
        cmd="$cmd -i $SSH_KEY"
    fi
    echo "$cmd ${SSH_USER}@${TARGET_HOST}"
}

build_rsync_cmd() {
    local cmd="rsync -avz --delete"
    if [[ -n "$SSH_KEY" ]]; then
        cmd="$cmd -e 'ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new'"
    else
        cmd="$cmd -e 'ssh -o StrictHostKeyChecking=accept-new'"
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

    if [[ ! -d "${PROJECT_ROOT}/autobot_shared" ]]; then
        error "autobot_shared/ not found. Run from project root."
        exit 1
    fi
    success "Found autobot_shared/"

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
        -e "ssh -o StrictHostKeyChecking=accept-new ${SSH_KEY:+-i $SSH_KEY}" \
        "${PROJECT_ROOT}/autobot-slm-backend/" \
        "${SSH_USER}@${TARGET_HOST}:${REMOTE_BACKEND}/" \
        > /dev/null
    success "Backend deployed"

    info "Deploying autobot-slm-frontend..."
    rsync -avz --delete \
        -e "ssh -o StrictHostKeyChecking=accept-new ${SSH_KEY:+-i $SSH_KEY}" \
        "${PROJECT_ROOT}/autobot-slm-frontend/" \
        "${SSH_USER}@${TARGET_HOST}:${REMOTE_FRONTEND}/" \
        > /dev/null
    success "Frontend deployed"

    info "Deploying autobot_shared..."
    rsync -avz --delete \
        -e "ssh -o StrictHostKeyChecking=accept-new ${SSH_KEY:+-i $SSH_KEY}" \
        "${PROJECT_ROOT}/autobot_shared/" \
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

# Database (PostgreSQL -- Issue #786)
SLM_DATABASE_URL=postgresql+asyncpg://slm_app@127.0.0.1:5432/slm

# Redis (optional but recommended)
# AUTOBOT_REDIS_HOST must be set in the deployment environment (#2224)
REDIS_HOST=${_OPERATOR_REDIS_HOST:?AUTOBOT_REDIS_HOST is required -- set it in your environment}
REDIS_PORT=6379
REDIS_DB=0

# Security
SECRET_KEY=${SECRET_KEY}

# Admin bootstrap. main.py::_ensure_admin_user reads this at startup and
# creates (or re-syncs) the admin user through UserService, with bcrypt
# hashing. It is the only supported way to seed the SLM admin -- see the
# comment at the admin-verification step below.
SLM_ADMIN_PASSWORD=${ADMIN_PASSWORD}

# Logging
LOG_LEVEL=INFO
LOG_FILE=${REMOTE_LOGS}/slm-backend.log
ENVEOF"
    success "Configuration generated"

    # Create data directory and run migrations
    info "Setting up database..."
    remote_exec_sudo "mkdir -p ${REMOTE_BACKEND}/data"
    remote_exec_sudo "chown -R autobot:autobot ${REMOTE_BACKEND}"
    # Run migrations. The guard used to test for migrations/run.py, which does
    # not exist -- the entry point is migrations/runner.py -- so the branch never
    # fired and `|| true` would have swallowed the failure if it had.
    if remote_exec "test -f ${REMOTE_BACKEND}/migrations/runner.py"; then
        if ! remote_exec_sudo "cd ${REMOTE_BACKEND} && ${REMOTE_BACKEND}/venv/bin/python -m migrations.runner"; then
            error "Database migrations FAILED. The backend will not start against this schema."
            return 1
        fi
        success "Database setup complete"
    else
        error "migrations/runner.py not found at ${REMOTE_BACKEND} -- the deployed tree is incomplete."
        return 1
    fi

    # Admin user.
    #
    # This step used to run an inline python block importing `database.db` and
    # `models.user`. Neither module has ever existed in this tree: the DB layer
    # is `services/database.py` (async-only, so `next(get_db())` and
    # `db.query()` cannot work), the user model is
    # `user_management/models/user.py`, there is no `is_admin` column
    # (it is `is_platform_admin`), the NOT NULL `email` column was never
    # supplied, and it hashed the password with SHA-256 while the rest of the
    # system uses bcrypt via autobot_shared.auth.jwt_core.hash_password. The
    # whole block was wrapped in `2>/dev/null || warn`, so every one of those
    # failures surfaced as one soft warning and the bootstrap reported success
    # having created no admin at all.
    #
    # The supported path already exists and is the one Ansible uses:
    # main.py::_ensure_admin_user reads SLM_ADMIN_PASSWORD from the .env
    # written above and creates or re-syncs the admin through UserService with
    # bcrypt hashing. Adding SLM_ADMIN_PASSWORD to that .env is what actually
    # makes the admin appear; re-implementing the write here is what went
    # wrong the first time.
    #
    # This step deliberately does NOT claim to have verified it. The backend is
    # not running yet at this phase, and a check that cannot run must not print
    # a reassuring line (#14867). Tracked separately: a post-start admin
    # verification, and the missing PYTHONPATH that stops the bootstrapped
    # backend importing autobot_shared at all.
    info "Admin user: seeded by the backend on first start from SLM_ADMIN_PASSWORD"
    warn "NOT VERIFIED by this script - the backend has not started yet."
    warn "After start, confirm with: sudo journalctl -u autobot-slm-backend | grep -i admin"

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

    # #15650, #15689: the shell equivalent of
    # roles/_shared/tasks/build_publish_slm_frontend.yml -- build:slm (not a
    # plain `npm run build`, which bakes in the wrong API base, #9563/#9710/
    # #10435), a build failure that aborts loudly instead of warning and
    # continuing, and a build that lands in its own fresh directory, published
    # by an atomic symlink flip only after a non-empty index.html is proven
    # (#15430, #15462, #15557, #15610). One file, installed here and by
    # sync-frontend.sh, so the idiom is not copied a third time in shell.
    info "Installing build+publish helper..."
    cat "${INFRA_ROOT}/autobot-slm-frontend/templates/build-publish-slm-frontend.sh" | \
        remote_exec_sudo "cat > ${REMOTE_FRONTEND}/build-publish.sh"
    remote_exec_sudo "chmod +x ${REMOTE_FRONTEND}/build-publish.sh"

    info "Building and publishing frontend..."
    # No `|| warn ... continuing` here: a failed build must abort bootstrap,
    # not silently promote an empty/partial dist- directory. vite empties its
    # outDir before writing, so publishing a failed build serves 403 for
    # every /slm/ path (#15430, #15462) -- exactly what #15650 found this
    # script doing.
    remote_exec_sudo "cd ${REMOTE_FRONTEND} && ./build-publish.sh"
    success "Frontend built and published"

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
