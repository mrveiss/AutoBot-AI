#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Progressive Circuit Breaker Enforcement Ramp
# Gradually increases enforcement percentage with automatic rollback on failure.
#
# Usage:
#   bash scripts/service-auth/circuit-breaker-ramp.sh            # Default 60-min stages
#   bash scripts/service-auth/circuit-breaker-ramp.sh --quick    # 5-min stages (testing)
#   bash scripts/service-auth/circuit-breaker-ramp.sh --dry-run  # Show plan only
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_HOST="172.16.168.20"
BACKEND_PORT="8001"
HEALTH_ENDPOINT="http://${BACKEND_HOST}:${BACKEND_PORT}/api/health"
ENV_FILE="/home/kali/Desktop/AutoBot/.env"
HEALTH_CHECK_INTERVAL=30  # seconds between health checks during stage
STARTUP_WAIT=5

# Ramp stages (percentage values)
STAGES=(10 25 50 75 100)

# Default stage duration in seconds (60 minutes)
STAGE_DURATION_DEFAULT=3600
# Quick mode stage duration in seconds (5 minutes)
STAGE_DURATION_QUICK=300

# Runtime flags
DRY_RUN=false
STAGE_DURATION="${STAGE_DURATION_DEFAULT}"

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
log_info() {
    echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_warn() {
    echo "[WARN]  $(date '+%Y-%m-%d %H:%M:%S') $*" >&2
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2
}

log_success() {
    echo "[OK]    $(date '+%Y-%m-%d %H:%M:%S') $*"
}

# ---------------------------------------------------------------------------
# Parse command-line arguments
# ---------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --quick)
                STAGE_DURATION="${STAGE_DURATION_QUICK}"
                shift
                ;;
            --duration)
                STAGE_DURATION="$2"
                shift 2
                ;;
            *)
                log_error "Unknown argument: $1"
                echo "Usage: $0 [--dry-run] [--quick] [--duration SECONDS]"
                exit 1
                ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# Display ramp plan
# ---------------------------------------------------------------------------
display_plan() {
    local duration_human
    duration_human=$(format_duration "${STAGE_DURATION}")

    echo "======================================================"
    echo " Circuit Breaker Ramp Plan"
    echo "======================================================"
    echo ""
    echo "  Stage duration: ${duration_human} each"
    echo "  Health check interval: ${HEALTH_CHECK_INTERVAL}s"
    echo "  Stages:"

    local total_seconds=0
    for i in "${!STAGES[@]}"; do
        local pct="${STAGES[$i]}"
        local stage_num=$((i + 1))
        total_seconds=$((total_seconds + STAGE_DURATION))
        echo "    ${stage_num}. Enforce ${pct}% for ${duration_human}"
    done

    echo ""
    echo "  Total estimated time: $(format_duration ${total_seconds})"
    echo "  Auto-rollback: YES (on health check failure)"
    echo "======================================================"
}

# ---------------------------------------------------------------------------
# Format seconds as human-readable duration
# ---------------------------------------------------------------------------
format_duration() {
    local total_seconds="$1"
    local hours=$((total_seconds / 3600))
    local minutes=$(((total_seconds % 3600) / 60))

    if [[ "${hours}" -gt 0 ]]; then
        echo "${hours}h ${minutes}m"
    else
        echo "${minutes}m"
    fi
}

# ---------------------------------------------------------------------------
# Update circuit breaker percentage in .env
# ---------------------------------------------------------------------------
update_percentage() {
    local pct="$1"

    if [[ ! -f "${ENV_FILE}" ]]; then
        log_error "Environment file not found: ${ENV_FILE}"
        return 1
    fi

    # Update or add the percentage variable
    if grep -q "^SERVICE_AUTH_CIRCUIT_BREAKER_PERCENTAGE=" "${ENV_FILE}"; then
        sed -i \
            "s/^SERVICE_AUTH_CIRCUIT_BREAKER_PERCENTAGE=.*/SERVICE_AUTH_CIRCUIT_BREAKER_PERCENTAGE=${pct}/" \
            "${ENV_FILE}"
    else
        echo "SERVICE_AUTH_CIRCUIT_BREAKER_PERCENTAGE=${pct}" >> "${ENV_FILE}"
    fi

    # Ensure circuit breaker is enabled
    if grep -q "^SERVICE_AUTH_CIRCUIT_BREAKER_ENABLED=" "${ENV_FILE}"; then
        sed -i \
            "s/^SERVICE_AUTH_CIRCUIT_BREAKER_ENABLED=.*/SERVICE_AUTH_CIRCUIT_BREAKER_ENABLED=true/" \
            "${ENV_FILE}"
    else
        echo "SERVICE_AUTH_CIRCUIT_BREAKER_ENABLED=true" >> "${ENV_FILE}"
    fi

    log_info "Updated circuit breaker to ${pct}%"
}

