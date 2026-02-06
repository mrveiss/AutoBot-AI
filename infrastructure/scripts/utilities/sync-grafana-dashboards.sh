#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Grafana Dashboard Sync Script (Issue #697)
# Syncs local Grafana dashboards to the Redis VM where Grafana runs.
# Can be run standalone or called from run_autobot.sh startup.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[GRAFANA]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# =============================================================================
# SSOT Configuration - Load from .env file
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Configuration
TARGET_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
TARGET_USER="autobot"
SSH_KEY="$HOME/.ssh/autobot_key"
LOCAL_DASHBOARDS="$PROJECT_ROOT/config/grafana/dashboards"
REMOTE_DASHBOARDS="/var/lib/grafana/dashboards"

# Options
QUIET=false
CHECK_ONLY=false

show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Syncs Grafana dashboards from local config to the Redis VM.

Options:
  --check       Check sync status without syncing
  --quiet       Minimal output (for startup scripts)
  --help        Show this help

Examples:
  $0                    # Full sync with status output
  $0 --check            # Check if dashboards are in sync
  $0 --quiet            # Quiet sync for startup scripts
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --check) CHECK_ONLY=true; shift ;;
        --quiet) QUIET=true; shift ;;
        --help) show_usage; exit 0 ;;
        *) error "Unknown option: $1"; show_usage; exit 1 ;;
    esac
done

# Check prerequisites
check_prerequisites() {
    if [ ! -f "$SSH_KEY" ]; then
        error "SSH key not found: $SSH_KEY"
        error "Run ./scripts/utilities/setup-ssh-keys.sh first"
        return 1
    fi

    if [ ! -d "$LOCAL_DASHBOARDS" ]; then
        error "Local dashboards directory not found: $LOCAL_DASHBOARDS"
        return 1
    fi

    # Test connection
    if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o BatchMode=yes \
        "$TARGET_USER@$TARGET_HOST" "echo 'ok'" > /dev/null 2>&1; then
        [ "$QUIET" = false ] && warning "Cannot connect to Grafana host ($TARGET_HOST)"
        return 1
    fi

    return 0
}

# Get dashboard count and checksums
get_local_status() {
    local count=$(find "$LOCAL_DASHBOARDS" -name "*.json" 2>/dev/null | wc -l)
    local checksum=$(find "$LOCAL_DASHBOARDS" -name "*.json" -exec md5sum {} \; 2>/dev/null | sort | md5sum | cut -d' ' -f1)
    echo "$count:$checksum"
}

get_remote_status() {
    ssh -i "$SSH_KEY" -o BatchMode=yes "$TARGET_USER@$TARGET_HOST" \
        "find $REMOTE_DASHBOARDS -name '*.json' 2>/dev/null | wc -l; \
         find $REMOTE_DASHBOARDS -name '*.json' -exec md5sum {} \; 2>/dev/null | sort | md5sum | cut -d' ' -f1" 2>/dev/null || echo "0:none"
}

# Check sync status
check_sync_status() {
    local local_status=$(get_local_status)
    local local_count=$(echo "$local_status" | cut -d: -f1)
    local local_checksum=$(echo "$local_status" | cut -d: -f2)

    local remote_info=$(ssh -i "$SSH_KEY" -o BatchMode=yes "$TARGET_USER@$TARGET_HOST" \
        "count=\$(find $REMOTE_DASHBOARDS -name '*.json' 2>/dev/null | wc -l); \
         checksum=\$(find $REMOTE_DASHBOARDS -name '*.json' -exec md5sum {} \; 2>/dev/null | sort | md5sum | cut -d' ' -f1); \
         echo \"\$count:\$checksum\"" 2>/dev/null) || remote_info="0:none"

    local remote_count=$(echo "$remote_info" | cut -d: -f1)
    local remote_checksum=$(echo "$remote_info" | cut -d: -f2)

    if [ "$local_count" = "$remote_count" ] && [ "$local_checksum" = "$remote_checksum" ]; then
        [ "$QUIET" = false ] && success "Dashboards in sync ($local_count dashboards)"
        return 0
    else
        [ "$QUIET" = false ] && warning "Dashboards out of sync (local: $local_count, remote: $remote_count)"
        return 1
    fi
}

# Sync dashboards
sync_dashboards() {
    [ "$QUIET" = false ] && log "Syncing dashboards to $TARGET_HOST..."

    # Ensure remote directory exists
    ssh -i "$SSH_KEY" "$TARGET_USER@$TARGET_HOST" \
        "sudo mkdir -p $REMOTE_DASHBOARDS && sudo chown $TARGET_USER:$TARGET_USER $REMOTE_DASHBOARDS" 2>/dev/null

    # Count local dashboards
    local count=$(find "$LOCAL_DASHBOARDS" -name "*.json" | wc -l)

    if [ "$count" -eq 0 ]; then
        warning "No dashboards found in $LOCAL_DASHBOARDS"
        return 0
    fi

    # Sync using rsync
    if command -v rsync >/dev/null 2>&1; then
        rsync -avz --delete \
            -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
            "$LOCAL_DASHBOARDS/" "$TARGET_USER@$TARGET_HOST:$REMOTE_DASHBOARDS/" \
            ${QUIET:+--quiet}
    else
        # Fallback to scp
        scp -i "$SSH_KEY" -o StrictHostKeyChecking=no -r \
            "$LOCAL_DASHBOARDS/"*.json "$TARGET_USER@$TARGET_HOST:$REMOTE_DASHBOARDS/" \
            ${QUIET:+2>/dev/null}
    fi

    [ "$QUIET" = false ] && success "Synced $count dashboards to Grafana"
    return 0
}

# Main
main() {
    if ! check_prerequisites; then
        [ "$QUIET" = false ] && warning "Skipping Grafana dashboard sync (prerequisites not met)"
        exit 0  # Don't fail startup
    fi

    if [ "$CHECK_ONLY" = true ]; then
        check_sync_status
        exit $?
    fi

    # Check if sync needed
    if check_sync_status 2>/dev/null; then
        [ "$QUIET" = false ] && log "Dashboards already in sync, skipping"
        exit 0
    fi

    # Sync dashboards
    sync_dashboards
}

main "$@"
