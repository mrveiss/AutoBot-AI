#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0

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

# `set -e` stays (#14869): removing it would trade one silent failure for
# another -- an unexpected abort would then continue on a broken interpreter and
# report verdicts it never measured. What changes is that no check reaches the
# shell as a bare failing command any more:
#
#   * every python probe runs through `run_python_check`, whose invocation sits
#     in an `if` condition, so a crash is a captured return code rather than an
#     abort;
#   * the counters use arithmetic ASSIGNMENT. `((TESTS_PASSED++))` is a
#     post-increment: with the counter at 0 the expression evaluates to 0, which
#     `((...))` reports as exit status 1. Under `set -e` that aborted the run on
#     the FIRST PASS -- the suite printed one verdict, never printed a summary,
#     and exited 1, which reads as "some tests failed";
#   * `pipefail` so a failing producer in a pipeline cannot be masked by a
#     succeeding consumer.
#
# `set -u` is deliberately NOT set: several lookups here are legitimately
# optional and use `${VAR:-default}`, and adding -u now would convert those into
# the same class of mid-run abort this file exists to remove.
set -e
set -o pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Exit code a python probe uses to say "I ran, and the thing I check is broken".
# Any OTHER non-zero code means the probe could not run at all -- a missing
# import, an unreachable service, a syntax error. The two must not collapse into
# one verdict: an uncaught exception also exits 1, so before this the shell read
# "the check failed" and "the check never happened" as the same answer (#14869).
CHECK_FAILED_RC=20

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The backend package root, derived from this script's own location so it works
# from any checkout. Every python3 block below imports `services.*`/`security.*`
# from here; without this on PYTHONPATH they resolve to nothing and each check
# silently reports a failure it never actually ran (#14866).
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/autobot-backend"
# Both roots are needed: `services.*` / `security.*` live under autobot-backend,
# while `autobot_shared.*` sits at the repo root. Omitting either leaves half the
# imports unresolvable, which is the shape of the original bug.
export PYTHONPATH="${BACKEND_DIR}:${REPO_ROOT}:${PYTHONPATH:-}"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../lib/ssot-config.sh" || {
    echo "FATAL: ${SCRIPT_DIR}/../lib/ssot-config.sh could not be sourced -- refusing to run on hardcoded config fallbacks (#14172)" >&2
    return 1 2>/dev/null || exit 1
}
REDIS_HOST="${AUTOBOT_REDIS_HOST:-localhost}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-localhost}"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"

# Options
QUICK_MODE=false
FULL_MODE=false
SECURITY_ONLY=false
PERFORMANCE_ONLY=false

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_WARNED=0
# Checks that could not run. Counted separately from FAIL because they are a
# different fact: FAIL is a measurement, ERROR is the absence of one. Both make
# the run exit non-zero, so neither can be mistaken for a clean suite.
TESTS_ERRORED=0

