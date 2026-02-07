#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# sync-all-vms.sh - Sync code from main machine to all VMs
# Main machine is the single source of truth for all code
#
# Usage: ./sync-all-vms.sh [--dry-run] [--vm <vm-name>]

set -e

# =============================================================================
# SSOT Configuration - Issue #694
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/ssot-config.sh" 2>/dev/null || source "$SCRIPT_DIR/lib/ssot-config.sh" 2>/dev/null || {
    # Fallback if lib not found
    PROJECT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
    [ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }
}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_header() { echo -e "${BLUE}========================================${NC}"; echo -e "${BLUE}$1${NC}"; echo -e "${BLUE}========================================${NC}"; }

# VM Configuration - Using SSOT env vars
declare -A VMS=(
    ["frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${AUTOBOT_SSH_USER:-autobot}"
DRY_RUN=false
SPECIFIC_VM=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --vm) SPECIFIC_VM="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--vm <vm-name>]"
            echo "  --dry-run    Show what would be synced without actually syncing"
            echo "  --vm <name>  Only sync to specific VM (frontend, npu-worker, redis, ai-stack, browser)"
            exit 0
            ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# Sync function
sync_to_vm() {
    local vm_name=$1
    local vm_ip=$2
    local local_path=$3
    local remote_path=$4
    local exclude_pattern=$5

    if [ ! -e "$PROJECT_ROOT/$local_path" ]; then
        log_warn "Skipping $local_path (does not exist)"
        return 0
    fi

    local rsync_opts="-avz --progress"
    if [ -n "$exclude_pattern" ]; then
        rsync_opts="$rsync_opts --exclude='$exclude_pattern'"
    fi

    if [ "$DRY_RUN" = true ]; then
        rsync_opts="$rsync_opts --dry-run"
    fi

    log_info "Syncing $local_path -> $vm_name:$remote_path"

    # Ensure remote directory exists
    ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
        "$SSH_USER@$vm_ip" "mkdir -p $remote_path" 2>/dev/null || true

    # Sync
    rsync $rsync_opts \
        -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
        "$PROJECT_ROOT/$local_path" "$SSH_USER@$vm_ip:$remote_path/" 2>/dev/null
}

# Test VM connectivity
test_vm() {
    local vm_name=$1
    local vm_ip=$2

    if ssh -i "$SSH_KEY" -o ConnectTimeout=3 -o StrictHostKeyChecking=no \
        "$SSH_USER@$vm_ip" "echo ok" > /dev/null 2>&1; then
        echo -e "  ${GREEN}${NC} $vm_name ($vm_ip)"
        return 0
    else
        echo -e "  ${RED}${NC} $vm_name ($vm_ip) - unreachable"
        return 1
    fi
}

# Main sync logic
log_header "AutoBot VM Code Sync"
echo "Main machine is the single source of truth"
echo ""

# Test connectivity
log_info "Testing VM connectivity..."
for vm_name in "${!VMS[@]}"; do
    if [ -n "$SPECIFIC_VM" ] && [ "$vm_name" != "$SPECIFIC_VM" ]; then
        continue
    fi
    test_vm "$vm_name" "${VMS[$vm_name]}" || true
done
echo ""

# Sync Frontend VM
if [ -z "$SPECIFIC_VM" ] || [ "$SPECIFIC_VM" = "frontend" ]; then
    log_header "Syncing Frontend VM (${VMS[frontend]})"
    if test_vm "frontend" "${VMS[frontend]}" 2>/dev/null; then
        sync_to_vm "frontend" "${VMS[frontend]}" "autobot-vue/" "/home/autobot/autobot-vue" "node_modules"
    fi
fi

# Sync NPU Worker VM
if [ -z "$SPECIFIC_VM" ] || [ "$SPECIFIC_VM" = "npu-worker" ]; then
    log_header "Syncing NPU Worker VM (${VMS[npu-worker]})"
    if test_vm "npu-worker" "${VMS[npu-worker]}" 2>/dev/null; then
        # Sync NPU-specific files
        sync_to_vm "npu-worker" "${VMS[npu-worker]}" "src/npu_integration.py" "/home/autobot/autobot-npu-worker"
        sync_to_vm "npu-worker" "${VMS[npu-worker]}" "src/npu_semantic_search.py" "/home/autobot/autobot-npu-worker"
        sync_to_vm "npu-worker" "${VMS[npu-worker]}" "src/constants/" "/home/autobot/autobot-npu-worker/src"
        sync_to_vm "npu-worker" "${VMS[npu-worker]}" "src/utils/" "/home/autobot/autobot-npu-worker/src"
    fi
fi

# Sync AI Stack VM
if [ -z "$SPECIFIC_VM" ] || [ "$SPECIFIC_VM" = "ai-stack" ]; then
    log_header "Syncing AI Stack VM (${VMS[ai-stack]})"
    if test_vm "ai-stack" "${VMS[ai-stack]}" 2>/dev/null; then
        sync_to_vm "ai-stack" "${VMS[ai-stack]}" "src/agents/" "/home/autobot/autobot/src"
        sync_to_vm "ai-stack" "${VMS[ai-stack]}" "src/knowledge_base.py" "/home/autobot/autobot/src"
        sync_to_vm "ai-stack" "${VMS[ai-stack]}" "src/constants/" "/home/autobot/autobot/src"
    fi
fi

# Sync Browser VM
if [ -z "$SPECIFIC_VM" ] || [ "$SPECIFIC_VM" = "browser" ]; then
    log_header "Syncing Browser VM (${VMS[browser]})"
    if test_vm "browser" "${VMS[browser]}" 2>/dev/null; then
        sync_to_vm "browser" "${VMS[browser]}" "scripts/browser/" "/home/autobot/browser"
    fi
fi

# Redis VM typically doesn't need code sync (data only)
if [ -z "$SPECIFIC_VM" ] || [ "$SPECIFIC_VM" = "redis" ]; then
    log_header "Redis VM (${VMS[redis]})"
    log_info "Redis VM is data-only, no code sync needed"
fi

echo ""
log_header "Sync Complete"
if [ "$DRY_RUN" = true ]; then
    log_warn "This was a dry run - no files were actually synced"
fi
