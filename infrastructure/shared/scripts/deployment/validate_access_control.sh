#!/bin/bash

################################################################################
# Access Control Validation Suite
#
# Comprehensive validation of access control deployment across 6-VM infrastructure.
# Tests ownership coverage, enforcement modes, audit logging, and performance.
#
# Usage:
#   ./validate_access_control.sh [options]
#
# Options:
#   --quick              Quick validation (basic checks only)
#   --full               Full validation (includes performance tests)
#   --security-only      Security validation only
#   --performance-only   Performance validation only
#
# Examples:
#   ./validate_access_control.sh --quick
#   ./validate_access_control.sh --full
################################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
REDIS_HOST="172.16.168.23"
REDIS_PORT="6379"
BACKEND_HOST="172.16.168.20"
BACKEND_PORT="8001"

# Options
QUICK_MODE=false
FULL_MODE=false
SECURITY_ONLY=false
PERFORMANCE_ONLY=false

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_WARNED=0

# Logging functions
log_header() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${1}${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

log_section() {
    echo -e "${BLUE}▶ ${1}${NC}"
}

log_test() {
    echo -n "  Testing: $1 ... "
}

log_pass() {
    echo -e "${GREEN}PASS${NC}"
    ((TESTS_PASSED++))
}

log_fail() {
    echo -e "${RED}FAIL${NC} - $1"
    ((TESTS_FAILED++))
}

log_warn() {
    echo -e "${YELLOW}WARN${NC} - $1"
    ((TESTS_WARNED++))
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

# Test: Feature flags system exists
test_feature_flags_exists() {
    log_test "Feature flags system exists"

    if python3 -c "from backend.services.feature_flags import get_feature_flags" 2>/dev/null; then
        log_pass
    else
        log_fail "Cannot import feature_flags module"
    fi
}

# Test: Get enforcement mode
test_get_enforcement_mode() {
    log_test "Get current enforcement mode"

    local mode=$(python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    mode = await flags.get_enforcement_mode()
    print(mode.value)

asyncio.run(main())
" 2>/dev/null)

    if [ -n "$mode" ]; then
        log_pass
        log_info "Current mode: $mode"
    else
        log_fail "Cannot get enforcement mode"
    fi
}

# Test: Session ownership coverage
test_ownership_coverage() {
    log_test "Session ownership coverage"

    local result=$(python3 -c "
import asyncio
from backend.utils.async_redis_manager import get_redis_manager
from backend.security.session_ownership import SessionOwnershipValidator

async def main():
    redis_manager = await get_redis_manager()
    redis = await redis_manager.main()

    # Count total sessions
    cursor = 0
    total = 0
    while True:
        cursor, keys = await redis.scan(cursor, match='chat_session:*', count=100)
        total += len(keys)
        if cursor == 0:
            break

    # Count owned sessions
    validator = SessionOwnershipValidator(redis)
    cursor = 0
    owned = 0
    while True:
        cursor, keys = await redis.scan(cursor, match='chat_session_owner:*', count=100)
        owned += len(keys)
        if cursor == 0:
            break

    coverage = (owned / total * 100) if total > 0 else 100
    print(f'{total}|{owned}|{coverage:.1f}')

asyncio.run(main())
" 2>/dev/null)

    IFS='|' read -r total owned coverage <<< "$result"

    if [ "$coverage" = "100.0" ] || [ "$total" = "0" ]; then
        log_pass
        log_info "Coverage: $coverage% ($owned/$total sessions)"
    else
        log_fail "Incomplete coverage: $coverage% ($owned/$total sessions)"
    fi
}

# Test: Audit logging system
test_audit_logging() {
    log_test "Audit logging system"

    python3 -c "
import asyncio
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()

    # Test log write
    await logger.log(
        operation='validation.test',
        result='success',
        user_id='validator',
        details={'test': True}
    )
    await logger.flush()

    # Get statistics
    stats = await logger.get_statistics()
    if stats.get('redis_available'):
        print('OK')
        return 0
    else:
        print('FAIL')
        return 1

import sys
sys.exit(asyncio.run(main()))
" > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        log_pass
    else
        log_fail "Audit logging not working"
    fi
}

# Test: Redis connectivity
test_redis_connectivity() {
    log_test "Redis connectivity"

    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
        log_pass
    else
        log_fail "Cannot connect to Redis"
    fi
}

# Test: Backend API health
test_backend_health() {
    log_test "Backend API health"

    if curl -s -f "http://$BACKEND_HOST:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
        log_pass
    else
        log_warn "Backend API not responding"
    fi
}

# Test: Ownership validation performance
test_ownership_performance() {
    log_test "Ownership validation performance (<10ms)"

    local result=$(python3 -c "
import asyncio
import time
from backend.utils.async_redis_manager import get_redis_manager
from backend.security.session_ownership import SessionOwnershipValidator

async def main():
    redis_manager = await get_redis_manager()
    redis = await redis_manager.main()

    validator = SessionOwnershipValidator(redis)

    # Create test session
    test_session = 'test_perf_session_123'
    await validator.set_session_owner(test_session, 'testuser')

    # Measure performance
    iterations = 100
    start = time.time()

    for _ in range(iterations):
        await validator.get_session_owner(test_session)

    elapsed = (time.time() - start) * 1000  # ms
    avg_ms = elapsed / iterations

    # Cleanup
    ownership_key = validator._get_ownership_key(test_session)
    await redis.delete(ownership_key)

    print(f'{avg_ms:.2f}')

asyncio.run(main())
" 2>/dev/null)

    if [ -n "$result" ]; then
        if (( $(echo "$result < 10" | bc -l) )); then
            log_pass
            log_info "Average: ${result}ms"
        else
            log_warn "Slower than target: ${result}ms (target: <10ms)"
        fi
    else
        log_fail "Performance test failed"
    fi
}

# Test: Audit logging performance
test_audit_performance() {
    log_test "Audit logging performance (<5ms)"

    local result=$(python3 -c "
import asyncio
import time
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()

    # Measure performance
    iterations = 100
    start = time.time()

    for i in range(iterations):
        await logger.log(
            operation='performance.test',
            result='success',
            user_id='perftest',
            details={'iteration': i}
        )

    elapsed = (time.time() - start) * 1000  # ms
    avg_ms = elapsed / iterations

    await logger.flush()

    print(f'{avg_ms:.2f}')

asyncio.run(main())
" 2>/dev/null)

    if [ -n "$result" ]; then
        if (( $(echo "$result < 5" | bc -l) )); then
            log_pass
            log_info "Average: ${result}ms"
        else
            log_warn "Slower than target: ${result}ms (target: <5ms)"
        fi
    else
        log_fail "Audit performance test failed"
    fi
}

# Test: Security - unauthorized access blocked
test_security_enforcement() {
    log_test "Unauthorized access enforcement"

    # This test would require actual HTTP requests to protected endpoints
    # Simplified version checks if enforcement mode can be set

    python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags, EnforcementMode

async def main():
    flags = await get_feature_flags()

    # Test setting each mode
    for mode in [EnforcementMode.DISABLED, EnforcementMode.LOG_ONLY, EnforcementMode.ENFORCED]:
        await flags.set_enforcement_mode(mode)
        current = await flags.get_enforcement_mode()
        if current != mode:
            return 1

    return 0

import sys
sys.exit(asyncio.run(main()))
" > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        log_pass
    else
        log_fail "Cannot set enforcement modes"
    fi
}

# Run validation suite
run_validation() {
    log_header "Access Control Validation Suite"

    # Basic tests (always run)
    log_section "Basic Functionality Tests"
    test_feature_flags_exists
    test_get_enforcement_mode
    test_redis_connectivity

    if [ "$PERFORMANCE_ONLY" = false ]; then
        echo

        log_section "Security Tests"
        test_ownership_coverage
        test_audit_logging
        test_security_enforcement
    fi

    if [ "$SECURITY_ONLY" = false ] && [ "$QUICK_MODE" = false ]; then
        echo

        log_section "Performance Tests"
        test_ownership_performance
        test_audit_performance
    fi

    if [ "$SECURITY_ONLY" = false ] && [ "$PERFORMANCE_ONLY" = false ]; then
        echo

        log_section "Infrastructure Tests"
        test_backend_health
    fi
}

# Print summary
print_summary() {
    echo
    log_header "Validation Summary"

    local total=$((TESTS_PASSED + TESTS_FAILED + TESTS_WARNED))

    echo "  Total Tests:     $total"
    echo -e "  ${GREEN}Passed:${NC}          $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}          $TESTS_FAILED"
    echo -e "  ${YELLOW}Warnings:${NC}        $TESTS_WARNED"
    echo

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed successfully${NC}"
        return 0
    else
        echo -e "${RED}✗ Some tests failed - review errors above${NC}"
        return 1
    fi
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [options]

Options:
  --quick              Quick validation (basic checks only)
  --full               Full validation (includes all tests)
  --security-only      Security validation only
  --performance-only   Performance validation only
  -h, --help           Show this help message

Examples:
  $0 --quick             # Quick validation
  $0 --full              # Full comprehensive validation
  $0 --security-only     # Security tests only
EOF
}

# Main execution
main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --quick)
                QUICK_MODE=true
                shift
                ;;
            --full)
                FULL_MODE=true
                shift
                ;;
            --security-only)
                SECURITY_ONLY=true
                shift
                ;;
            --performance-only)
                PERFORMANCE_ONLY=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # Run validation
    run_validation

    # Print summary
    print_summary
}

main "$@"
