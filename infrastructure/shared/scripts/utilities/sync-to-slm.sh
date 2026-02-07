#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# SLM Full Sync Script
# Syncs both slm-server (backend) and slm-admin (frontend) to the SLM management node
# Usage: ./sync-to-slm.sh [--build|--restart|--all]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Configuration
REMOTE_HOST="172.16.168.19"
REMOTE_USER="autobot"
SLM_SERVER_LOCAL="$PROJECT_ROOT/slm-server"
SLM_ADMIN_LOCAL="$PROJECT_ROOT/slm-admin"
# Remote paths match the install location on 172.16.168.19
SLM_SERVER_REMOTE="/home/autobot/AutoBot/slm-server"
SLM_ADMIN_REMOTE="/home/autobot/AutoBot/slm-admin"

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

echo ""
echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}       SLM Full Deployment Sync          ${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""
echo "Target: $REMOTE_USER@$REMOTE_HOST"
echo "Components: slm-server, slm-admin"
echo ""

# Check if remote is reachable
log_step "Checking connectivity to $REMOTE_HOST..."
if ! ping -c 1 -W 2 "$REMOTE_HOST" > /dev/null 2>&1; then
    log_error "Cannot reach $REMOTE_HOST"
    exit 1
fi
log_info "Host reachable"

# Sync slm-server (Python backend)
echo ""
log_step "Syncing slm-server (backend)..."
rsync -avz --delete \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude '*.log' \
    --exclude 'venv/' \
    --exclude '.venv/' \
    --exclude '*.db' \
    --exclude '.env.local' \
    "$SLM_SERVER_LOCAL/" \
    "$REMOTE_USER@$REMOTE_HOST:$SLM_SERVER_REMOTE/"
log_info "Backend synced"

# Sync slm-admin (Vue frontend)
echo ""
log_step "Syncing slm-admin (frontend)..."
rsync -avz --delete \
    --exclude 'node_modules/' \
    --exclude 'dist/' \
    --exclude '.git/' \
    --exclude '*.log' \
    "$SLM_ADMIN_LOCAL/" \
    "$REMOTE_USER@$REMOTE_HOST:$SLM_ADMIN_REMOTE/"
log_info "Frontend synced"

# Handle options
case "$1" in
    --build)
        echo ""
        log_step "Installing frontend dependencies..."
        ssh "$REMOTE_USER@$REMOTE_HOST" "cd $SLM_ADMIN_REMOTE && npm install"

        echo ""
        log_step "Building frontend for production..."
        ssh "$REMOTE_USER@$REMOTE_HOST" "cd $SLM_ADMIN_REMOTE && npm run build"
        log_info "Frontend built"
        ;;

    --restart)
        echo ""
        log_step "Restarting SLM services..."
        ssh "$REMOTE_USER@$REMOTE_HOST" "sudo systemctl restart slm-backend slm-admin-ui" || {
            log_warn "Could not restart via systemctl, trying manual restart..."
        }
        log_info "Services restarted"
        ;;

    --all)
        echo ""
        log_step "Installing frontend dependencies..."
        ssh "$REMOTE_USER@$REMOTE_HOST" "cd $SLM_ADMIN_REMOTE && npm install"

        echo ""
        log_step "Building frontend for production..."
        ssh "$REMOTE_USER@$REMOTE_HOST" "cd $SLM_ADMIN_REMOTE && npm run build"

        echo ""
        log_step "Restarting SLM services..."
        ssh "$REMOTE_USER@$REMOTE_HOST" "sudo systemctl restart slm-backend slm-admin-ui 2>/dev/null" || {
            log_warn "Systemctl restart not available - services may need manual restart"
        }
        log_info "Full deployment complete"
        ;;

    *)
        echo ""
        log_info "Files synced. Use options for additional actions:"
        echo ""
        echo "  --build    Install deps and build frontend"
        echo "  --restart  Restart SLM services"
        echo "  --all      Build and restart everything"
        ;;
esac

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}           Sync Complete!                ${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo "Manual commands if needed:"
echo ""
echo "  Frontend dev server:"
echo "    ssh $REMOTE_USER@$REMOTE_HOST 'cd $SLM_ADMIN_REMOTE && npm run dev'"
echo ""
echo "  Frontend build:"
echo "    ssh $REMOTE_USER@$REMOTE_HOST 'cd $SLM_ADMIN_REMOTE && npm run build'"
echo ""
echo "  Restart backend:"
echo "    ssh $REMOTE_USER@$REMOTE_HOST 'sudo systemctl restart slm-backend'"
echo ""
echo "  View logs:"
echo "    ssh $REMOTE_USER@$REMOTE_HOST 'journalctl -u slm-backend -f'"
echo ""
