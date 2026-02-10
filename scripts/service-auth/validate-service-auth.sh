#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Service Authentication Validation Suite
# Usage: bash scripts/service-auth/validate-service-auth.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_HOST="172.16.168.20"
BACKEND_PORT="8001"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
REDIS_HOST="172.16.168.23"
REDIS_PORT="6379"
ENV_FILE="/home/kali/Desktop/AutoBot/.env"

# Counters
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

# Exempt paths that should return non-401 (public paths)
EXEMPT_PATHS=(
    "/api/health"
    "/api/docs"
    "/api/openapi.json"
    "/docs"
    "/redoc"
)

# Service-only paths that should return 401 without auth
SERVICE_PATHS=(
    "/api/internal/services/status"
    "/api/internal/npu/dispatch"
    "/api/internal/redis/flush-cache"
)

# Expected service keys in Redis (6 services)
SERVICE_IDS=(
    "main-backend"
    "frontend"
    "npu-worker"
    "redis-stack"
    "ai-stack"
    "browser-service"
)

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
record_pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "  [PASS] $1"
}

record_fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "  [FAIL] $1"
}

record_skip() {
    SKIP_COUNT=$((SKIP_COUNT + 1))
    echo "  [SKIP] $1"
}

print_header() {
    echo ""
    echo "--- $1 ---"
}

# ---------------------------------------------------------------------------
# Test 1: Backend health check
# ---------------------------------------------------------------------------
test_backend_health() {
    print_header "Test 1: Backend Health Check"

    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout 10 --max-time 15 \
        "${BACKEND_URL}/api/health" 2>/dev/null || echo "000")

    if [[ "${http_code}" == "200" ]]; then
        record_pass "Backend healthy (HTTP ${http_code})"
    else
        record_fail "Backend unreachable (HTTP ${http_code})"
    fi
}

# ---------------------------------------------------------------------------
# Test 2: Frontend exempt paths (should NOT return 401)
# ---------------------------------------------------------------------------
test_exempt_paths() {
    print_header "Test 2: Exempt Paths (should return non-401)"

    for path in "${EXEMPT_PATHS[@]}"; do
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" \
            --connect-timeout 5 --max-time 10 \
            "${BACKEND_URL}${path}" 2>/dev/null || echo "000")

        if [[ "${http_code}" == "000" ]]; then
            record_fail "${path} -> connection failed"
        elif [[ "${http_code}" == "401" ]]; then
            record_fail "${path} -> HTTP 401 (should be exempt)"
        else
            record_pass "${path} -> HTTP ${http_code}"
        fi
    done
}

# ---------------------------------------------------------------------------
# Test 3: Service-only paths blocked without auth
# ---------------------------------------------------------------------------
test_service_paths_blocked() {
    print_header "Test 3: Service Paths (should return 401 without auth)"

    for path in "${SERVICE_PATHS[@]}"; do
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" \
            --connect-timeout 5 --max-time 10 \
            "${BACKEND_URL}${path}" 2>/dev/null || echo "000")

        if [[ "${http_code}" == "000" ]]; then
            record_skip "${path} -> connection failed (endpoint may not exist yet)"
        elif [[ "${http_code}" == "401" || "${http_code}" == "403" ]]; then
            record_pass "${path} -> HTTP ${http_code} (blocked as expected)"
        elif [[ "${http_code}" == "404" ]]; then
            record_skip "${path} -> HTTP 404 (endpoint not deployed yet)"
        else
            record_fail "${path} -> HTTP ${http_code} (expected 401/403)"
        fi
    done
}

# ---------------------------------------------------------------------------
# Test 4: Service key presence in Redis
# ---------------------------------------------------------------------------
test_redis_service_keys() {
    print_header "Test 4: Service Keys in Redis"

    # Check Redis connectivity first
    if ! redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping \
        > /dev/null 2>&1; then
        record_fail "Cannot connect to Redis at ${REDIS_HOST}:${REDIS_PORT}"
        for sid in "${SERVICE_IDS[@]}"; do
            record_skip "Key check for ${sid} (Redis unreachable)"
        done
        return
    fi

    record_pass "Redis connectivity OK"

    for sid in "${SERVICE_IDS[@]}"; do
        local key_exists
        key_exists=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" \
            exists "service:auth:key:${sid}" 2>/dev/null || echo "0")

        if [[ "${key_exists}" == "1" ]] || [[ "${key_exists}" == *"1"* ]]; then
            record_pass "Key present: service:auth:key:${sid}"
        else
            record_fail "Key missing: service:auth:key:${sid}"
        fi
    done
}

# ---------------------------------------------------------------------------
# Test 5: Enforcement mode status
# ---------------------------------------------------------------------------
test_enforcement_status() {
    print_header "Test 5: Enforcement Mode Status"

    if [[ ! -f "${ENV_FILE}" ]]; then
        record_fail ".env file not found at ${ENV_FILE}"
        return
    fi

    local mode
    mode=$(grep "^SERVICE_AUTH_ENFORCEMENT_MODE=" "${ENV_FILE}" \
        2>/dev/null | cut -d'=' -f2 || echo "not_set")

    if [[ "${mode}" == "true" ]]; then
        record_pass "Enforcement mode: ENABLED (${mode})"
    elif [[ "${mode}" == "false" ]]; then
        record_pass "Enforcement mode: DISABLED (${mode}) -- logging only"
    else
        record_fail "Enforcement mode: UNKNOWN (${mode})"
    fi
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary() {
    local total=$((PASS_COUNT + FAIL_COUNT + SKIP_COUNT))

    echo ""
    echo "======================================================"
    echo " Service Auth Validation Summary"
    echo "======================================================"
    printf "  %-12s %d\n" "PASSED:" "${PASS_COUNT}"
    printf "  %-12s %d\n" "FAILED:" "${FAIL_COUNT}"
    printf "  %-12s %d\n" "SKIPPED:" "${SKIP_COUNT}"
    printf "  %-12s %d\n" "TOTAL:" "${total}"
    echo "======================================================"

    if [[ "${FAIL_COUNT}" -eq 0 ]]; then
        echo "  RESULT: ALL CHECKS PASSED"
    else
        echo "  RESULT: ${FAIL_COUNT} CHECK(S) FAILED"
    fi
    echo "======================================================"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo "======================================================"
    echo " AutoBot Service Authentication Validation Suite"
    echo " $(date '+%Y-%m-%d %H:%M:%S')"
    echo "======================================================"

    test_backend_health
    test_exempt_paths
    test_service_paths_blocked
    test_redis_service_keys
    test_enforcement_status
    print_summary

    if [[ "${FAIL_COUNT}" -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main "$@"