# Set by print_summary. The EXIT trap uses it to tell "the suite finished and
# reported" apart from "the suite died partway and the last thing on screen was
# an unrelated PASS" -- the exact reading that hid #14869.
VALIDATION_COMPLETED=false

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
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_fail() {
    echo -e "${RED}FAIL${NC} - $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

log_warn() {
    echo -e "${YELLOW}WARN${NC} - $1"
    TESTS_WARNED=$((TESTS_WARNED + 1))
}

# A check that could not run. Never PASS, and never a bare FAIL: the operator
# has to know the difference between "access control is broken" and "this suite
# could not tell you anything about access control".
log_error() {
    echo -e "${RED}ERROR${NC} - could not run: $1"
    if [ -n "${2:-}" ]; then
        echo "$2" | tail -n 5 | sed 's/^/      | /'
    fi
    TESTS_ERRORED=$((TESTS_ERRORED + 1))
}

# Usage/config errors, which are not a test verdict and must not move a counter.
log_fatal() {
    echo -e "${RED}FATAL${NC} - $1" >&2
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

# Run a python3 probe without ever aborting the suite (#14869).
#
# Publishes PY_RC / PY_OUT / PY_ERR. The invocation lives in an `if` condition,
# which is the one context `set -e` exempts, so a traceback becomes a return
# code the caller can classify instead of killing the run before the caller's
# own `if [ $? -eq 0 ]` is ever reached.
run_python_check() {
    local err_file
    PY_OUT=""
    PY_ERR=""
    PY_RC=0
    err_file="$(mktemp)"
    if PY_OUT="$(python3 -c "$1" 2>"${err_file}")"; then
        PY_RC=0
    else
        PY_RC=$?
    fi
    PY_ERR="$(cat "${err_file}")"
    rm -f "${err_file}"
    return 0
}

# Numeric less-than without bc. `bc` is absent from most base images, and the
# old `(( $(echo "$x < 10" | bc -l) ))` form evaluated an EMPTY string there,
# which is 0, which reported the target as missed -- a fabricated WARN about a
# measurement that was never compared (#14869).
num_lt() {
    awk -v a="$1" -v b="$2" 'BEGIN { exit !(a + 0 < b + 0) }'
}

# Report an ERROR when a probe could not run, or a FAIL when it ran and failed.
classify_probe() {
    local what="$1"
    if [ "${PY_RC}" -eq "${CHECK_FAILED_RC}" ]; then
        log_fail "${what}"
    else
        log_error "${what} (probe exited ${PY_RC})" "${PY_ERR}"
    fi
}

# Test: Feature flags system exists
test_feature_flags_exists() {
    log_test "Feature flags system exists"

    run_python_check "from services.feature_flags import get_feature_flags"
    if [ "${PY_RC}" -eq 0 ]; then
        log_pass
    else
        log_fail "Cannot import feature_flags module"
    fi
}

# Test: Get enforcement mode
test_get_enforcement_mode() {
    log_test "Get current enforcement mode"

    local program
    program="$(cat <<'PY'
import asyncio
from services.feature_flags import get_feature_flags


async def main():
    flags = await get_feature_flags()
    mode = await flags.get_enforcement_mode()
    print(mode.value)


asyncio.run(main())
PY
)"
    run_python_check "${program}"

    if [ "${PY_RC}" -ne 0 ]; then
        log_error "enforcement-mode probe" "${PY_ERR}"
    elif [ -n "${PY_OUT}" ]; then
        log_pass
        log_info "Current mode: ${PY_OUT}"
    else
        log_fail "Enforcement mode resolved to an empty value"
    fi
}

# Test: Session ownership coverage
test_ownership_coverage() {
    log_test "Session ownership coverage"

    local program total owned coverage
    program="$(cat <<'PY'
import asyncio

from autobot_shared.redis_client import get_redis_client as get_redis_manager
from security.session_ownership import SessionOwnershipValidator


async def _count(redis, pattern):
    cursor = 0
    seen = 0
    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
        seen += len(keys)
        if cursor == 0:
            return seen


async def main():
    # Exactly what security/session_ownership.py:836 does. Calling it bare
    # returns the SYNC client (async_client defaults to False), so awaiting it
    # raises TypeError, and a .main() attribute exists on neither client. That
    # turned an import-time failure into a call-time one, which is the same
    # defect a step later (#14866). This program is now fed to python through a
    # SINGLE-QUOTED heredoc, so the shell no longer touches its contents at all
    # -- previously it was a double-quoted argument, where a backtick was
    # command substitution and bash handed python a mangled program (#14880).
    redis = await get_redis_manager(async_client=True, database="main")
    SessionOwnershipValidator(redis)
    total = await _count(redis, 'chat_session:*')
    owned = await _count(redis, 'chat_session_owner:*')
    coverage = (owned / total * 100) if total > 0 else 100
    print(f'{total}|{owned}|{coverage:.1f}')


asyncio.run(main())
PY
)"
    run_python_check "${program}"

    if [ "${PY_RC}" -ne 0 ]; then
        log_error "ownership-coverage probe" "${PY_ERR}"
        return 0
    fi

    IFS='|' read -r total owned coverage <<< "${PY_OUT}"
    if [ -z "${coverage}" ]; then
        # The probe exited 0 without producing the triple it promises. That is a
        # broken probe, not incomplete coverage -- reporting "Incomplete
        # coverage: % (/ sessions)" here is what the old code did.
        log_error "ownership-coverage probe returned no measurement" "${PY_OUT}"
    elif [ "${coverage}" = "100.0" ] || [ "${total}" = "0" ]; then
        log_pass
        log_info "Coverage: ${coverage}% (${owned}/${total} sessions)"
    else
        log_fail "Incomplete coverage: ${coverage}% (${owned}/${total} sessions)"
    fi
}

