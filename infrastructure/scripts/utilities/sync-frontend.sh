#!/bin/bash

# Frontend sync script using SSH key authentication
# Usage: ./sync-frontend.sh [component|all]

set -e

# =============================================================================
# SSOT Configuration - Load from .env file (Single Source of Truth)
# Issue: #604 - SSOT Phase 4 Cleanup
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Configuration - Using SSOT env vars with fallbacks
REMOTE_HOST="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
REMOTE_USER="autobot"
SSH_KEY="$HOME/.ssh/autobot_key"
LOCAL_SRC="$PROJECT_ROOT/autobot-vue/src"
REMOTE_DEST="/home/autobot/autobot-vue/src"
FRONTEND_PORT="${AUTOBOT_FRONTEND_PORT:-5173}"
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    log_error "SSH key not found at $SSH_KEY"
    exit 1
fi

# Test SSH connection
if ! ssh -T -i "$SSH_KEY" -o ConnectTimeout=5 "$REMOTE_USER@$REMOTE_HOST" "echo 'Connection test successful'" > /dev/null 2>&1; then
    log_error "Cannot connect to $REMOTE_HOST using SSH key"
    exit 1
fi

log_info "SSH connection verified ✓"

# Step 1: Stop Vite dev server first (to clear in-memory cache)
log_info "Stopping Vite dev server..."
timeout 10 ssh -i "$SSH_KEY" "$REMOTE_USER@$REMOTE_HOST" \
    "pkill -9 -f 'vite.*--host.*5173' 2>/dev/null || true; pkill -9 -f 'npm.*dev' 2>/dev/null || true" || echo "  (timeout or already stopped)"
sleep 1
log_info "Vite dev server stopped ✓"

# Step 2: Clean caches and temp files on remote (while Vite is stopped)
log_info "Cleaning Vite caches and temp files on remote..."
timeout 15 ssh -i "$SSH_KEY" "$REMOTE_USER@$REMOTE_HOST" \
    "cd /home/autobot/autobot-vue && rm -rf .vite node_modules/.cache node_modules/.vite dist .vite-temp && echo 'Caches cleared'" || log_warn "Cache cleanup timed out"
log_info "Remote caches cleaned ✓"

# Step 3: Sync specific component or all
SYNC_TARGET="${1:-all}"

case "$SYNC_TARGET" in
    "component"|"components")
        log_info "Syncing components directory..."
        rsync -avz --delete -e "ssh -i $SSH_KEY" \
            "$LOCAL_SRC/components/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DEST/components/"
        ;;
    "all")
        log_info "Syncing entire src directory (with deletion of removed files)..."
        rsync -avz --delete -e "ssh -i $SSH_KEY" \
            --exclude 'node_modules' \
            --exclude '.DS_Store' \
            --exclude '*.log' \
            "$LOCAL_SRC/" "$REMOTE_USER@$REMOTE_HOST:/home/autobot/autobot-vue/src/"
        ;;
    *)
        log_info "Syncing specific file/directory: $SYNC_TARGET"
        if [ -f "$LOCAL_SRC/$SYNC_TARGET" ] || [ -d "$LOCAL_SRC/$SYNC_TARGET" ]; then
            if [ -d "$LOCAL_SRC/$SYNC_TARGET" ]; then
                rsync -avz --delete -e "ssh -i $SSH_KEY" \
                    "$LOCAL_SRC/$SYNC_TARGET/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DEST/$SYNC_TARGET/"
            else
                rsync -avz -e "ssh -i $SSH_KEY" \
                    "$LOCAL_SRC/$SYNC_TARGET" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DEST/$SYNC_TARGET"
            fi
        else
            log_error "File or directory not found: $LOCAL_SRC/$SYNC_TARGET"
            exit 1
        fi
        ;;
esac

log_info "Sync completed successfully! ✓"

# Step 4: Start Vite dev server with clean cache and fresh files
log_info "Starting Vite dev server..."
timeout 10 ssh -i "$SSH_KEY" "$REMOTE_USER@$REMOTE_HOST" \
    "cd /home/autobot/autobot-vue && VITE_BACKEND_HOST=$BACKEND_HOST VITE_BACKEND_PORT=$BACKEND_PORT nohup npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT > /tmp/vite.log 2>&1 < /dev/null &" || log_warn "Vite startup command may have timed out"
sleep 3
log_info "Vite dev server started ✓"
log_info "Frontend sync complete - all caches cleared, files synced, server restarted ✓"
