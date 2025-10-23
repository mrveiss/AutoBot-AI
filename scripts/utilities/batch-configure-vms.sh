#!/bin/bash
# Batch VM Configuration for Single-User Environment
# Since all VMs have only 'autobot' user, this simplifies mass configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# SSH Configuration
SSH_KEY="$HOME/.ssh/autobot_key"
SSH_USER="autobot"

# VM IP addresses
VMS=(
    "172.16.168.21:frontend"
    "172.16.168.22:npu-worker"
    "172.16.168.23:redis"
    "172.16.168.24:ai-stack"
    "172.16.168.25:browser"
)

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

batch_configure_passwordless_sudo() {
    echo -e "${GREEN}🔐 Batch Configuration: Passwordless Sudo${NC}"
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${CYAN}Environment: Single-user VMs (autobot only)${NC}"
    echo ""
    
    echo -n "Enter password for autobot user (will be used for all VMs): "
    read -s password
    echo ""
    echo ""
    
    if [ -z "$password" ]; then
        warning "No password provided, skipping passwordless sudo configuration"
        return 1
    fi
    
    local success_count=0
    local total_vms=${#VMS[@]}
    
    for vm_entry in "${VMS[@]}"; do
        IFS=':' read -r vm_ip vm_name <<< "$vm_entry"
        
        log "Configuring passwordless sudo on $vm_name ($vm_ip)..."
        
        # Check if already configured
        if ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$SSH_USER@$vm_ip" "sudo -n true" 2>/dev/null; then
            success "Passwordless sudo already configured on $vm_name"
            ((success_count++))
            continue
        fi
        
        # Configure passwordless sudo
        if echo "$password" | ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$SSH_USER@$vm_ip" "sudo -S bash -c 'echo \"autobot ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/autobot-nopasswd && chmod 440 /etc/sudoers.d/autobot-nopasswd && echo \"✅ Configured\"'" 2>/dev/null | grep -q "✅ Configured"; then
            success "Passwordless sudo configured on $vm_name"
            ((success_count++))
        else
            error "Failed to configure passwordless sudo on $vm_name"
        fi
        
        echo ""
    done
    
    echo -e "${BLUE}===============================================${NC}"
    if [ $success_count -eq $total_vms ]; then
        success "Passwordless sudo configured on all $total_vms VMs"
        echo -e "${CYAN}✅ All VMs now allow package installation without prompts${NC}"
    else
        warning "Passwordless sudo configured on $success_count/$total_vms VMs"
    fi
}

batch_install_packages() {
    local packages="$1"
    
    if [ -z "$packages" ]; then
        error "Usage: batch_install_packages \"package1 package2 package3\""
        return 1
    fi
    
    echo -e "${GREEN}📦 Batch Installation: $packages${NC}"
    echo -e "${BLUE}===============================================${NC}"
    
    echo -n "Enter password for autobot user (for package installation): "
    read -s password
    echo ""
    echo ""
    
    if [ -z "$password" ]; then
        warning "No password provided, skipping package installation"
        return 1
    fi
    
    for vm_entry in "${VMS[@]}"; do
        IFS=':' read -r vm_ip vm_name <<< "$vm_entry"
        
        log "Installing packages on $vm_name ($vm_ip): $packages"
        
        # Try to install packages
        if echo "$password" | ssh -i "$SSH_KEY" -o ConnectTimeout=15 "$SSH_USER@$vm_ip" "sudo -S apt update > /dev/null 2>&1 && sudo -S apt install -y $packages > /dev/null 2>&1" 2>/dev/null; then
            success "Packages installed on $vm_name"
        else
            error "Failed to install packages on $vm_name"
        fi
        
        echo ""
    done
}

show_vm_status() {
    echo -e "${GREEN}🌐 VM Status Overview${NC}"
    echo -e "${BLUE}===============================================${NC}"
    
    for vm_entry in "${VMS[@]}"; do
        IFS=':' read -r vm_ip vm_name <<< "$vm_entry"
        
        echo -e "${CYAN}📦 $vm_name ($vm_ip):${NC}"
        
        # Check SSH connectivity
        if ssh -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "echo 'Connected'" 2>/dev/null | grep -q "Connected"; then
            echo "  SSH: ✅ Connected"
            
            # Check passwordless sudo
            if ssh -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "sudo -n true" 2>/dev/null; then
                echo "  Sudo: ✅ Passwordless"
            else
                echo "  Sudo: ⚠️  Requires password"
            fi
            
            # Check uptime
            local uptime=$(ssh -i "$SSH_KEY" -o ConnectTimeout=3 "$SSH_USER@$vm_ip" "uptime -p" 2>/dev/null | sed 's/up //' || echo "Unknown")
            echo "  Uptime: $uptime"
        else
            echo "  SSH: ❌ Not connected"
        fi
        
        echo ""
    done
}

main() {
    case "${1:-status}" in
        "sudo"|"passwordless")
            batch_configure_passwordless_sudo
            ;;
        "install")
            if [ -z "$2" ]; then
                error "Usage: $0 install \"package1 package2 package3\""
                exit 1
            fi
            batch_install_packages "$2"
            ;;
        "status")
            show_vm_status
            ;;
        "help"|"-h"|"--help")
            echo "AutoBot Batch VM Configuration"
            echo ""
            echo "Usage: $0 [command] [options]"
            echo ""
            echo "Commands:"
            echo "  status             Show VM status overview (default)"
            echo "  sudo               Configure passwordless sudo on all VMs"
            echo "  install PACKAGES   Install packages on all VMs"
            echo "  help               Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 status"
            echo "  $0 sudo"
            echo "  $0 install \"curl wget netcat-openbsd\""
            ;;
        *)
            error "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

main "$@"