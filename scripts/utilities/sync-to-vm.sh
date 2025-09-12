#!/bin/bash

# Universal sync script for AutoBot distributed architecture
# Uses certificate-based SSH authentication for all VMs
# Usage: ./sync-to-vm.sh <vm-name> <local-path> <remote-path> [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_header() {
    echo -e "${BLUE}[SYNC]${NC} $1"
}

# AutoBot VM configuration
declare -A VMS=(
    ["frontend"]="172.16.168.21"
    ["npu-worker"]="172.16.168.22" 
    ["redis"]="172.16.168.23"
    ["ai-stack"]="172.16.168.24"
    ["browser"]="172.16.168.25"
)

SSH_KEY="$HOME/.ssh/autobot_key"
REMOTE_USER="autobot"

# Show usage
show_usage() {
    echo "Usage: $0 <vm-name> <local-path> <remote-path> [options]"
    echo
    echo "VM Names:"
    for vm_name in "${!VMS[@]}"; do
        echo "  $vm_name (${VMS[$vm_name]})"
    done
    echo
    echo "Examples:"
    echo "  $0 frontend autobot-vue/src/components/ /home/autobot/autobot-vue/src/components/"
    echo "  $0 frontend autobot-vue/src/components/App.vue /home/autobot/autobot-vue/src/components/"
    echo "  $0 all scripts/setup.sh /home/autobot/scripts/"
    echo
    echo "Special VM Names:"
    echo "  all - Sync to all VMs"
    echo
    echo "Options:"
    echo "  --restart-service <service> - Restart service after sync"
    echo "  --test-connection          - Test SSH connection only"
}

# Validate parameters
if [ $# -lt 1 ]; then
    log_error "Missing parameters"
    show_usage
    exit 1
fi

VM_NAME="$1"
LOCAL_PATH="$2"
REMOTE_PATH="$3"
RESTART_SERVICE=""
TEST_ONLY=false

# Parse options
shift 3 2>/dev/null || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --restart-service)
            RESTART_SERVICE="$2"
            shift 2
            ;;
        --test-connection)
            TEST_ONLY=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    log_error "SSH key not found at $SSH_KEY"
    log_info "Run ./scripts/utilities/setup-ssh-keys.sh first"
    exit 1
fi

# Function to test SSH connection
test_connection() {
    local vm_name=$1
    local vm_ip=$2
    
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
        "$REMOTE_USER@$vm_ip" "echo 'Connection successful'" > /dev/null 2>&1; then
        log_info "$vm_name ($vm_ip): Connection successful ✓"
        return 0
    else
        log_error "$vm_name ($vm_ip): Connection failed ✗"
        return 1
    fi
}

# Function to sync to a single VM
sync_to_vm() {
    local vm_name=$1
    local vm_ip=$2
    local local_path=$3
    local remote_path=$4
    
    log_header "Syncing to $vm_name ($vm_ip)"
    
    # Test connection first
    if ! test_connection "$vm_name" "$vm_ip"; then
        return 1
    fi
    
    # Return if test-only mode
    if [ "$TEST_ONLY" = true ]; then
        return 0
    fi
    
    # Validate local path exists
    if [ ! -e "$local_path" ]; then
        log_error "Local path does not exist: $local_path"
        return 1
    fi
    
    # Ensure remote directory exists
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$REMOTE_USER@$vm_ip" \
        "mkdir -p $(dirname "$remote_path")" 2>/dev/null
    
    # Sync files
    if [ -d "$local_path" ]; then
        log_info "Syncing directory: $local_path -> $vm_name:$remote_path"
        scp -i "$SSH_KEY" -o StrictHostKeyChecking=no -r \
            "$local_path" "$REMOTE_USER@$vm_ip:$(dirname "$remote_path")/"
    else
        log_info "Syncing file: $local_path -> $vm_name:$remote_path"
        scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
            "$local_path" "$REMOTE_USER@$vm_ip:$remote_path"
    fi
    
    # Restart service if requested
    if [ -n "$RESTART_SERVICE" ]; then
        log_info "Restarting service: $RESTART_SERVICE"
        ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$REMOTE_USER@$vm_ip" \
            "sudo systemctl restart $RESTART_SERVICE" 2>/dev/null || \
        ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$REMOTE_USER@$vm_ip" \
            "pkill -f '$RESTART_SERVICE' && sleep 2" 2>/dev/null || true
    fi
    
    log_info "$vm_name: Sync completed successfully ✓"
    return 0
}

# Main execution
if [ "$VM_NAME" = "all" ]; then
    log_header "Syncing to all VMs"
    successful=0
    failed=0
    
    for vm_name in "${!VMS[@]}"; do
        vm_ip="${VMS[$vm_name]}"
        if sync_to_vm "$vm_name" "$vm_ip" "$LOCAL_PATH" "$REMOTE_PATH"; then
            ((successful++))
        else
            ((failed++))
        fi
        echo
    done
    
    log_info "Summary: $successful successful, $failed failed"
    [ $failed -eq 0 ] && exit 0 || exit 1
    
elif [ -n "${VMS[$VM_NAME]}" ]; then
    vm_ip="${VMS[$VM_NAME]}"
    sync_to_vm "$VM_NAME" "$vm_ip" "$LOCAL_PATH" "$REMOTE_PATH"
    
else
    log_error "Unknown VM name: $VM_NAME"
    echo
    show_usage
    exit 1
fi