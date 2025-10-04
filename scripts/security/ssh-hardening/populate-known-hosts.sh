#!/bin/bash
# AutoBot SSH Host Key Population Script
# Securely populates known_hosts with AutoBot VM host keys
# Part of CVE-AUTOBOT-2025-001 remediation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🔐 AutoBot SSH Host Key Population${NC}"
echo -e "${BLUE}CVE-AUTOBOT-2025-001 Remediation - Secure SSH Setup${NC}"
echo ""

# AutoBot VM configuration
declare -A AUTOBOT_HOSTS=(
    ["WSL-Host"]="172.16.168.20"
    ["Frontend-VM"]="172.16.168.21"
    ["NPU-Worker-VM"]="172.16.168.22"
    ["Redis-VM"]="172.16.168.23"
    ["AI-Stack-VM"]="172.16.168.24"
    ["Browser-VM"]="172.16.168.25"
)

SSH_KEY="$HOME/.ssh/autobot_key"
KNOWN_HOSTS="$HOME/.ssh/known_hosts"
BACKUP_SUFFIX="backup-$(date +%Y%m%d-%H%M%S)"

# Function to log messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Function to test connectivity
test_connectivity() {
    local host_ip=$1
    if timeout 3 nc -z "$host_ip" 22 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to fetch and verify host key
fetch_host_key() {
    local host_name=$1
    local host_ip=$2
    
    log_info "Fetching host key for $host_name ($host_ip)..."
    
    # Test connectivity first
    if ! test_connectivity "$host_ip"; then
        log_error "$host_name is not reachable on port 22"
        return 1
    fi
    
    # Fetch host key using ssh-keyscan (secure method)
    local host_key
    host_key=$(ssh-keyscan -H -t rsa,ecdsa,ed25519 "$host_ip" 2>/dev/null)
    
    if [ -z "$host_key" ]; then
        log_error "Failed to fetch host key for $host_name"
        return 1
    fi
    
    # Display host key fingerprint for verification
    local fingerprint
    fingerprint=$(echo "$host_key" | ssh-keygen -lf - 2>/dev/null | head -1)
    log_info "Host key fingerprint: $fingerprint"
    
    # Add to known_hosts if not already present
    if ssh-keygen -F "$host_ip" >/dev/null 2>&1; then
        log_warn "$host_name ($host_ip) already in known_hosts"
    else
        echo "$host_key" >> "$KNOWN_HOSTS"
        log_success "Added $host_name ($host_ip) to known_hosts"
    fi
    
    return 0
}

# Main execution
main() {
    # Check if SSH key exists
    if [ ! -f "$SSH_KEY" ]; then
        log_error "SSH key not found at $SSH_KEY"
        log_info "Run ./scripts/utilities/setup-ssh-keys.sh first"
        exit 1
    fi
    
    # Ensure .ssh directory exists
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"
    
    # Backup existing known_hosts if it exists
    if [ -f "$KNOWN_HOSTS" ]; then
        log_info "Backing up existing known_hosts..."
        cp "$KNOWN_HOSTS" "${KNOWN_HOSTS}.${BACKUP_SUFFIX}"
        log_success "Backup created: ${KNOWN_HOSTS}.${BACKUP_SUFFIX}"
    else
        touch "$KNOWN_HOSTS"
        chmod 600 "$KNOWN_HOSTS"
        log_info "Created new known_hosts file"
    fi
    
    echo ""
    log_info "Populating host keys for AutoBot infrastructure..."
    echo ""
    
    # Populate host keys
    local success_count=0
    local fail_count=0
    
    for host_name in "${!AUTOBOT_HOSTS[@]}"; do
        host_ip="${AUTOBOT_HOSTS[$host_name]}"
        
        if fetch_host_key "$host_name" "$host_ip"; then
            ((success_count++))
        else
            ((fail_count++))
        fi
        echo ""
    done
    
    # Summary
    echo -e "${CYAN}========================================${NC}"
    log_info "Summary: $success_count successful, $fail_count failed"
    echo ""
    
    if [ $fail_count -eq 0 ]; then
        log_success "All AutoBot host keys successfully populated!"
        log_info "SSH connections will now verify host identity"
        log_info "MITM attacks will be detected and rejected"
        echo ""
        log_info "Next steps:"
        echo "  1. Test SSH connection: ssh -i $SSH_KEY autobot@172.16.168.21"
        echo "  2. Run verification tests: ./scripts/security/ssh-hardening/verify-ssh-security.sh"
        echo ""
        return 0
    else
        log_warn "Some hosts failed to populate"
        log_info "Check network connectivity to failed hosts"
        echo ""
        return 1
    fi
}

# Run main function
main "$@"
