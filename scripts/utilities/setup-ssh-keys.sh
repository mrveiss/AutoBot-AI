#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Setup SSH certificate-based authentication for all AutoBot VMs
# This script deploys SSH keys to all remote hosts in the distributed architecture

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
    echo -e "${BLUE}[SETUP]${NC} $1"
}

# AutoBot VM configuration - Using SSOT env vars
declare -A VMS=(
    ["frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_PUB_KEY="$SSH_KEY.pub"
REMOTE_USER="${AUTOBOT_SSH_USER:-autobot}"
# SECURITY: No default password - must use SSH keys or interactive auth
# DEFAULT_PASSWORD removed for security compliance

log_header "AutoBot SSH Key Setup for Distributed Architecture"
echo "=========================================================="

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    log_warn "SSH key not found. Generating new key pair..."
    ssh-keygen -t rsa -b 4096 -f "$SSH_KEY" -N "" -C "autobot@distributed-architecture"
    log_info "SSH key pair generated"
else
    log_info "SSH key already exists"
fi

# Display key fingerprint for verification
log_info "SSH Key Fingerprint:"
ssh-keygen -lf "$SSH_KEY"
echo

# Function to deploy key to a single host
deploy_key_to_host() {
    local host_name=$1
    local host_ip=$2

    log_header "Setting up SSH key for $host_name ($host_ip)"

    # SECURITY FIX: Use interactive SSH key deployment instead of hardcoded passwords
    log_info "Attempting SSH key deployment (may require interactive password entry)..."

    # Check if key-based auth already works
    if ssh -i "$SSH_KEY" -o ConnectTimeout=10 \
        -o PasswordAuthentication=no "$REMOTE_USER@$host_ip" "echo 'Key auth test successful'" 2>/dev/null; then
        log_info "SSH key authentication already working for $host_name"
        return 0
    fi

    log_info "Deploying SSH key to $host_name (password required interactively)..."

    # Copy SSH key to remote host - will prompt for password if needed
    if ssh-copy-id -i "$SSH_PUB_KEY" "$REMOTE_USER@$host_ip"; then

        # Test key-based authentication
        if ssh -i "$SSH_KEY" -o ConnectTimeout=5 \
            "$REMOTE_USER@$host_ip" "echo 'SSH key authentication successful'" 2>/dev/null; then
            log_info "$host_name: SSH key deployment successful"
            return 0
        else
            log_error "$host_name: SSH key authentication failed"
            return 1
        fi
    else
        log_warn "$host_name: Cannot connect with password authentication"

        # Try key-based auth in case it's already set up
        if ssh -i "$SSH_KEY" -o ConnectTimeout=5 \
            "$REMOTE_USER@$host_ip" "echo 'SSH key authentication successful'" 2>/dev/null; then
            log_info "$host_name: SSH key already configured"
            return 0
        else
            log_error "$host_name: Cannot establish any authentication"
            return 1
        fi
    fi
}

# Deploy keys to all hosts
successful_hosts=()
failed_hosts=()

for host_name in "${!VMS[@]}"; do
    host_ip="${VMS[$host_name]}"

    if deploy_key_to_host "$host_name" "$host_ip"; then
        successful_hosts+=("$host_name")
    else
        failed_hosts+=("$host_name")
    fi
    echo
done

# Summary report
echo "=========================================================="
log_header "SSH Key Deployment Summary"

if [ ${#successful_hosts[@]} -gt 0 ]; then
    log_info "Successfully configured SSH keys for:"
    for host in "${successful_hosts[@]}"; do
        echo -e "  $host (${VMS[$host]})"
    done
fi

if [ ${#failed_hosts[@]} -gt 0 ]; then
    log_warn "Failed to configure SSH keys for:"
    for host in "${failed_hosts[@]}"; do
        echo -e "  $host (${VMS[$host]})"
    done
fi

echo
log_info "Total: ${#successful_hosts[@]} successful, ${#failed_hosts[@]} failed"

# Test all connections
echo
log_header "Testing SSH Key Authentication"
echo "=========================================="

for host_name in "${successful_hosts[@]}"; do
    host_ip="${VMS[$host_name]}"
    if ssh -i "$SSH_KEY" -o ConnectTimeout=5 \
        "$REMOTE_USER@$host_ip" "hostname && uptime" 2>/dev/null; then
        log_info "$host_name: Connection test successful"
    else
        log_error "$host_name: Connection test failed"
    fi
done

echo
if [ ${#failed_hosts[@]} -eq 0 ]; then
    log_info "All SSH keys configured successfully! Password authentication can now be disabled."
else
    log_warn "Some hosts failed. Manual intervention may be required."
fi

echo
log_info "SSH Key Location: $SSH_KEY"
log_info "Usage Example: ssh -i $SSH_KEY $REMOTE_USER@${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
