#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# SLM Management Plane Sync Script
# Syncs SLM backend, frontend, and shared lib to the SLM management node (172.16.168.19)
# The SLM then handles distributing code to fleet nodes via its code-sync agents.
#
# Usage: ./sync-to-slm.sh [--build|--restart|--nginx|--all]

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
NGINX_CONF_LOCAL="$PROJECT_ROOT/infrastructure/autobot-slm-frontend/templates/autobot-slm.conf"

# Remote paths (match systemd service and nginx config)
REMOTE_BASE="/opt/autobot"
SLM_BACKEND_REMOTE="$REMOTE_BASE/autobot-slm-backend"
SLM_FRONTEND_REMOTE="$REMOTE_BASE/autobot-slm-frontend"
SHARED_LIB_REMOTE="$REMOTE_BASE/autobot-shared"
NGINX_REMOTE="/etc/nginx/sites-enabled/autobot-slm.conf"

# Service names
BACKEND_SERVICE="autobot-slm-backend"

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

# Build SSH command with key if available
ssh_cmd() {
    if [ -f "$SSH_KEY" ]; then
        ssh -i "$SSH_KEY" $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "$@"
    else
        ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "$@"
    fi
}

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
    echo "Syncs SLM management plane code to $REMOTE_HOST"
    echo "Components: autobot-slm-backend, autobot-slm-frontend, autobot-shared"
    echo ""
    echo "Options:"
    echo "  (none)      Sync files only"
    echo "  --build     Sync + npm install + npm run build"
    echo "  --restart   Sync + restart backend service"
    echo "  --nginx     Sync + deploy nginx config + reload nginx"
    echo "  --all       Sync + build + nginx + restart (full deploy)"
    echo "  --help      Show this help"
}

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}     SLM Management Plane Deployment        ${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "Target:     $REMOTE_USER@$REMOTE_HOST"
echo "Components: autobot-slm-backend, autobot-slm-frontend, autobot-shared"
echo "Remote:     $REMOTE_BASE/"
echo ""

# Parse option
ACTION="${1:-sync}"
case "$ACTION" in
    --help|-h) show_usage; exit 0 ;;
    --build|--restart|--nginx|--all) ;;
    *) ACTION="sync" ;;
esac

# Check connectivity
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

# Sync SLM backend
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

# Sync SLM frontend (source, not dist)
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

# Handle options
case "$ACTION" in
    --build)
        echo ""
        log_step "Installing frontend dependencies..."
        ssh_cmd "cd $SLM_FRONTEND_REMOTE && npm install"

        echo ""
        log_step "Building frontend for production..."
        ssh_cmd "cd $SLM_FRONTEND_REMOTE && npm run build"
        log_info "Frontend built (dist at $SLM_FRONTEND_REMOTE/dist)"
        ;;

    --restart)
        echo ""
        log_step "Restarting $BACKEND_SERVICE..."
        ssh_cmd "sudo systemctl restart $BACKEND_SERVICE" || {
            log_warn "Could not restart via systemctl"
        }
        log_info "Backend restarted"
        ;;

    --nginx)
        echo ""
        log_step "Deploying nginx config..."
        if [ -f "$SSH_KEY" ]; then
            scp -i "$SSH_KEY" $SSH_OPTS "$NGINX_CONF_LOCAL" \
                "$REMOTE_USER@$REMOTE_HOST:/tmp/autobot-slm.conf"
        else
            scp $SSH_OPTS "$NGINX_CONF_LOCAL" \
                "$REMOTE_USER@$REMOTE_HOST:/tmp/autobot-slm.conf"
        fi
        ssh_cmd "sudo cp /tmp/autobot-slm.conf $NGINX_REMOTE && sudo nginx -t && sudo nginx -s reload"
        log_info "Nginx config deployed and reloaded"
        ;;

    --all)
        echo ""
        log_step "Installing frontend dependencies..."
        ssh_cmd "cd $SLM_FRONTEND_REMOTE && npm install"

        echo ""
        log_step "Building frontend for production..."
        ssh_cmd "cd $SLM_FRONTEND_REMOTE && npm run build"
        log_info "Frontend built"

        echo ""
        log_step "Deploying nginx config..."
        if [ -f "$SSH_KEY" ]; then
            scp -i "$SSH_KEY" $SSH_OPTS "$NGINX_CONF_LOCAL" \
                "$REMOTE_USER@$REMOTE_HOST:/tmp/autobot-slm.conf"
        else
            scp $SSH_OPTS "$NGINX_CONF_LOCAL" \
                "$REMOTE_USER@$REMOTE_HOST:/tmp/autobot-slm.conf"
        fi
        ssh_cmd "sudo cp /tmp/autobot-slm.conf $NGINX_REMOTE && sudo nginx -t && sudo nginx -s reload"
        log_info "Nginx config deployed"

        echo ""
        log_step "Restarting $BACKEND_SERVICE..."
        ssh_cmd "sudo systemctl restart $BACKEND_SERVICE" || {
            log_warn "Systemctl restart not available"
        }
        log_info "Full deployment complete"
        ;;

    *)
        echo ""
        log_info "Files synced. Use options for additional actions:"
        echo ""
        echo "  --build    Install deps and build frontend"
        echo "  --restart  Restart SLM backend service"
        echo "  --nginx    Deploy nginx config and reload"
        echo "  --all      Build + nginx + restart (full deploy)"
        ;;
esac

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}           Sync Complete!                   ${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Manual commands if needed:"
echo ""
echo "  Build frontend:"
echo "    ssh $REMOTE_USER@$REMOTE_HOST 'cd $SLM_FRONTEND_REMOTE && npm run build'"
echo ""
echo "  Restart backend:"
echo "    ssh $REMOTE_USER@$REMOTE_HOST 'sudo systemctl restart $BACKEND_SERVICE'"
echo ""
echo "  Reload nginx:"
echo "    ssh $REMOTE_USER@$REMOTE_HOST 'sudo nginx -s reload'"
echo ""
echo "  View logs:"
echo "    ssh $REMOTE_USER@$REMOTE_HOST 'journalctl -u $BACKEND_SERVICE -f'"
echo ""
