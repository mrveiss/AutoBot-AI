#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# AutoBot Hyper-V Deployment Health Check Utility
# Validates all services across the 5-VM deployment
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true
LOG_FILE="/var/log/autobot/health-check-$(date +%Y%m%d-%H%M%S).log"
TIMEOUT=10

# VM endpoints (from SSOT config with fallbacks)
FRONTEND_HOST="${AUTOBOT_FRONTEND_HOST:-localhost}"
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-localhost}"
DATABASE_HOST="${AUTOBOT_REDIS_HOST:-localhost}"
AIML_HOST="${AUTOBOT_AI_STACK_HOST:-localhost}"
BROWSER_HOST="${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}"

# Service ports (from SSOT config with fallbacks)
FRONTEND_PORT="80"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
REDISINSIGHT_PORT="8002"
AI_STACK_PORT="${AUTOBOT_AI_STACK_PORT:-8080}"
NPU_WORKER_PORT="${AUTOBOT_NPU_WORKER_PORT:-8081}"
PLAYWRIGHT_PORT="${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"
VNC_PORT="5901"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    mkdir -p "$(dirname "$LOG_FILE")"

    case "$level" in
        "INFO")  echo -e "${GREEN}[INFO]${NC}  $message" | tee -a "$LOG_FILE" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC}  $message" | tee -a "$LOG_FILE" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} $message" | tee -a "$LOG_FILE" ;;
        "DEBUG") echo -e "${BLUE}[DEBUG]${NC} $message" | tee -a "$LOG_FILE" ;;
        *)       echo "[$level] $message" | tee -a "$LOG_FILE" ;;
    esac
}

# Check if a service is responding on a port
check_port() {
    local host="$1"
    local port="$2"
    local service="$3"

    if nc -z -w "$TIMEOUT" "$host" "$port" >/dev/null 2>&1; then
        log "INFO" "✅ $service ($host:$port) - Port is open"
        return 0
    else
        log "ERROR" "❌ $service ($host:$port) - Port is not responding"
        return 1
    fi
}

# Check HTTP endpoint
check_http() {
    local url="$1"
    local service="$2"
    local expected_status="${3:-200}"

    local response
    if response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout "$TIMEOUT" "$url" 2>/dev/null); then
        if [[ "$response" == "$expected_status" ]]; then
            log "INFO" "✅ $service - HTTP $response (Expected: $expected_status)"
            return 0
        else
            log "ERROR" "❌ $service - HTTP $response (Expected: $expected_status)"
            return 1
        fi
    else
        log "ERROR" "❌ $service - No HTTP response from $url"
        return 1
    fi
}

# Check Redis connectivity
check_redis() {
    local host="$1"
    local port="$2"

    if redis-cli -h "$host" -p "$port" ping >/dev/null 2>&1; then
        log "INFO" "✅ Redis ($host:$port) - PING successful"

        # Check Redis info
        local redis_info
        if redis_info=$(redis-cli -h "$host" -p "$port" info server 2>/dev/null | grep redis_version); then
            log "INFO" "✅ Redis - $redis_info"
        fi

        return 0
    else
        log "ERROR" "❌ Redis ($host:$port) - PING failed"
        return 1
    fi
}

# Check SSH connectivity
check_ssh() {
    local host="$1"
    local service="$2"

    if ssh -o ConnectTimeout="$TIMEOUT" -o BatchMode=yes "autobot@$host" exit >/dev/null 2>&1; then
        log "INFO" "✅ SSH $service ($host) - Connection successful"
        return 0
    else
        log "WARN" "⚠️  SSH $service ($host) - Connection failed (check SSH keys)"
        return 1
    fi
}