# ---------------------------------------------------------------------------
# Restart the backend service
# ---------------------------------------------------------------------------
restart_backend() {
    log_info "Restarting backend..."

    if systemctl is-active --quiet autobot-backend 2>/dev/null; then
        sudo systemctl restart autobot-backend
    else
        pkill -f "uvicorn.*8001" 2>/dev/null || true
        sleep 1
        cd /home/kali/Desktop/AutoBot
        nohup python -m uvicorn autobot_user_backend.main:app \
            --host 0.0.0.0 --port "${BACKEND_PORT}" \
            > /tmp/autobot-backend-ramp.log 2>&1 &
    fi

    sleep "${STARTUP_WAIT}"
}

# ---------------------------------------------------------------------------
# Check backend health (returns 0 for healthy)
# ---------------------------------------------------------------------------
check_health() {
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout 10 --max-time 15 \
        "${HEALTH_ENDPOINT}" 2>/dev/null || echo "000")

    [[ "${http_code}" == "200" ]]
}

# ---------------------------------------------------------------------------
# Roll back to 0% enforcement
# ---------------------------------------------------------------------------
rollback() {
    log_error "ROLLING BACK: Setting circuit breaker to 0% and disabling enforcement"
    update_percentage 0

    # Also disable enforcement mode entirely as a safety measure
    if grep -q "^SERVICE_AUTH_ENFORCEMENT_MODE=" "${ENV_FILE}"; then
        sed -i \
            's/^SERVICE_AUTH_ENFORCEMENT_MODE=.*/SERVICE_AUTH_ENFORCEMENT_MODE=false/' \
            "${ENV_FILE}"
    fi

    restart_backend

    if check_health; then
        log_warn "Rollback complete. Backend is healthy at 0% enforcement."
    else
        log_error "Rollback complete but backend is UNHEALTHY. Manual intervention required."
    fi
}

# ---------------------------------------------------------------------------
# Monitor health during a stage
# ---------------------------------------------------------------------------
monitor_stage() {
    local pct="$1"
    local elapsed=0

    while [[ "${elapsed}" -lt "${STAGE_DURATION}" ]]; do
        sleep "${HEALTH_CHECK_INTERVAL}"
        elapsed=$((elapsed + HEALTH_CHECK_INTERVAL))

        if ! check_health; then
            log_error "Health check FAILED at ${pct}% (elapsed: ${elapsed}s)"
            return 1
        fi

        local remaining=$((STAGE_DURATION - elapsed))
        log_info "Stage ${pct}%: healthy (${elapsed}s elapsed, ${remaining}s remaining)"
    done

    return 0
}

# ---------------------------------------------------------------------------
# Execute a single ramp stage
# ---------------------------------------------------------------------------
execute_stage() {
    local stage_num="$1"
    local pct="$2"
    local duration_human
    duration_human=$(format_duration "${STAGE_DURATION}")

    echo ""
    log_info "=== Stage ${stage_num}/${#STAGES[@]}: ${pct}% enforcement (${duration_human}) ==="

    update_percentage "${pct}"
    restart_backend

    if ! check_health; then
        log_error "Backend failed to start at ${pct}%"
        rollback
        return 1
    fi

    log_success "Backend healthy at ${pct}%. Monitoring for ${duration_human}..."

    if ! monitor_stage "${pct}"; then
        rollback
        return 1
    fi

    log_success "Stage ${stage_num} complete: ${pct}% held stable for ${duration_human}"
    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    parse_args "$@"

    echo "======================================================"
    echo " AutoBot Circuit Breaker Progressive Ramp"
    echo " $(date '+%Y-%m-%d %H:%M:%S')"
    echo "======================================================"

    display_plan

    if [[ "${DRY_RUN}" == "true" ]]; then
        echo ""
        log_info "DRY RUN: No changes will be made."
        exit 0
    fi

    echo ""
    log_info "Starting progressive ramp..."

    for i in "${!STAGES[@]}"; do
        local stage_num=$((i + 1))
        local pct="${STAGES[$i]}"

        if ! execute_stage "${stage_num}" "${pct}"; then
            echo ""
            log_error "Ramp ABORTED at stage ${stage_num} (${pct}%)"
            exit 1
        fi
    done

    echo ""
    echo "======================================================"
    log_success "RAMP COMPLETE: Enforcement at 100%"
    echo "  All ${#STAGES[@]} stages passed health checks."
    echo "  Enforcement is now fully active."
    echo "======================================================"
    exit 0
}

main "$@"
