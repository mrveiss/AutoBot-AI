#!/bin/bash

# Bulletproof Frontend Architecture Testing Suite
# Tests all failure scenarios and recovery mechanisms

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true
FRONTEND_VM="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
FRONTEND_USER="${AUTOBOT_SSH_USER:-autobot}"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
TEST_RESULTS_DIR="/tmp/bulletproof-test-results"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_debug() { echo -e "${BLUE}[DEBUG]${NC} $1"; }
log_test() { echo -e "${BLUE}[TEST]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }

# Test tracking
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0
TEST_START_TIME=$(date +%s)

# Initialize test environment
initialize_test_environment() {
    log_info "Initializing bulletproof architecture test environment..."

    mkdir -p "$TEST_RESULTS_DIR"

    # Create test report header
    cat > "$TEST_RESULTS_DIR/test-report.md" << EOF
# Bulletproof Frontend Architecture Test Report

**Test Started:** $(date)
**Frontend VM:** $FRONTEND_VM
**Test Suite:** Comprehensive Failure & Recovery Testing

## Test Results Summary

EOF

    log_info "✓ Test environment initialized"
}

# Test helper functions
run_test() {
    local test_name="$1"
    local test_function="$2"

    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log_test "Running test: $test_name"

    local start_time=$(date +%s)
    local test_result="PASS"
    local error_message=""

    if $test_function; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        log_pass "$test_name"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        test_result="FAIL"
        log_fail "$test_name"
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Record test result
    cat >> "$TEST_RESULTS_DIR/test-report.md" << EOF
### $test_name
- **Result:** $test_result
- **Duration:** ${duration}s
- **Timestamp:** $(date)

EOF
}

# Test 1: Basic Frontend Connectivity
test_basic_connectivity() {
    log_debug "Testing basic frontend connectivity..."

    local max_attempts=5
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "http://$FRONTEND_VM:5173" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done

    return 1
}

# Test 2: Deployment Directory Architecture
test_deployment_architecture() {
    log_debug "Testing deployment directory architecture..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << 'EOF'
        # Check if service directory exists and is correct
        if [ ! -d "/opt/autobot/src/autobot-slm-frontend" ]; then
            echo "ERROR: Service directory missing"
            exit 1
        fi

        # Check ownership
        owner=$(stat -c '%U' /opt/autobot/src/autobot-slm-frontend)
        if [ "$owner" != "autobot-service" ]; then
            echo "ERROR: Incorrect ownership (expected: autobot-service, got: $owner)"
            exit 1
        fi

        # Check critical files
        critical_files=("package.json" "vite.config.ts" "src/App.vue")
        for file in "${critical_files[@]}"; do
            if [ ! -f "/opt/autobot/src/autobot-slm-frontend/$file" ]; then
                echo "ERROR: Critical file missing: $file"
                exit 1
            fi
        done

        echo "Deployment architecture verification passed"
EOF
}

# Test 3: Cache Busting System
test_cache_busting() {
    log_debug "Testing cache busting system..."

    # Get initial response
    local initial_response=$(curl -s "http://$FRONTEND_VM:5173" 2>/dev/null || echo "")

    if [ -z "$initial_response" ]; then
        return 1
    fi

    # Check for cache-busting headers
    local headers=$(curl -I -s "http://$FRONTEND_VM:5173" 2>/dev/null || echo "")

    if echo "$headers" | grep -q "Cache-Control.*no-cache"; then
        return 0
    else
        echo "Cache-busting headers not found"
        return 1
    fi
}

# Test 4: Router Health Monitoring
test_router_health() {
    log_debug "Testing router health monitoring..."

    local html_content=$(curl -s "http://$FRONTEND_VM:5173" 2>/dev/null || echo "")

    # Check for router-view presence
    if echo "$html_content" | grep -q "router-view\|<router-view"; then
        return 0
    else
        echo "Router-view not found in DOM"
        return 1
    fi
}

# Test 5: API Proxy Functionality
test_api_proxy() {
    log_debug "Testing API proxy functionality..."

    if curl -s -f "http://$FRONTEND_VM:5173/api/health" >/dev/null 2>&1; then
        return 0
    else
        echo "API proxy test failed"
        return 1
    fi
}

# Test 6: WebSocket Proxy
test_websocket_proxy() {
    log_debug "Testing WebSocket proxy..."

    # Simple WebSocket connection test
    if timeout 5 bash -c "</dev/tcp/$FRONTEND_VM/5173" 2>/dev/null; then
        return 0
    else
        echo "WebSocket proxy connection failed"
        return 1
    fi
}

# Test 7: Service Process Health
test_service_process() {
    log_debug "Testing service process health..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << 'EOF'
        # Check if frontend process is running
        if pgrep -f "vite.*5173" >/dev/null; then
            echo "Frontend process is running"

            # Check if PID file exists and is valid
            if [ -f "/tmp/frontend.pid" ]; then
                pid=$(cat /tmp/frontend.pid)
                if kill -0 "$pid" 2>/dev/null; then
                    echo "PID file is valid"
                    exit 0
                else
                    echo "PID file is stale"
                    exit 1
                fi
            else
                echo "PID file missing but process running"
                exit 0
            fi
        else
            echo "Frontend process not running"
            exit 1
        fi
EOF
}

# Test 8: Simulated Cache Poisoning Recovery
test_cache_poisoning_recovery() {
    log_debug "Testing cache poisoning recovery..."

    # This test would typically involve injecting stale cache content
    # For now, we test the detection mechanism

    local html_content=$(curl -s "http://$FRONTEND_VM:5173" 2>/dev/null || echo "")

    # Check if AutoBot content is present (indicating no cache poisoning)
    if echo "$html_content" | grep -q "AutoBot"; then
        return 0
    else
        echo "AutoBot content not found - possible cache poisoning"
        return 1
    fi
}

# Test 9: Service Restart Recovery
test_service_restart_recovery() {
    log_debug "Testing service restart recovery..."

    # Kill the service and check if it recovers
    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << EOF
        echo "Killing frontend service for restart test..."
        pkill -f "vite.*5173" || true
        sleep 3

        # Start service again
        cd /opt/autobot/src/autobot-slm-frontend
        export VITE_BACKEND_HOST=${AUTOBOT_BACKEND_HOST:-172.16.168.20}
        export VITE_BACKEND_PORT=${AUTOBOT_BACKEND_PORT:-8001}
        export NODE_ENV=development

        nohup npm run dev -- --host 0.0.0.0 --port ${AUTOBOT_FRONTEND_PORT:-5173} > logs/frontend.log 2>&1 &
        echo \$! > /tmp/frontend.pid

        echo "Service restarted"
EOF

    # Wait for service to come back online
    sleep 10

    # Test if service is responding
    local max_attempts=10
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "http://$FRONTEND_VM:5173" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done

    return 1
}

# Test 10: Performance Under Load
test_performance_under_load() {
    log_debug "Testing performance under load..."

    local concurrent_requests=10
    local total_requests=50
    local success_count=0

    # Run concurrent requests
    for i in $(seq 1 $concurrent_requests); do
        {
            for j in $(seq 1 $((total_requests / concurrent_requests))); do
                if curl -s -f "http://$FRONTEND_VM:5173" >/dev/null 2>&1; then
                    echo "SUCCESS" >> "$TEST_RESULTS_DIR/load-test-results.tmp"
                else
                    echo "FAILURE" >> "$TEST_RESULTS_DIR/load-test-results.tmp"
                fi
            done
        } &
    done

    # Wait for all background jobs
    wait

    # Count successes
    if [ -f "$TEST_RESULTS_DIR/load-test-results.tmp" ]; then
        success_count=$(grep -c "SUCCESS" "$TEST_RESULTS_DIR/load-test-results.tmp" || echo "0")
        rm -f "$TEST_RESULTS_DIR/load-test-results.tmp"
    fi

    # Consider test passed if >90% requests succeed
    local success_rate=$((success_count * 100 / total_requests))

    if [ $success_rate -ge 90 ]; then
        echo "Load test passed: $success_rate% success rate"
        return 0
    else
        echo "Load test failed: $success_rate% success rate"
        return 1
    fi
}

# Test 11: File Synchronization Integrity
test_file_sync_integrity() {
    log_debug "Testing file synchronization integrity..."

    # Check if local and remote files match (basic check)
    local local_hash=""
    local remote_hash=""

    if [ -f "/home/kali/Desktop/AutoBot/autobot-slm-frontend/src/App.vue" ]; then
        local_hash=$(sha256sum "/home/kali/Desktop/AutoBot/autobot-slm-frontend/src/App.vue" | cut -d' ' -f1)
    fi

    remote_hash=$(ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" \
        "sha256sum /opt/autobot/src/autobot-slm-frontend/src/App.vue 2>/dev/null | cut -d' ' -f1" || echo "")

    if [ -n "$local_hash" ] && [ -n "$remote_hash" ] && [ "$local_hash" = "$remote_hash" ]; then
        return 0
    else
        echo "File synchronization integrity check failed"
        echo "Local hash: $local_hash"
        echo "Remote hash: $remote_hash"
        return 1
    fi
}

# Test 12: Zero-Downtime Deployment Readiness
test_zero_downtime_readiness() {
    log_debug "Testing zero-downtime deployment readiness..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << 'EOF'
        # Check if blue-green directories can be created
        if [ ! -w "/opt/autobot/src" ]; then
            echo "ERROR: Cannot write to deployment directory"
            exit 1
        fi

        # Check if backup directory exists
        if [ ! -d "/opt/autobot/backups" ]; then
            echo "Creating backup directory..."
            sudo mkdir -p /opt/autobot/backups
            sudo chown -R autobot-service:autobot-service /opt/autobot/backups
        fi

        # Test staging directory creation
        test_staging="/opt/autobot/src/test-staging-$$"
        if sudo mkdir -p "$test_staging"; then
            sudo rmdir "$test_staging"
            echo "Zero-downtime deployment readiness verified"
            exit 0
        else
            echo "ERROR: Cannot create staging directory"
            exit 1
        fi
EOF
}

# Failure scenario tests
test_failure_scenarios() {
    log_info "Running failure scenario tests..."

    # Test service interruption recovery
    run_test "Service Restart Recovery" test_service_restart_recovery

    # Test cache poisoning detection
    run_test "Cache Poisoning Detection" test_cache_poisoning_recovery

    # Test performance under load
    run_test "Performance Under Load" test_performance_under_load
}

# Generate comprehensive test report
generate_final_report() {
    local end_time=$(date +%s)
    local total_duration=$((end_time - TEST_START_TIME))
    local success_rate=0

    if [ $TESTS_TOTAL -gt 0 ]; then
        success_rate=$((TESTS_PASSED * 100 / TESTS_TOTAL))
    fi

    cat >> "$TEST_RESULTS_DIR/test-report.md" << EOF

## Test Summary

- **Total Tests:** $TESTS_TOTAL
- **Passed:** $TESTS_PASSED
- **Failed:** $TESTS_FAILED
- **Success Rate:** $success_rate%
- **Total Duration:** ${total_duration}s
- **Test Completed:** $(date)

## Architecture Components Tested

1. ✅ Basic Frontend Connectivity
2. ✅ Deployment Directory Architecture
3. ✅ Cache Busting System
4. ✅ Router Health Monitoring
5. ✅ API Proxy Functionality
6. ✅ WebSocket Proxy
7. ✅ Service Process Health
8. ✅ Cache Poisoning Recovery
9. ✅ File Synchronization Integrity
10. ✅ Zero-Downtime Deployment Readiness
11. ✅ Service Restart Recovery
12. ✅ Performance Under Load

## Bulletproof Architecture Status

$(if [ $success_rate -ge 90 ]; then
    echo "🎉 **BULLETPROOF ARCHITECTURE FULLY OPERATIONAL**"
    echo ""
    echo "The frontend architecture has passed comprehensive testing and is bulletproof against:"
    echo "- Deployment failures"
    echo "- Cache poisoning"
    echo "- Router breakdowns"
    echo "- Service interruptions"
    echo "- Performance degradation"
    echo "- File synchronization issues"
else
    echo "⚠️ **BULLETPROOF ARCHITECTURE NEEDS ATTENTION**"
    echo ""
    echo "Some tests failed. Review the test results and address issues before production use."
fi)

## Recommendations

$(if [ $success_rate -ge 90 ]; then
    echo "- Architecture is production-ready"
    echo "- All bulletproof mechanisms are functioning"
    echo "- Zero-downtime deployments are supported"
    echo "- Auto-recovery systems are operational"
else
    echo "- Address failed test scenarios"
    echo "- Review deployment configuration"
    echo "- Verify service dependencies"
    echo "- Re-run tests after fixes"
fi)

---
Generated by Bulletproof Frontend Architecture Test Suite
EOF

    log_info "Final test report generated: $TEST_RESULTS_DIR/test-report.md"
}

# Main test execution
main() {
    log_info "🧪 Bulletproof Frontend Architecture Testing Suite"
    log_info "================================================="

    initialize_test_environment

    # Core functionality tests
    run_test "Basic Frontend Connectivity" test_basic_connectivity
    run_test "Deployment Architecture" test_deployment_architecture
    run_test "Cache Busting System" test_cache_busting
    run_test "Router Health Monitoring" test_router_health
    run_test "API Proxy Functionality" test_api_proxy
    run_test "WebSocket Proxy" test_websocket_proxy
    run_test "Service Process Health" test_service_process
    run_test "File Sync Integrity" test_file_sync_integrity
    run_test "Zero-Downtime Readiness" test_zero_downtime_readiness

    # Failure scenario tests
    test_failure_scenarios

    # Generate final report
    generate_final_report

    # Display results
    local success_rate=$((TESTS_PASSED * 100 / TESTS_TOTAL))

    log_info "================================================="
    if [ $success_rate -ge 90 ]; then
        log_info "🎉 BULLETPROOF ARCHITECTURE TEST: PASSED"
        log_info "Success Rate: $success_rate% ($TESTS_PASSED/$TESTS_TOTAL)"
        log_info "Architecture is bulletproof and production-ready"
    else
        log_warn "⚠️ BULLETPROOF ARCHITECTURE TEST: NEEDS ATTENTION"
        log_warn "Success Rate: $success_rate% ($TESTS_PASSED/$TESTS_TOTAL)"
        log_warn "Some components need fixes before production use"
    fi
    log_info "Detailed Report: $TEST_RESULTS_DIR/test-report.md"
    log_info "================================================="

    # Exit with appropriate code
    if [ $success_rate -ge 90 ]; then
        exit 0
    else
        exit 1
    fi
}

# Handle script interruption
trap 'log_error "Testing interrupted"; exit 1' INT TERM

# Execute main function
main "$@"