# Main health check function
main_health_check() {
    log "INFO" "🏥 AutoBot Health Check Starting..."
    log "INFO" "Timestamp: $(date)"
    log "INFO" "Log file: $LOG_FILE"
    log "INFO" ""

    local overall_status=0

    # ==========================================
    # VM1 - FRONTEND CHECKS
    # ==========================================
    log "INFO" "🌐 Checking Frontend VM (VM1 - $FRONTEND_HOST)"

    if ! check_port "$FRONTEND_HOST" "$FRONTEND_PORT" "Frontend HTTP"; then
        overall_status=1
    fi

    if ! check_http "http://$FRONTEND_HOST/health" "Frontend Health"; then
        overall_status=1
    fi

    if ! check_http "http://$FRONTEND_HOST/" "Frontend Main" "200"; then
        overall_status=1
    fi

    if ! check_ssh "$FRONTEND_HOST" "Frontend"; then
        overall_status=1
    fi

    log "INFO" ""

    # ==========================================
    # VM2 - BACKEND CHECKS
    # ==========================================
    log "INFO" "🔧 Checking Backend VM (VM2 - $BACKEND_HOST)"

    if ! check_port "$BACKEND_HOST" "$BACKEND_PORT" "Backend API"; then
        overall_status=1
    fi

    if ! check_http "http://$BACKEND_HOST:$BACKEND_PORT/api/health" "Backend Health"; then
        overall_status=1
    fi

    if ! check_http "http://$BACKEND_HOST:$BACKEND_PORT/api/system/status" "Backend Status"; then
        overall_status=1
    fi

    if ! check_ssh "$BACKEND_HOST" "Backend"; then
        overall_status=1
    fi

    log "INFO" ""

    # ==========================================
    # VM3 - DATABASE CHECKS
    # ==========================================
    log "INFO" "🗄️  Checking Database VM (VM3 - $DATABASE_HOST)"

    if ! check_port "$DATABASE_HOST" "$REDIS_PORT" "Redis Stack"; then
        overall_status=1
    fi

    if ! check_redis "$DATABASE_HOST" "$REDIS_PORT"; then
        overall_status=1
    fi

    if ! check_port "$DATABASE_HOST" "$REDISINSIGHT_PORT" "RedisInsight"; then
        overall_status=1
    fi

    if ! check_ssh "$DATABASE_HOST" "Database"; then
        overall_status=1
    fi

    # Check Redis databases
    log "INFO" "Checking Redis databases..."
    for db in {0..9} 15; do
        if redis-cli -h "$DATABASE_HOST" -p "$REDIS_PORT" -n "$db" ping >/dev/null 2>&1; then
            local key_count
            key_count=$(redis-cli -h "$DATABASE_HOST" -p "$REDIS_PORT" -n "$db" dbsize 2>/dev/null || echo "0")
            log "INFO" "  DB $db: $key_count keys"
        fi
    done

    log "INFO" ""

    # ==========================================
    # VM4 - AI/ML CHECKS
    # ==========================================
    log "INFO" "🤖 Checking AI/ML VM (VM4 - $AIML_HOST)"

    if ! check_port "$AIML_HOST" "$AI_STACK_PORT" "AI Stack"; then
        overall_status=1
    fi

    if ! check_http "http://$AIML_HOST:$AI_STACK_PORT/health" "AI Stack Health"; then
        overall_status=1
    fi

    if ! check_port "$AIML_HOST" "$NPU_WORKER_PORT" "NPU Worker"; then
        overall_status=1
    fi

    if ! check_http "http://$AIML_HOST:$NPU_WORKER_PORT/health" "NPU Worker Health"; then
        overall_status=1
    fi

    if ! check_ssh "$AIML_HOST" "AI/ML"; then
        overall_status=1
    fi

    log "INFO" ""

    # ==========================================
    # VM5 - BROWSER CHECKS
    # ==========================================
    log "INFO" "🌐 Checking Browser VM (VM5 - $BROWSER_HOST)"

    if ! check_port "$BROWSER_HOST" "$PLAYWRIGHT_PORT" "Playwright API"; then
        overall_status=1
    fi

    if ! check_http "http://$BROWSER_HOST:$PLAYWRIGHT_PORT/health" "Playwright Health"; then
        overall_status=1
    fi

    if ! check_port "$BROWSER_HOST" "$VNC_PORT" "VNC Server"; then
        overall_status=1
    fi

    if ! check_ssh "$BROWSER_HOST" "Browser"; then
        overall_status=1
    fi

    log "INFO" ""

    # ==========================================
    # INTEGRATION TESTS
    # ==========================================
    log "INFO" "🔗 Running Integration Tests"

    # Test frontend -> backend communication
    if curl -s -f "http://$FRONTEND_HOST/api/health" >/dev/null; then
        log "INFO" "✅ Frontend → Backend proxy working"
    else
        log "ERROR" "❌ Frontend → Backend proxy failed"
        overall_status=1
    fi

    # Test backend -> database communication
    if curl -s -f "http://$BACKEND_HOST:$BACKEND_PORT/api/system/redis" >/dev/null; then
        log "INFO" "✅ Backend → Database connection working"
    else
        log "ERROR" "❌ Backend → Database connection failed"
        overall_status=1
    fi

    # Test backend -> AI/ML communication
    if timeout 10 curl -s -f "http://$BACKEND_HOST:$BACKEND_PORT/api/ai/status" >/dev/null; then
        log "INFO" "✅ Backend → AI/ML connection working"
    else
        log "WARN" "⚠️  Backend → AI/ML connection timeout (may be normal during startup)"
    fi

    log "INFO" ""

    # ==========================================
    # SYSTEM RESOURCE CHECKS
    # ==========================================
    log "INFO" "📊 System Resource Summary"

    for vm in "$FRONTEND_HOST:Frontend" "$BACKEND_HOST:Backend" "$DATABASE_HOST:Database" "$AIML_HOST:AI/ML" "$BROWSER_HOST:Browser"; do
        IFS=':' read -r host name <<< "$vm"

        if ssh -o ConnectTimeout=5 -o BatchMode=yes "autobot@$host" exit >/dev/null 2>&1; then
            # Get system info
            local cpu_usage memory_usage disk_usage
            cpu_usage=$(ssh -o ConnectTimeout=5 "autobot@$host" "top -bn1 | grep 'Cpu(s)' | awk '{print \$2}' | sed 's/%us,//'" 2>/dev/null || echo "N/A")
            memory_usage=$(ssh -o ConnectTimeout=5 "autobot@$host" "free | grep Mem | awk '{printf \"%.1f\", \$3/\$2 * 100.0}'" 2>/dev/null || echo "N/A")
            disk_usage=$(ssh -o ConnectTimeout=5 "autobot@$host" "df / | tail -1 | awk '{print \$5}' | sed 's/%//'" 2>/dev/null || echo "N/A")

            log "INFO" "  $name: CPU ${cpu_usage}%, Memory ${memory_usage}%, Disk ${disk_usage}%"
        else
            log "WARN" "  $name: Unable to retrieve system stats"
        fi
    done

    log "INFO" ""

    # ==========================================
    # FINAL SUMMARY
    # ==========================================
    if [[ $overall_status -eq 0 ]]; then
        log "INFO" "🎉 Overall Health Check: PASSED"
        log "INFO" "All AutoBot services are healthy and responsive"
    else
        log "ERROR" "❌ Overall Health Check: FAILED"
        log "ERROR" "Some services are not responding properly"
    fi

    log "INFO" ""
    log "INFO" "Health check completed at $(date)"
    log "INFO" "For detailed logs, see: $LOG_FILE"

    return $overall_status
}