# Test: Audit logging system
test_audit_logging() {
    log_test "Audit logging system"

    local program
    program="$(cat <<'PY'
import asyncio
import sys

from services.audit_logger import get_audit_logger

CHECK_FAILED_RC = 20


async def main():
    logger = await get_audit_logger()
    await logger.log(
        operation='validation.test',
        result='success',
        user_id='validator',
        details={'test': True},
    )
    await logger.flush()
    stats = await logger.get_statistics()
    # Exit 0 or CHECK_FAILED_RC only. An uncaught exception exits 1, which is
    # how "audit logging is broken" and "this probe never ran" used to be the
    # same answer to the shell (#14869).
    return 0 if stats.get('redis_available') else CHECK_FAILED_RC


sys.exit(asyncio.run(main()))
PY
)"
    run_python_check "${program}"

    if [ "${PY_RC}" -eq 0 ]; then
        log_pass
    else
        classify_probe "Audit logging not working"
    fi
}

# Test: Redis connectivity
test_redis_connectivity() {
    log_test "Redis connectivity"

    if ! command -v redis-cli > /dev/null 2>&1; then
        log_error "redis-cli is not installed, so connectivity was never tested"
        return 0
    fi
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
        log_pass
    else
        log_fail "Cannot connect to Redis"
    fi
}

# Test: Backend API health
test_backend_health() {
    log_test "Backend API health"

    if ! command -v curl > /dev/null 2>&1; then
        log_error "curl is not installed, so backend health was never tested"
        return 0
    fi
    if curl -s -f -o /dev/null "http://$BACKEND_HOST:$BACKEND_PORT/api/health"; then
        log_pass
    else
        log_warn "Backend API not responding"
    fi
}

# Report a latency probe: ERROR when it produced no number, PASS/WARN otherwise.
report_latency() {
    local what="$1" target_ms="$2"
    if [ "${PY_RC}" -ne 0 ]; then
        log_error "${what} probe" "${PY_ERR}"
    elif [ -z "${PY_OUT}" ]; then
        log_error "${what} probe returned no measurement"
    elif num_lt "${PY_OUT}" "${target_ms}"; then
        log_pass
        log_info "Average: ${PY_OUT}ms"
    else
        log_warn "Slower than target: ${PY_OUT}ms (target: <${target_ms}ms)"
    fi
}

# Test: Ownership validation performance
test_ownership_performance() {
    log_test "Ownership validation performance (<10ms)"

    local program
    program="$(cat <<'PY'
import asyncio
import time

from autobot_shared.redis_client import get_redis_client as get_redis_manager
from security.session_ownership import SessionOwnershipValidator


async def main():
    redis = await get_redis_manager(async_client=True, database="main")
    validator = SessionOwnershipValidator(redis)
    test_session = 'test_perf_session_123'
    await validator.set_session_owner(test_session, 'testuser')

    iterations = 100
    start = time.time()
    for _ in range(iterations):
        await validator.get_session_owner(test_session)
    avg_ms = (time.time() - start) * 1000 / iterations

    await redis.delete(validator._get_ownership_key(test_session))
    print(f'{avg_ms:.2f}')


asyncio.run(main())
PY
)"
    run_python_check "${program}"
    report_latency "ownership-validation performance" 10
}

