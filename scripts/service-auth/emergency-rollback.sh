#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Emergency Service Auth Enforcement Rollback
# Usage: bash scripts/service-auth/emergency-rollback.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_HOST="172.16.168.20"
BACKEND_PORT="8001"
HEALTH_ENDPOINT="http://${BACKEND_HOST}:${BACKEND_PORT}/api/health"
ENV_FILE="/home/kali/Desktop/AutoBot/.env"
STARTUP_WAIT_SECONDS=5
SSH_KEY="${HOME}/.ssh/autobot_key"
SSH_USER="autobot"
REMOTE_ENV_FILE="/opt/autobot/.env"

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
log_info() {
    echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2
}

log_success() {
    echo "[OK]    $(date '+%Y-%m-%d %H:%M:%S') $*"
}

# ---------------------------------------------------------------------------
# Disable enforcement in .env
# ---------------------------------------------------------------------------
disable_enforcement_local() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        log_error "Environment file not found: ${ENV_FILE}"
        return 1
    fi

    if grep -q "^SERVICE_AUTH_ENFORCEMENT_MODE=" "${ENV_FILE}"; then
        sed -i 's/^SERVICE_AUTH_ENFORCEMENT_MODE=.*/SERVICE_AUTH_ENFORCEMENT_MODE=false/' \
            "${ENV_FILE}"
    else
        echo "SERVICE_AUTH_ENFORCEMENT_MODE=false" >> "${ENV_FILE}"
    fi

    log_info "Local .env updated: SERVICE_AUTH_ENFORCEMENT_MODE=false"
}

# ---------------------------------------------------------------------------
# Restart backend service
# ---------------------------------------------------------------------------
restart_backend() {
    log_info "Attempting to restart backend service..."

    # Try systemctl first (may be running as systemd service)
    if systemctl is-active --quiet autobot-backend 2>/dev/null; then
        log_info "Restarting via systemctl..."
        sudo systemctl restart autobot-backend
        return 0
    fi

    # Fallback: kill existing process and restart manually
    log_info "systemctl not available or service not managed; using pkill fallback..."
    pkill -f "uvicorn.*8001" 2>/dev/null || true
    sleep 1

    # Start backend in background from the project directory
    cd /home/kali/Desktop/AutoBot
    nohup python -m uvicorn autobot_user_backend.main:app \
        --host 0.0.0.0 --port "${BACKEND_PORT}" \
        > /tmp/autobot-backend-rollback.log 2>&1 &

    log_info "Backend process started (PID: $!)"
}

# ---------------------------------------------------------------------------
# Wait for startup
# ---------------------------------------------------------------------------
wait_for_startup() {
    log_info "Waiting ${STARTUP_WAIT_SECONDS}s for backend startup..."
    sleep "${STARTUP_WAIT_SECONDS}"
}

# ---------------------------------------------------------------------------
# Verify backend health
# ---------------------------------------------------------------------------
verify_health() {
    log_info "Checking backend health at ${HEALTH_ENDPOINT}..."

    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout 10 --max-time 15 \
        "${HEALTH_ENDPOINT}" 2>/dev/null || echo "000")

    if [[ "${http_code}" == "200" ]]; then
        log_success "Backend is healthy (HTTP ${http_code})"
        return 0
    else
        log_error "Backend health check failed (HTTP ${http_code})"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo "=============================================="
    echo " AutoBot Emergency Enforcement Rollback"
    echo "=============================================="
    echo ""

    log_info "Step 1/4: Disabling enforcement mode in local .env"
    disable_enforcement_local

    log_info "Step 2/4: Restarting backend service"
    restart_backend

    log_info "Step 3/4: Waiting for startup"
    wait_for_startup

    log_info "Step 4/4: Verifying backend health"
    if verify_health; then
        echo ""
        echo "=============================================="
        log_success "ROLLBACK SUCCESSFUL"
        echo "  Enforcement mode: DISABLED"
        echo "  Backend status:   HEALTHY"
        echo "=============================================="
        exit 0
    else
        echo ""
        echo "=============================================="
        log_error "ROLLBACK COMPLETED BUT HEALTH CHECK FAILED"
        echo "  Enforcement mode: DISABLED"
        echo "  Backend status:   UNHEALTHY"
        echo ""
        echo "  Manual investigation required:"
        echo "    tail -f /tmp/autobot-backend-rollback.log"
        echo "    journalctl -u autobot-backend --since '5 min ago'"
        echo "=============================================="
        exit 1
    fi
}

main "$@"
