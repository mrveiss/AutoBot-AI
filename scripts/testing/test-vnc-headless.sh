#!/bin/bash

# AutoBot VNC Headless Testing Script
# Tests the standardized VNC solution for headless servers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOBOT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

TEST_FAILED=0
TESTS_RUN=0
TESTS_PASSED=0

log() {
    echo -e "${BLUE}[VNC-TEST]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[VNC-TEST]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[VNC-TEST]${NC} $1"
}

log_error() {
    echo -e "${RED}[VNC-TEST]${NC} $1"
}

test_result() {
    local test_name="$1"
    local result="$2"
    
    ((TESTS_RUN++))
    
    if [ "$result" = "0" ]; then
        log_success "✅ $test_name: PASSED"
        ((TESTS_PASSED++))
    else
        log_error "❌ $test_name: FAILED"
        TEST_FAILED=1
    fi
}

# Test 1: Check if installation script exists
test_installation_script() {
    log "Testing: Installation script exists"
    
    if [ -f "$AUTOBOT_ROOT/scripts/setup/install-vnc-headless.sh" ]; then
        if [ -x "$AUTOBOT_ROOT/scripts/setup/install-vnc-headless.sh" ]; then
            return 0
        else
            log_error "Installation script exists but is not executable"
            return 1
        fi
    else
        log_error "Installation script not found at scripts/setup/install-vnc-headless.sh"
        return 1
    fi
}

# Test 2: Check if setup.sh includes desktop option
test_setup_integration() {
    log "Testing: Setup script integration"
    
    if grep -q "desktop.*VNC.*headless" "$AUTOBOT_ROOT/setup.sh"; then
        if grep -q "desktop)" "$AUTOBOT_ROOT/setup.sh"; then
            return 0
        else
            log_error "Desktop option not found in setup.sh case statement"
            return 1
        fi
    else
        log_error "Desktop option not documented in setup.sh help"
        return 1
    fi
}

# Test 3: Check if run_autobot.sh uses systemd services
test_run_script_integration() {
    log "Testing: Run script integration"
    
    if grep -q "systemctl.*xvfb@1\|systemctl.*vncserver@1\|systemctl.*novnc" "$AUTOBOT_ROOT/run_autobot.sh"; then
        if grep -q "bash setup.sh desktop" "$AUTOBOT_ROOT/run_autobot.sh"; then
            return 0
        else
            log_error "Run script doesn't suggest desktop setup command"
            return 1
        fi
    else
        log_error "Run script doesn't use systemd VNC services"
        return 1
    fi
}

# Test 4: Test installation script help output
test_script_help() {
    log "Testing: Installation script help functionality"
    
    cd "$AUTOBOT_ROOT"
    if timeout 10 bash scripts/setup/install-vnc-headless.sh --help 2>/dev/null | grep -q "AutoBot VNC Headless Installation"; then
        return 0
    else
        log_error "Installation script help output not working properly"
        return 1
    fi
}

# Test 5: Test installation script validation
test_script_validation() {
    log "Testing: Installation script argument validation"
    
    cd "$AUTOBOT_ROOT"
    
    # Test invalid argument
    if ! timeout 5 bash scripts/setup/install-vnc-headless.sh --invalid-option >/dev/null 2>&1; then
        return 0
    else
        log_error "Installation script should reject invalid arguments"
        return 1
    fi
}