# Test: Audit logging performance
test_audit_performance() {
    log_test "Audit logging performance (<5ms)"

    local program
    program="$(cat <<'PY'
import asyncio
import time

from services.audit_logger import get_audit_logger


async def main():
    logger = await get_audit_logger()
    iterations = 100
    start = time.time()
    for i in range(iterations):
        await logger.log(
            operation='performance.test',
            result='success',
            user_id='perftest',
            details={'iteration': i},
        )
    avg_ms = (time.time() - start) * 1000 / iterations
    await logger.flush()
    print(f'{avg_ms:.2f}')


asyncio.run(main())
PY
)"
    run_python_check "${program}"
    report_latency "audit-logging performance" 5
}

# Test: Security - unauthorized access blocked
test_security_enforcement() {
    log_test "Unauthorized access enforcement"

    # This test would require actual HTTP requests to protected endpoints
    # Simplified version checks if enforcement mode can be set
    local program
    program="$(cat <<'PY'
import asyncio
import sys

from services.feature_flags import EnforcementMode, get_feature_flags

CHECK_FAILED_RC = 20


async def main():
    flags = await get_feature_flags()
    for mode in (EnforcementMode.DISABLED, EnforcementMode.LOG_ONLY, EnforcementMode.ENFORCED):
        await flags.set_enforcement_mode(mode)
        if await flags.get_enforcement_mode() != mode:
            return CHECK_FAILED_RC
    return 0


sys.exit(asyncio.run(main()))
PY
)"
    run_python_check "${program}"

    if [ "${PY_RC}" -eq 0 ]; then
        log_pass
    else
        classify_probe "Cannot set enforcement modes"
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

    local total=$((TESTS_PASSED + TESTS_FAILED + TESTS_WARNED + TESTS_ERRORED))

    echo "  Total Tests:     $total"
    echo -e "  ${GREEN}Passed:${NC}          $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}          $TESTS_FAILED"
    echo -e "  ${RED}Errored:${NC}         $TESTS_ERRORED (could not run)"
    echo -e "  ${YELLOW}Warnings:${NC}        $TESTS_WARNED"
    echo

    VALIDATION_COMPLETED=true

    if [ "$TESTS_ERRORED" -gt 0 ]; then
        echo -e "${RED}✗ ${TESTS_ERRORED} check(s) could not run - this suite cannot vouch for access control${NC}"
        return 1
    fi
    if [ "$TESTS_FAILED" -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed successfully${NC}"
        return 0
    fi
    echo -e "${RED}✗ Some tests failed - review errors above${NC}"
    return 1
}

# Say so when the suite dies before it reports (#14869).
#
# A run that aborts partway looks exactly like a run that finished: the last
# line on screen is a passing check and the shell exits non-zero. Without this
# there is nothing on screen that distinguishes the two.
report_incomplete_run() {
    local rc=$?
    if [ "$VALIDATION_COMPLETED" != true ]; then
        echo -e "${RED}✗ VALIDATION ABORTED before its summary (exit ${rc}).${NC}" >&2
        echo "  Checks that had reported by then: ${TESTS_PASSED} passed, ${TESTS_FAILED} failed, ${TESTS_ERRORED} errored, ${TESTS_WARNED} warned." >&2
        echo "  Every check after the abort point NEVER RAN. Do not read this run as a result." >&2
    fi
    return 0
}
trap report_incomplete_run EXIT

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
                VALIDATION_COMPLETED=true
                exit 0
                ;;
            *)
                # `log_error` was called here and had never been defined, so
                # under `set -e` this exited 127 from a "command not found"
                # instead of printing the usage it goes on to print (#14869).
                log_fatal "Unknown option: $1"
                show_usage
                VALIDATION_COMPLETED=true
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
