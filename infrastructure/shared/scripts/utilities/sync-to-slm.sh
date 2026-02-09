#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# SLM Management Plane Sync & Deploy Script (Issue #814)
#
# Phase 1: Rsync code to the SLM server (172.16.168.19)
# Phase 2: Run Ansible playbook to configure services (certs, nginx, build, systemd)
#
# The SLM then handles distributing code to fleet nodes via its code-sync agents.
#
# Usage: ./sync-to-slm.sh [OPTIONS]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# Load SSOT config if available
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Configuration
REMOTE_HOST="${AUTOBOT_SLM_HOST:-172.16.168.19}"
REMOTE_USER="autobot"
SSH_KEY="$HOME/.ssh/autobot_key"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

# Local paths
SLM_BACKEND_LOCAL="$PROJECT_ROOT/autobot-slm-backend"
SLM_FRONTEND_LOCAL="$PROJECT_ROOT/autobot-slm-frontend"
SHARED_LIB_LOCAL="$PROJECT_ROOT/autobot-shared"

# Ansible paths
ANSIBLE_DIR="$SLM_BACKEND_LOCAL/ansible"
ANSIBLE_INVENTORY="$ANSIBLE_DIR/inventory/slm-nodes.yml"
ANSIBLE_PLAYBOOK="$ANSIBLE_DIR/playbooks/deploy-slm-manager.yml"

# Remote paths (match systemd service and nginx config)
REMOTE_BASE="/opt/autobot"
SLM_BACKEND_REMOTE="$REMOTE_BASE/autobot-slm-backend"
SLM_FRONTEND_REMOTE="$REMOTE_BASE/autobot-slm-frontend"
SHARED_LIB_REMOTE="$REMOTE_BASE/autobot-shared"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

rsync_cmd() {
    if [ -f "$SSH_KEY" ]; then
        rsync -avz --delete -e "ssh -i $SSH_KEY $SSH_OPTS" "$@"
    else
        rsync -avz --delete -e "ssh $SSH_OPTS" "$@"
    fi
}

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Syncs code to SLM server, then runs Ansible to configure services."
    echo ""
    echo "Options:"
    echo "  (none)       Sync files only (no Ansible)"
    echo "  --deploy     Sync + run full Ansible playbook (recommended)"
    echo "  --tags TAGS  Sync + run Ansible with specific tags"
    echo "               Tags: packages, tls, backend, frontend, nginx, service"
    echo "  --sync-only  Sync files only (same as no option)"
    echo "  --help       Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 --deploy                    # Full deploy (sync + ansible)"
    echo "  $0 --tags frontend,nginx       # Rebuild frontend + reload nginx"
    echo "  $0 --tags tls                  # Regenerate TLS certs only"
    echo "  $0 --tags backend,service      # Update backend + restart service"
}

