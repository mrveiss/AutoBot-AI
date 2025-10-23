#!/bin/bash
# Secure VM Command Execution Utility
# Handles password prompts when passwordless sudo is not configured

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SSH_KEY="${SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${SSH_USER:-autobot}"

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

# Function to execute command on VM with password handling
secure_vm_exec() {
    local vm_ip="$1"
    local vm_name="$2"
    local command="$3"
    
    if [ -z "$vm_ip" ] || [ -z "$command" ]; then
        error "Usage: secure_vm_exec <vm_ip> <vm_name> <command>"
        return 1
    fi
    
    # First try without password (in case passwordless sudo is configured)
    if ssh -T -i "$SSH_KEY" -o ConnectTimeout=5 "$SSH_USER@$vm_ip" "$command" 2>/dev/null; then
        return 0
    fi
    
    # If that failed and command contains 'sudo', offer password option
    if [[ "$command" == *"sudo"* ]]; then
        warning "Command requires sudo privileges on $vm_name"
        echo -n "Enter password for $SSH_USER@$vm_name (or press Enter to skip): "
        read -s password
        echo ""
        
        if [ -n "$password" ]; then
            # Try with password
            echo "$password" | ssh -T -i "$SSH_KEY" -o ConnectTimeout=5 "$SSH_USER@$vm_ip" "sudo -S $command" 2>/dev/null
            return $?
        else
            warning "Skipping command that requires sudo privileges"
            return 1
        fi
    else
        # Re-run the failed command to show the actual error
        ssh -T -i "$SSH_KEY" -o ConnectTimeout=5 "$SSH_USER@$vm_ip" "$command"
        return $?
    fi
}

# Function to check if passwordless sudo is configured
check_passwordless_sudo() {
    local vm_ip="$1"
    local vm_name="${2:-VM}"
    
    if ssh -T -i "$SSH_KEY" -o ConnectTimeout=5 "$SSH_USER@$vm_ip" "sudo -n true" 2>/dev/null; then
        success "Passwordless sudo configured on $vm_name"
        return 0
    else
        warning "Passwordless sudo not configured on $vm_name"
        return 1
    fi
}

# Function to install packages securely
secure_package_install() {
    local vm_ip="$1"
    local vm_name="$2"
    shift 2
    local packages="$@"
    
    log "Installing packages on $vm_name: $packages"
    
    # Check if packages are already installed
    local missing_packages=""
    for pkg in $packages; do
        if ! ssh -T -i "$SSH_KEY" -o ConnectTimeout=5 "$SSH_USER@$vm_ip" "dpkg -l | grep -q '^ii.*$pkg '" 2>/dev/null; then
            missing_packages="$missing_packages $pkg"
        fi
    done
    
    if [ -z "$missing_packages" ]; then
        success "All packages already installed on $vm_name"
        return 0
    fi
    
    log "Missing packages on $vm_name:$missing_packages"
    
    # Try apt update and install with password handling
    if ! check_passwordless_sudo "$vm_ip" "$vm_name"; then
        warning "Package installation on $vm_name requires sudo password"
        echo -n "Enter password for $SSH_USER@$vm_name (or press Enter to skip): "
        read -s password
        echo ""
        
        if [ -n "$password" ]; then
            echo "$password" | ssh -T -i "$SSH_KEY" -o ConnectTimeout=10 "$SSH_USER@$vm_ip" "sudo -S apt update && sudo -S apt install -y$missing_packages" 2>/dev/null
        else
            warning "Skipping package installation on $vm_name"
            return 1
        fi
    else
        ssh -T -i "$SSH_KEY" -o ConnectTimeout=10 "$SSH_USER@$vm_ip" "sudo apt update && sudo apt install -y$missing_packages"
    fi
}

# Export functions for use in other scripts
export -f secure_vm_exec
export -f check_passwordless_sudo  
export -f secure_package_install
export -f log
export -f error
export -f success
export -f warning