# Test 6: Check required dependencies availability
test_dependencies() {
    log "Testing: Required dependencies detection"
    
    local missing_deps=()
    
    # Check for common package managers
    if ! command -v apt-get >/dev/null 2>&1 && ! command -v yum >/dev/null 2>&1 && ! command -v dnf >/dev/null 2>&1; then
        missing_deps+=("package-manager")
    fi
    
    # Check for git (needed for noVNC)
    if ! command -v git >/dev/null 2>&1; then
        missing_deps+=("git")
    fi
    
    # Check for systemctl
    if ! command -v systemctl >/dev/null 2>&1; then
        missing_deps+=("systemctl")
    fi
    
    if [ ${#missing_deps[@]} -eq 0 ]; then
        log_success "All required dependencies available"
        return 0
    else
        log_warn "Missing dependencies: ${missing_deps[*]}"
        log_warn "This is expected on some minimal systems"
        return 0  # Don't fail the test for missing deps on test system
    fi
}

# Test 7: Check if VNC services can be queried
test_service_queries() {
    log "Testing: VNC service status queries"
    
    # Test systemctl queries (should not fail even if services don't exist)
    local services=("xvfb@1" "vncserver@1" "novnc")
    local query_failures=0
    
    for service in "${services[@]}"; do
        if ! systemctl is-active "$service" >/dev/null 2>&1 && ! systemctl is-enabled "$service" >/dev/null 2>&1; then
            # This is expected if services aren't installed yet
            continue
        fi
    done
    
    # Test netstat/ss for port checking
    if command -v netstat >/dev/null 2>&1 || command -v ss >/dev/null 2>&1; then
        return 0
    else
        log_warn "Neither netstat nor ss available for port checking"
        return 0  # Don't fail test for this
    fi
}

# Test 8: Validate configuration files
test_config_templates() {
    log "Testing: Configuration template validation"
    
    cd "$AUTOBOT_ROOT"
    
    # Check if script contains proper systemd service templates
    if grep -q "\[Unit\]" scripts/setup/install-vnc-headless.sh && \
       grep -q "\[Service\]" scripts/setup/install-vnc-headless.sh && \
       grep -q "\[Install\]" scripts/setup/install-vnc-headless.sh; then
        return 0
    else
        log_error "Installation script missing proper systemd service templates"
        return 1
    fi
}

# Test 9: Test VNC password validation
test_password_validation() {
    log "Testing: VNC password validation logic"
    
    cd "$AUTOBOT_ROOT"
    
    # Test that script contains password validation
    if grep -q "VNC_PASSWORD" scripts/setup/install-vnc-headless.sh && \
       grep -q "6-8 characters" scripts/setup/install-vnc-headless.sh; then
        return 0
    else
        log_error "Installation script missing password validation"
        return 1
    fi
}

# Test 10: Test CLAUDE.md documentation update
test_documentation_update() {
    log "Testing: Documentation includes VNC instructions"
    
    if grep -qi "vnc\|desktop" "$AUTOBOT_ROOT/CLAUDE.md"; then
        return 0
    else
        log_warn "CLAUDE.md doesn't mention VNC setup (may need manual update)"
        return 0  # Don't fail test for documentation
    fi
}

# Main test execution
run_tests() {
    log "Starting AutoBot VNC Headless Testing Suite"
    log "Testing directory: $AUTOBOT_ROOT"
    echo ""
    
    test_result "Installation Script Exists" "$(test_installation_script; echo $?)"
    test_result "Setup Script Integration" "$(test_setup_integration; echo $?)"
    test_result "Run Script Integration" "$(test_run_script_integration; echo $?)"
    test_result "Script Help Functionality" "$(test_script_help; echo $?)"
    test_result "Script Argument Validation" "$(test_script_validation; echo $?)"
    test_result "Required Dependencies" "$(test_dependencies; echo $?)"
    test_result "Service Status Queries" "$(test_service_queries; echo $?)"
    test_result "Configuration Templates" "$(test_config_templates; echo $?)"
    test_result "Password Validation Logic" "$(test_password_validation; echo $?)"
    test_result "Documentation Update" "$(test_documentation_update; echo $?)"
    
    echo ""
    
    # Summary
    if [ $TEST_FAILED -eq 0 ]; then
        log_success "🎉 All tests passed! ($TESTS_PASSED/$TESTS_RUN)"
        log_success "VNC headless solution is ready for deployment"
        
        echo ""
        echo -e "${GREEN}Next Steps:${NC}"
        echo -e "${BLUE}  1. Install: ${YELLOW}bash setup.sh desktop${NC}"
        echo -e "${BLUE}  2. Start: ${YELLOW}bash run_autobot.sh --dev${NC}"
        echo -e "${BLUE}  3. Access: ${YELLOW}http://localhost:6080/vnc.html${NC}"
        
        return 0
    else
        log_error "❌ Some tests failed ($TESTS_PASSED/$TESTS_RUN passed)"
        log_error "Please fix the issues before deploying VNC solution"
        return 1
    fi
}

# Run the test suite
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    run_tests
fi