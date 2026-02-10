#!/bin/bash

# Setup Passwordless Sudo for AutoBot User on All VMs
# This enables package installation without password prompts
# SECURITY: This script prompts for passwords interactively rather than using hardcoded credentials
# ENVIRONMENT: All remote VMs have only 'autobot' user - single-user environment

set -e

# Load SSOT configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

# SSH Configuration (from SSOT)
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${AUTOBOT_SSH_USER:-autobot}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# VM IP addresses (from SSOT)
VMS=(
    "${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:frontend"
    "${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:npu-worker"
    "${AUTOBOT_REDIS_HOST:-172.16.168.23}:redis"
    "${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:ai-stack"
    "${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:browser"
)

setup_passwordless_sudo() {
    local vm_ip="$1"
    local vm_name="$2"

    log "Setting up passwordless sudo for autobot user on $vm_name ($vm_ip)..."

    # Check if autobot already has passwordless sudo
    if ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$SSH_USER@$vm_ip" "sudo -n true 2>/dev/null"; then
        success "Passwordless sudo already configured on $vm_name"
        return 0
    fi

    # Setup passwordless sudo with user-provided password
    echo "Enter password for autobot user on $vm_name:"
    read -s password
    echo "$password" | ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$SSH_USER@$vm_ip" "sudo -S bash -c 'echo \"autobot ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/autobot-nopasswd && chmod 440 /etc/sudoers.d/autobot-nopasswd && echo \"✅ Passwordless sudo configured successfully\"'" 2>/dev/null

    if [ $? -eq 0 ]; then
        success "Passwordless sudo configured on $vm_name"
        return 0
    else
        error "Failed to configure passwordless sudo on $vm_name"
        return 1
    fi
}

main() {
    echo -e "${GREEN}🔐 Setting Up Passwordless Sudo on AutoBot VMs${NC}"
    echo -e "${BLUE}===============================================${NC}"
    echo ""

    # Check SSH key exists
    if [ ! -f "$SSH_KEY" ]; then
        error "SSH key not found: $SSH_KEY"
        echo "Run: bash scripts/utilities/setup-ssh-keys.sh"
        exit 1
    fi

    local success_count=0
    local total_vms=${#VMS[@]}

    # Setup passwordless sudo on each VM
    for vm_entry in "${VMS[@]}"; do
        IFS=':' read -r vm_ip vm_name <<< "$vm_entry"

        if setup_passwordless_sudo "$vm_ip" "$vm_name"; then
            ((success_count++))
        fi
        echo ""
    done

    echo -e "${BLUE}===============================================${NC}"
    if [ $success_count -eq $total_vms ]; then
        success "Passwordless sudo configured on all $total_vms VMs"
        echo ""
        echo -e "${CYAN}✅ AutoBot users can now install packages without password prompts${NC}"
        echo -e "${CYAN}✅ VM startup scripts will work without sudo authentication issues${NC}"
    else
        warning "Passwordless sudo configured on $success_count/$total_vms VMs"
        echo ""
        echo -e "${YELLOW}⚠️  Some VMs may still require manual sudo configuration${NC}"
    fi

    echo ""
    log "Next step: Run VM startup scripts to test package installation"
    echo -e "${BLUE}Test command: bash scripts/vm-management/start-all-vms.sh${NC}"
}

main "$@"
