#!/bin/bash

# Frontend sync script using SSH key authentication
# Usage: ./sync-frontend.sh [component|all]

set -e

REMOTE_HOST="172.16.168.21"
REMOTE_USER="autobot"
SSH_KEY="$HOME/.ssh/autobot_key"
LOCAL_SRC="/home/kali/Desktop/AutoBot/autobot-vue/src"
REMOTE_DEST="/home/autobot/autobot-vue/src"

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

# Sync specific component or all
SYNC_TARGET="${1:-all}"

case "$SYNC_TARGET" in
    "component"|"components")
        log_info "Syncing components directory..."
        scp -i "$SSH_KEY" -r \
            "$LOCAL_SRC/components/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DEST/"
        ;;
    "all")
        log_info "Syncing entire src directory..."
        scp -i "$SSH_KEY" -r \
            "$LOCAL_SRC/" "$REMOTE_USER@$REMOTE_HOST:/home/autobot/autobot-vue/"
        ;;
    *)
        log_info "Syncing specific file/directory: $SYNC_TARGET"
        if [ -f "$LOCAL_SRC/$SYNC_TARGET" ] || [ -d "$LOCAL_SRC/$SYNC_TARGET" ]; then
            if [ -d "$LOCAL_SRC/$SYNC_TARGET" ]; then
                scp -i "$SSH_KEY" -r \
                    "$LOCAL_SRC/$SYNC_TARGET" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DEST/"
            else
                scp -i "$SSH_KEY" \
                    "$LOCAL_SRC/$SYNC_TARGET" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DEST/$SYNC_TARGET"
            fi
        else
            log_error "File or directory not found: $LOCAL_SRC/$SYNC_TARGET"
            exit 1
        fi
        ;;
esac

log_info "Sync completed successfully! ✓"

# Optional: Restart Vite dev server if needed
if [ "$2" == "--restart" ]; then
    log_info "Restarting Vite dev server..."
    ssh -T -i "$SSH_KEY" "$REMOTE_USER@$REMOTE_HOST" \
        "pkill -f 'vite.*--host.*5173' || true; sleep 2; cd /home/autobot/autobot-vue && VITE_BACKEND_HOST=${AUTOBOT_BACKEND_HOST:-172.16.168.20} VITE_BACKEND_PORT=${AUTOBOT_BACKEND_PORT:-8001} npm run dev -- --host 0.0.0.0 --port 5173 > /dev/null 2>&1 &"
    log_info "Vite dev server restarted ✓"
fi