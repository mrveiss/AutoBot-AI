#!/bin/bash
# AutoBot SSH Configuration Script
# Creates secure SSH client configuration for AutoBot distributed infrastructure
# Part of CVE-AUTOBOT-2025-001 remediation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../lib/ssot-config.sh" 2>/dev/null || true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🔐 AutoBot SSH Configuration Setup${NC}"
echo -e "${BLUE}CVE-AUTOBOT-2025-001 Remediation - Secure SSH Configuration${NC}"
echo ""

SSH_CONFIG="$HOME/.ssh/config"
BACKUP_SUFFIX="backup-$(date +%Y%m%d-%H%M%S)"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Check SSH version for accept-new support (requires SSH 7.6+)
check_ssh_version() {
    local ssh_version
    ssh_version=$(ssh -V 2>&1 | grep -oP 'OpenSSH_\K[0-9]+\.[0-9]+')
    local major minor
    major=$(echo "$ssh_version" | cut -d. -f1)
    minor=$(echo "$ssh_version" | cut -d. -f2)

    log_info "Detected OpenSSH version: $ssh_version"

    if [ "$major" -gt 7 ] || ([ "$major" -eq 7 ] && [ "$minor" -ge 6 ]); then
        echo "accept-new"
    else
        log_warn "SSH version < 7.6, using 'yes' instead of 'accept-new'"
        echo "yes"
    fi
}

# Main configuration
main() {
    # Ensure .ssh directory exists
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"

    # Backup existing SSH config if it exists
    if [ -f "$SSH_CONFIG" ]; then
        log_info "Backing up existing SSH config..."
        cp "$SSH_CONFIG" "${SSH_CONFIG}.${BACKUP_SUFFIX}"
        log_success "Backup created: ${SSH_CONFIG}.${BACKUP_SUFFIX}"
    fi

    # Determine StrictHostKeyChecking value based on SSH version
    local strict_checking
    strict_checking=$(check_ssh_version)

    log_info "Creating secure SSH configuration..."

    # Create SSH configuration
    cat > "$SSH_CONFIG" << EOF
# AutoBot Secure SSH Configuration
# Generated: $(date)
# CVE-AUTOBOT-2025-001 Remediation

# Global defaults
Host *
    # Security: Enable host key checking (CRITICAL)
    StrictHostKeyChecking $strict_checking

    # Use standard known_hosts file
    UserKnownHostsFile ~/.ssh/known_hosts

    # Key-based authentication only
    IdentitiesOnly yes
    PubkeyAuthentication yes
    PasswordAuthentication no

    # Connection settings
    ConnectTimeout 10
    ServerAliveInterval 60
    ServerAliveCountMax 3

    # Performance optimization
    ControlMaster auto
    ControlPath /tmp/.ssh-control-%h-%p-%r
    ControlPersist 600

# AutoBot WSL Host (Main Backend)
Host autobot-wsl autobot-host ${AUTOBOT_BACKEND_HOST}
    HostName ${AUTOBOT_BACKEND_HOST}
    User ${AUTOBOT_SSH_USER}
    IdentityFile ${AUTOBOT_SSH_KEY}
    Port 22

# AutoBot Frontend VM
Host autobot-frontend frontend-vm ${AUTOBOT_FRONTEND_HOST}
    HostName ${AUTOBOT_FRONTEND_HOST}
    User ${AUTOBOT_SSH_USER}
    IdentityFile ${AUTOBOT_SSH_KEY}
    Port 22

# AutoBot NPU Worker VM
Host autobot-npu npu-worker ${AUTOBOT_NPU_WORKER_HOST}
    HostName ${AUTOBOT_NPU_WORKER_HOST}
    User ${AUTOBOT_SSH_USER}
    IdentityFile ${AUTOBOT_SSH_KEY}
    Port 22

# AutoBot Redis/Database VM
Host autobot-redis redis-vm database-vm ${AUTOBOT_REDIS_HOST}
    HostName ${AUTOBOT_REDIS_HOST}
    User ${AUTOBOT_SSH_USER}
    IdentityFile ${AUTOBOT_SSH_KEY}
    Port 22

# AutoBot AI Stack VM
Host autobot-aiml ai-stack aiml-vm ${AUTOBOT_AI_STACK_HOST}
    HostName ${AUTOBOT_AI_STACK_HOST}
    User ${AUTOBOT_SSH_USER}
    IdentityFile ${AUTOBOT_SSH_KEY}
    Port 22

# AutoBot Browser VM
Host autobot-browser browser-vm ${AUTOBOT_BROWSER_SERVICE_HOST}
    HostName ${AUTOBOT_BROWSER_SERVICE_HOST}
    User ${AUTOBOT_SSH_USER}
    IdentityFile ${AUTOBOT_SSH_KEY}
    Port 22
EOF

    chmod 600 "$SSH_CONFIG"

    log_success "SSH configuration created successfully"
    echo ""
    log_info "Configuration details:"
    echo "  - StrictHostKeyChecking: $strict_checking (MITM protection enabled)"
    echo "  - Host key verification: ENABLED"
    echo "  - Known hosts file: ~/.ssh/known_hosts"
    echo "  - Authentication: Key-based only"
    echo ""

    if [ "$strict_checking" = "accept-new" ]; then
        log_info "SSH 7.6+ detected: Using 'accept-new' mode"
        echo "  - First connection: Automatically accept new host keys"
        echo "  - Subsequent connections: Verify against known_hosts"
        echo "  - Changed keys: REJECT (MITM detection)"
    else
        log_info "SSH < 7.6 detected: Using 'yes' mode"
        echo "  - Host key verification enabled, but less strict than 'accept-new'"
        echo "  - Manual host key acceptance may be required"
    fi

    echo ""
    log_info "Next steps:"
    echo "  1. Populate known_hosts: ./scripts/security/ssh-hardening/populate-known-hosts.sh"
    echo "  2. Test connections: ssh autobot-frontend 'echo OK'"
    echo "  3. Run verification: ./scripts/security/ssh-hardening/verify-ssh-security.sh"
    echo ""

    log_success "SSH configuration complete!"
}

main "$@"