# Display usage
show_usage() {
    cat << EOF
AutoBot Health Check Utility

USAGE:
  $0 [OPTIONS]

OPTIONS:
  --quick         Quick check (ports only)
  --full          Full health check (default)
  --services      Check service status only
  --network       Check network connectivity only
  --resources     Check system resources only
  --help          Show this help

EXAMPLES:
  $0                    # Full health check
  $0 --quick           # Quick port check only
  $0 --services        # Service status only
  $0 --network         # Network connectivity only

EOF
}

# Quick health check (ports only)
quick_check() {
    log "INFO" "⚡ Quick Health Check"

    local status=0

    check_port "$FRONTEND_HOST" "$FRONTEND_PORT" "Frontend" || status=1
    check_port "$BACKEND_HOST" "$BACKEND_PORT" "Backend" || status=1
    check_port "$DATABASE_HOST" "$REDIS_PORT" "Database" || status=1
    check_port "$AIML_HOST" "$AI_STACK_PORT" "AI Stack" || status=1
    check_port "$BROWSER_HOST" "$PLAYWRIGHT_PORT" "Browser" || status=1

    if [[ $status -eq 0 ]]; then
        log "INFO" "✅ Quick check: All ports responding"
    else
        log "ERROR" "❌ Quick check: Some ports not responding"
    fi

    return $status
}

# Main execution
main() {
    case "${1:---full}" in
        --quick)
            quick_check
            ;;
        --full)
            main_health_check
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            main_health_check
            ;;
    esac
}

# Execute main function
main "$@"
