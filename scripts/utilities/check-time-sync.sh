#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# AutoBot Time Synchronization Check Utility
# Checks time synchronization status across all VMs in the distributed infrastructure

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

# Configuration
ANSIBLE_DIR="$PROJECT_ROOT/ansible"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"

# VM Configuration - Using SSOT env vars
declare -A VMS=(
    ["frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

# Expected timezone
EXPECTED_TIMEZONE="Europe/Riga"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
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
    echo -e "${BLUE}[HEADER]${NC} $1"
}

# Check if SSH key exists
check_ssh_key() {
    if [ ! -f "$SSH_KEY" ]; then
        log_error "SSH key not found at $SSH_KEY"
        log_info "Run setup-ssh-keys.sh first to configure SSH access"
        exit 1
    fi
}

# Check VM connectivity
check_vm_connectivity() {
    local vm_name="$1"
    local vm_ip="$2"

    if ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o BatchMode=yes \
           "autobot@$vm_ip" "echo 'Connection test successful'" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Get time status from VM
get_vm_time_status() {
    local vm_ip="$1"

    ssh -i "$SSH_KEY" -o BatchMode=yes \
        "autobot@$vm_ip" "timedatectl status 2>/dev/null || echo 'timedatectl not available'"
}

# Get current time from VM
get_vm_current_time() {
    local vm_ip="$1"

    ssh -i "$SSH_KEY" -o BatchMode=yes \
        "autobot@$vm_ip" "date '+%Y-%m-%d %H:%M:%S %Z (UTC%z)' 2>/dev/null || echo 'date command failed'"
}

# Check if VM time is synchronized
check_vm_sync_status() {
    local vm_ip="$1"

    ssh -i "$SSH_KEY" -o BatchMode=yes \
        "autobot@$vm_ip" "timedatectl status | grep 'System clock synchronized' | grep -q 'yes'" 2>/dev/null
}

# Get VM timezone
get_vm_timezone() {
    local vm_ip="$1"

    ssh -i "$SSH_KEY" -o BatchMode=yes \
        "autobot@$vm_ip" "timedatectl show --property=Timezone --value 2>/dev/null || echo 'unknown'"
}

# Check main machine status
check_main_machine() {
    log_header "=== Main Machine (WSL) Time Status ==="

    local main_time_status
    main_time_status=$(timedatectl status 2>/dev/null || echo "timedatectl not available")

    local main_current_time
    main_current_time=$(date '+%Y-%m-%d %H:%M:%S %Z (UTC%z)')

    local main_timezone
    main_timezone=$(timedatectl show --property=Timezone --value 2>/dev/null || echo "unknown")

    local main_sync_status
    if timedatectl status | grep "System clock synchronized" | grep -q "yes" 2>/dev/null; then
        main_sync_status="synchronized"
    else
        main_sync_status="not synchronized"
    fi

    echo "Current time: $main_current_time"
    echo "Timezone: $main_timezone"
    echo "Sync status: $main_sync_status"
    echo ""
    echo "Full status:"
    echo "$main_time_status"
    echo ""

    if [[ "$main_timezone" != "$EXPECTED_TIMEZONE" ]]; then
        log_warn "Main machine timezone ($main_timezone) does not match expected ($EXPECTED_TIMEZONE)"
    fi

    if [[ "$main_sync_status" != "synchronized" ]]; then
        log_warn "Main machine time is not synchronized"
    fi
}

# Check all VMs
check_all_vms() {
    log_header "=== Distributed VMs Time Status ==="

    local overall_status=0
    local sync_count=0
    local total_vms=${#VMS[@]}

    for vm_name in "${!VMS[@]}"; do
        local vm_ip="${VMS[$vm_name]}"

        echo "----------------------------------------"
        echo "VM: $vm_name ($vm_ip)"
        echo "----------------------------------------"

        # Check connectivity
        if ! check_vm_connectivity "$vm_name" "$vm_ip"; then
            log_error "Cannot connect to $vm_name ($vm_ip)"
            overall_status=1
            echo ""
            continue
        fi

        # Get VM information
        local vm_time
        vm_time=$(get_vm_current_time "$vm_ip")

        local vm_timezone
        vm_timezone=$(get_vm_timezone "$vm_ip")

        local vm_sync_status
        if check_vm_sync_status "$vm_ip"; then
            vm_sync_status="synchronized"
            ((sync_count++))
        else
            vm_sync_status="not synchronized"
            overall_status=1
        fi

        # Display information
        echo "Current time: $vm_time"
        echo "Timezone: $vm_timezone"
        echo "Sync status: $vm_sync_status"

        # Check timezone
        if [[ "$vm_timezone" != "$EXPECTED_TIMEZONE" ]]; then
            log_warn "Timezone mismatch: expected $EXPECTED_TIMEZONE, got $vm_timezone"
            overall_status=1
        else
            log_info "Timezone matches main machine"
        fi

        # Check sync status
        if [[ "$vm_sync_status" == "synchronized" ]]; then
            log_info "Time is synchronized"
        else
            log_error "Time is not synchronized"
        fi

        echo ""
    done

    # Summary
    log_header "=== Summary ==="
    echo "Total VMs checked: $total_vms"
    echo "VMs with synchronized time: $sync_count"
    echo "VMs with timezone issues: $((total_vms - sync_count))"

    if [[ $overall_status -eq 0 ]]; then
        log_info "All VMs are properly synchronized with correct timezone"
    else
        log_error "Some VMs have time synchronization or timezone issues"
        echo ""
        echo "To fix issues, run:"
        echo "  cd $ANSIBLE_DIR"
        echo "  ansible-playbook playbooks/deploy-time-sync.yml"
    fi

    return $overall_status
}

# Force time sync on all VMs
force_sync_all() {
    log_header "=== Forcing Time Synchronization on All VMs ==="

    for vm_name in "${!VMS[@]}"; do
        local vm_ip="${VMS[$vm_name]}"

        echo "----------------------------------------"
        echo "Forcing sync on: $vm_name ($vm_ip)"
        echo "----------------------------------------"

        if ! check_vm_connectivity "$vm_name" "$vm_ip"; then
            log_error "Cannot connect to $vm_name ($vm_ip)"
            continue
        fi

        # Try to force sync
        if ssh -i "$SSH_KEY" -o BatchMode=yes \
               "autobot@$vm_ip" "sudo systemctl restart systemd-timesyncd && sleep 5" 2>/dev/null; then
            log_info "Restarted time sync service on $vm_name"
        else
            log_error "Failed to restart time sync service on $vm_name"
        fi

        # Check result
        sleep 2
        if check_vm_sync_status "$vm_ip"; then
            log_info "Time sync successful on $vm_name"
        else
            log_warn "Time sync may still be in progress on $vm_name"
        fi

        echo ""
    done
}

# Deploy time sync via Ansible
deploy_time_sync() {
    log_header "=== Deploying Time Synchronization via Ansible ==="

    if [ ! -d "$ANSIBLE_DIR" ]; then
        log_error "Ansible directory not found: $ANSIBLE_DIR"
        exit 1
    fi

    cd "$ANSIBLE_DIR"

    if [ -f "playbooks/deploy-time-sync.yml" ]; then
        log_info "Running time synchronization deployment..."
        ansible-playbook playbooks/deploy-time-sync.yml -v
    else
        log_error "Time sync playbook not found: playbooks/deploy-time-sync.yml"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "AutoBot Time Synchronization Check Utility"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  check         Check time sync status on all VMs (default)"
    echo "  main          Check main machine time status only"
    echo "  force         Force time synchronization on all VMs"
    echo "  deploy        Deploy time sync configuration via Ansible"
    echo "  help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Check all VMs"
    echo "  $0 check              # Check all VMs"
    echo "  $0 main               # Check main machine only"
    echo "  $0 force              # Force sync on all VMs"
    echo "  $0 deploy             # Deploy via Ansible"
    echo ""
    echo "Notes:"
    echo "  - Requires SSH key authentication ($SSH_KEY)"
    echo "  - Expected timezone: $EXPECTED_TIMEZONE"
    echo "  - Logs are available at /var/log/autobot/time-sync.log on each VM"
}

# Main execution
main() {
    local command="${1:-check}"

    case "$command" in
        "check")
            check_ssh_key
            check_main_machine
            check_all_vms
            ;;
        "main")
            check_main_machine
            ;;
        "force")
            check_ssh_key
            force_sync_all
            echo ""
            log_info "Waiting 10 seconds for synchronization to complete..."
            sleep 10
            check_all_vms
            ;;
        "deploy")
            check_ssh_key
            deploy_time_sync
            ;;
        "help"|"--help"|"-h")
            show_usage
            ;;
        *)
            log_error "Unknown command: $command"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
