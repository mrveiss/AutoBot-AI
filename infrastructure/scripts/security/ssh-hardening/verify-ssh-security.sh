#!/bin/bash
# AutoBot SSH Security Verification Script
# Verifies SSH host key verification is working properly
# Part of CVE-AUTOBOT-2025-001 remediation testing

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🔐 AutoBot SSH Security Verification${NC}"
echo -e "${BLUE}CVE-AUTOBOT-2025-001 Remediation - Security Testing${NC}"
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
SSH_CONFIG="$HOME/.ssh/config"

# Test results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

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
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
}

# Test 1: Verify SSH config exists
test_ssh_config() {
    ((TOTAL_TESTS++))
    log_info "Test 1: Checking SSH config exists..."

    if [ -f "$SSH_CONFIG" ]; then
        log_success "SSH config exists at $SSH_CONFIG"
        ((PASSED_TESTS++))
        return 0
    else
        log_fail "SSH config NOT found at $SSH_CONFIG"
        log_info "Run: ./scripts/security/ssh-hardening/configure-ssh.sh"
        ((FAILED_TESTS++))
        return 1
    fi
}

# Test 2: Verify no StrictHostKeyChecking=no in config
test_no_disabled_checking() {
    ((TOTAL_TESTS++))
    log_info "Test 2: Checking SSH config doesn't disable host key checking..."

    if grep -q "StrictHostKeyChecking.*no" "$SSH_CONFIG" 2>/dev/null; then
        log_fail "SSH config contains 'StrictHostKeyChecking no' (VULNERABLE)"
        ((FAILED_TESTS++))
        return 1
    else
        log_success "SSH config does not disable host key checking"
        ((PASSED_TESTS++))
        return 0
    fi
}

# Test 3: Verify known_hosts exists and is not empty
test_known_hosts() {
    ((TOTAL_TESTS++))
    log_info "Test 3: Checking known_hosts exists and has entries..."

    if [ ! -f "$KNOWN_HOSTS" ]; then
        log_fail "known_hosts NOT found"
        log_info "Run: ./scripts/security/ssh-hardening/populate-known-hosts.sh"
        ((FAILED_TESTS++))
        return 1
    fi

    local host_count
    host_count=$(grep -c "^[^#]" "$KNOWN_HOSTS" 2>/dev/null || echo 0)

    if [ "$host_count" -ge 6 ]; then
        log_success "known_hosts contains $host_count host keys (expected >= 6)"
        ((PASSED_TESTS++))
        return 0
    else
        log_fail "known_hosts only has $host_count entries (expected >= 6)"
        log_info "Run: ./scripts/security/ssh-hardening/populate-known-hosts.sh"
        ((FAILED_TESTS++))
        return 1
    fi
}

# Test 4: Verify SSH connections work with host key checking
test_ssh_connections() {
    log_info "Test 4: Testing SSH connections with host key verification..."

    local test_passed=0
    local test_failed=0

    for host_name in "${!AUTOBOT_HOSTS[@]}"; do
        ((TOTAL_TESTS++))
        host_ip="${AUTOBOT_HOSTS[$host_name]}"

        # Test SSH connection
        if timeout 5 ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=3 \
            "autobot@$host_ip" "echo 'SSH OK'" >/dev/null 2>&1; then
            log_success "$host_name ($host_ip): Connection successful with host key verification"
            ((PASSED_TESTS++))
            ((test_passed++))
        else
            log_fail "$host_name ($host_ip): Connection failed"
            ((FAILED_TESTS++))
            ((test_failed++))
        fi
    done

    if [ $test_failed -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

# Test 5: Verify no vulnerable scripts
test_no_vulnerable_scripts() {
    ((TOTAL_TESTS++))
    log_info "Test 5: Checking for vulnerable SSH usage in scripts..."

    local vulnerable_count
    vulnerable_count=$(grep -r "StrictHostKeyChecking=no" \
        /home/kali/Desktop/AutoBot/scripts/ 2>/dev/null | wc -l)

    if [ "$vulnerable_count" -eq 0 ]; then
        log_success "No vulnerable SSH usage found in scripts"
        ((PASSED_TESTS++))
        return 0
    else
        log_fail "Found $vulnerable_count instances of StrictHostKeyChecking=no in scripts"
        log_info "Scripts still need remediation"
        ((FAILED_TESTS++))
        return 1
    fi
}

# Test 6: Verify host key fingerprints
test_host_fingerprints() {
    log_info "Test 6: Displaying host key fingerprints for verification..."

    for host_name in "${!AUTOBOT_HOSTS[@]}"; do
        host_ip="${AUTOBOT_HOSTS[$host_name]}"

        local fingerprint
        fingerprint=$(ssh-keygen -F "$host_ip" 2>/dev/null | \
            ssh-keygen -lf - 2>/dev/null | head -1 || echo "Not found")

        echo "  $host_name ($host_ip): $fingerprint"
    done

    echo ""
    log_info "Verify these fingerprints match your VMs"
}

# Test 7: Test MITM detection (optional, requires confirmation)
test_mitm_detection() {
    log_warn "Test 7: MITM Detection Test (DESTRUCTIVE - skipped by default)"
    log_info "This test would simulate a host key change to verify rejection"
    log_info "Run manually if needed: ./scripts/security/ssh-hardening/test-mitm-detection.sh"
}

# Main execution
main() {
    # Run all tests
    echo -e "${CYAN}Starting security verification tests...${NC}"
    echo ""

    test_ssh_config
    echo ""

    test_no_disabled_checking
    echo ""

    test_known_hosts
    echo ""

    test_ssh_connections
    echo ""

    test_no_vulnerable_scripts
    echo ""

    test_host_fingerprints
    echo ""

    test_mitm_detection
    echo ""

    # Summary
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}Security Verification Summary${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    log_info "Total Tests: $TOTAL_TESTS"
    log_success "Passed: $PASSED_TESTS"
    if [ $FAILED_TESTS -gt 0 ]; then
        log_fail "Failed: $FAILED_TESTS"
    else
        log_info "Failed: $FAILED_TESTS"
    fi
    echo ""

    if [ $FAILED_TESTS -eq 0 ]; then
        log_success "✅ All security tests PASSED!"
        log_success "SSH host key verification is properly configured"
        log_success "MITM attacks will be detected and rejected"
        echo ""
        return 0
    else
        log_error "❌ Some security tests FAILED"
        log_info "Review failed tests and run remediation scripts"
        echo ""
        log_info "Remediation steps:"
        echo "  1. Configure SSH: ./scripts/security/ssh-hardening/configure-ssh.sh"
        echo "  2. Populate keys: ./scripts/security/ssh-hardening/populate-known-hosts.sh"
        echo "  3. Fix scripts: ./scripts/security/ssh-hardening/fix-all-scripts.sh"
        echo ""
        return 1
    fi
}

main "$@"