# Parse options
ACTION="sync-only"
ANSIBLE_TAGS=""
case "${1:-}" in
    --help|-h) show_usage; exit 0 ;;
    --deploy) ACTION="deploy" ;;
    --tags)
        ACTION="deploy"
        ANSIBLE_TAGS="${2:-}"
        if [ -z "$ANSIBLE_TAGS" ]; then
            log_error "Missing tags argument. Usage: $0 --tags frontend,nginx"
            exit 1
        fi
        ;;
    --sync-only|"") ACTION="sync-only" ;;
    *)
        log_error "Unknown option: $1"
        show_usage
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}     SLM Management Plane Deployment        ${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "Target:     $REMOTE_USER@$REMOTE_HOST"
echo "Components: autobot-slm-backend, autobot-slm-frontend, autobot-shared"
echo "Remote:     $REMOTE_BASE/"
echo "Action:     $ACTION"
[ -n "$ANSIBLE_TAGS" ] && echo "Tags:       $ANSIBLE_TAGS"
echo ""

# ===== Phase 1: Rsync code =====

log_step "Checking connectivity to $REMOTE_HOST..."
if ! ping -c 1 -W 2 "$REMOTE_HOST" > /dev/null 2>&1; then
    log_error "Cannot reach $REMOTE_HOST"
    exit 1
fi
log_info "Host reachable"

# Sync autobot-shared (backend dependency)
echo ""
log_step "Syncing autobot-shared..."
rsync_cmd \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    "$SHARED_LIB_LOCAL/" \
    "$REMOTE_USER@$REMOTE_HOST:$SHARED_LIB_REMOTE/"
log_info "Shared lib synced"

# Sync SLM backend (exclude ansible dir - it stays local for running playbooks)
echo ""
log_step "Syncing autobot-slm-backend..."
rsync_cmd \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude '*.log' \
    --exclude 'venv/' \
    --exclude '.venv/' \
    --exclude '*.db' \
    --exclude '.env.local' \
    --exclude 'ansible/' \
    "$SLM_BACKEND_LOCAL/" \
    "$REMOTE_USER@$REMOTE_HOST:$SLM_BACKEND_REMOTE/"
log_info "Backend synced"

# Sync SLM frontend (source, not dist - Ansible will build)
echo ""
log_step "Syncing autobot-slm-frontend..."
rsync_cmd \
    --exclude 'node_modules/' \
    --exclude 'dist/' \
    --exclude '.git/' \
    --exclude '*.log' \
    "$SLM_FRONTEND_LOCAL/" \
    "$REMOTE_USER@$REMOTE_HOST:$SLM_FRONTEND_REMOTE/"
log_info "Frontend synced"

# ===== Phase 2: Run Ansible =====

if [ "$ACTION" = "deploy" ]; then
    echo ""
    echo -e "${BLUE}--------------------------------------------${NC}"
    echo -e "${BLUE}     Running Ansible Playbook               ${NC}"
    echo -e "${BLUE}--------------------------------------------${NC}"
    echo ""

    # Verify ansible-playbook is available locally
    if ! command -v ansible-playbook &> /dev/null; then
        log_error "ansible-playbook not found. Install: sudo apt install ansible"
        exit 1
    fi

    # Verify inventory and playbook exist
    if [ ! -f "$ANSIBLE_INVENTORY" ]; then
        log_error "Inventory not found: $ANSIBLE_INVENTORY"
        exit 1
    fi
    if [ ! -f "$ANSIBLE_PLAYBOOK" ]; then
        log_error "Playbook not found: $ANSIBLE_PLAYBOOK"
        exit 1
    fi

    # Build ansible command (run from ansible/ dir so ansible.cfg is picked up)
    ANSIBLE_CMD=(
        ansible-playbook
        -i "inventory/slm-nodes.yml"
        "playbooks/deploy-slm-manager.yml"
    )

    # Add SSH key if available
    if [ -f "$SSH_KEY" ]; then
        ANSIBLE_CMD+=(--private-key "$SSH_KEY")
    fi

    # Add tags if specified
    if [ -n "$ANSIBLE_TAGS" ]; then
        ANSIBLE_CMD+=(--tags "$ANSIBLE_TAGS")
        log_step "Running playbook with tags: $ANSIBLE_TAGS"
    else
        log_step "Running full playbook..."
    fi

    # Execute from ansible dir so ansible.cfg roles_path works
    (cd "$ANSIBLE_DIR" && "${ANSIBLE_CMD[@]}")

    echo ""
    log_info "Ansible playbook completed"
fi

# ===== Summary =====

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}           Sync Complete!                   ${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

if [ "$ACTION" = "sync-only" ]; then
    echo "Files synced. To configure services, run:"
    echo ""
    echo "  $0 --deploy                    # Full deploy"
    echo "  $0 --tags frontend,nginx       # Build frontend + nginx"
    echo "  $0 --tags tls                  # Generate TLS certs"
    echo "  $0 --tags backend,service      # Backend + restart"
else
    echo "Deployment complete. Useful commands:"
    echo ""
    echo "  View backend logs:"
    echo "    ssh $REMOTE_USER@$REMOTE_HOST 'journalctl -u autobot-slm-backend -f'"
    echo ""
    echo "  View nginx logs:"
    echo "    ssh $REMOTE_USER@$REMOTE_HOST 'tail -f /opt/autobot/logs/nginx-error.log'"
fi
echo ""
