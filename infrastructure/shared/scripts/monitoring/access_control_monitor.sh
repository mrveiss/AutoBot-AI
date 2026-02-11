#!/bin/bash

################################################################################
# Access Control Monitoring Dashboard
#
# Real-time monitoring of access control rollout across 6-VM infrastructure.
# Displays enforcement mode, audit logs, unauthorized access attempts, and
# performance metrics.
#
# Usage:
#   ./access_control_monitor.sh [options]
#
# Options:
#   --interval SECONDS     Refresh interval (default: 5)
#   --follow               Follow mode (continuous updates)
#   --audit-only           Show only audit logs
#   --stats-only           Show only statistics
#   --watch-denials        Watch for denied access attempts
#
# Examples:
#   ./access_control_monitor.sh --follow
#   ./access_control_monitor.sh --watch-denials
#   ./access_control_monitor.sh --interval 10
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Configuration
REDIS_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"

# Options
INTERVAL=5
FOLLOW_MODE=false
AUDIT_ONLY=false
STATS_ONLY=false
WATCH_DENIALS=false

# Logging functions
log_header() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${1}${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

log_section() {
    echo -e "${BLUE}▶ ${1}${NC}"
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_metric() {
    local label="$1"
    local value="$2"
    printf "  %-30s %s\n" "$label:" "$value"
}

# Get current enforcement mode
get_enforcement_mode() {
    python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    mode = await flags.get_enforcement_mode()
    print(mode.value.upper())

asyncio.run(main())
" 2>/dev/null || echo "UNKNOWN"
}

# Get rollout statistics
get_rollout_stats() {
    python3 -c "
import asyncio
import json
from backend.services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    stats = await flags.get_rollout_statistics()
    print(json.dumps(stats, indent=2))

asyncio.run(main())
" 2>/dev/null || echo "{}"
}

# Get audit statistics
get_audit_stats() {
    python3 -c "
import asyncio
import json
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()
    stats = await logger.get_statistics()
    print(json.dumps(stats, indent=2))

asyncio.run(main())
" 2>/dev/null || echo "{}"
}

# Get recent denied access attempts
get_recent_denials() {
    python3 -c "
import asyncio
import json
from datetime import datetime, timedelta
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()
    entries = await logger.query(
        result='denied',
        start_time=datetime.now() - timedelta(hours=1),
        limit=10
    )

    for entry in entries:
        print(f'{entry.timestamp} | {entry.user_id or \"anonymous\"} | {entry.operation} | {entry.resource}')

asyncio.run(main())
" 2>/dev/null
}

# Get session ownership coverage
get_ownership_coverage() {
    python3 -c "
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
    cursor = 0
    owned = 0
    while True:
        cursor, keys = await redis.scan(cursor, match='chat_session_owner:*', count=100)
        owned += len(keys)
        if cursor == 0:
            break

    coverage = (owned / total * 100) if total > 0 else 0
    print(f'{total}|{owned}|{coverage:.1f}')

asyncio.run(main())
" 2>/dev/null || echo "0|0|0"
}

# Display dashboard
show_dashboard() {
    clear

    log_header "Access Control Monitoring Dashboard - $(date '+%Y-%m-%d %H:%M:%S')"

    # Current enforcement mode
    log_section "Enforcement Status"
    local mode=$(get_enforcement_mode)

    case $mode in
        DISABLED)
            echo -e "  Mode: ${GREEN}DISABLED${NC} (no enforcement)"
            ;;
        LOG_ONLY)
            echo -e "  Mode: ${YELLOW}LOG_ONLY${NC} (monitoring violations)"
            ;;
        ENFORCED)
            echo -e "  Mode: ${RED}ENFORCED${NC} (blocking violations)"
            ;;
        *)
            echo -e "  Mode: ${MAGENTA}UNKNOWN${NC}"
            ;;
    esac
    echo

    # Ownership coverage
    if [ "$AUDIT_ONLY" = false ]; then
        log_section "Session Ownership Coverage"
        local coverage=$(get_ownership_coverage)
        IFS='|' read -r total owned percent <<< "$coverage"

        log_metric "Total Sessions" "$total"
        log_metric "Owned Sessions" "$owned"
        log_metric "Coverage" "${percent}%"

        if [ "$percent" = "100.0" ]; then
            echo -e "  ${GREEN}✓ Full ownership coverage${NC}"
        else
            echo -e "  ${YELLOW}⚠ Incomplete ownership coverage${NC}"
        fi
        echo
    fi

    # Rollout statistics
    if [ "$AUDIT_ONLY" = false ] && [ "$STATS_ONLY" = false ]; then
        log_section "Rollout Statistics"
        local rollout_stats=$(get_rollout_stats)

        echo "$rollout_stats" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'  Current Mode:         {data.get(\"current_mode\", \"unknown\").upper()}')
    print(f'  Endpoint Overrides:   {data.get(\"total_endpoints_configured\", 0)}')
    print(f'  Mode Changes:         {len(data.get(\"history\", []))}')
except:
    print('  Error loading rollout statistics')
"
        echo
    fi

    # Audit statistics
    if [ "$STATS_ONLY" = false ]; then
        log_section "Audit Logging Statistics"
        local audit_stats=$(get_audit_stats)

        echo "$audit_stats" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'  Total Logged:         {data.get(\"total_logged\", 0)}')
    print(f'  Failed:               {data.get(\"total_failed\", 0)}')
    print(f'  Redis Failures:       {data.get(\"redis_failures\", 0)}')
    print(f'  Queue Size:           {data.get(\"batch_queue_size\", 0)}')
    print(f'  Last 24h Entries:     {data.get(\"entries_last_24h\", \"N/A\")}')
    redis_status = 'UP' if data.get('redis_available') else 'DOWN'
    color = '\033[0;32m' if data.get('redis_available') else '\033[0;31m'
    print(f'  Redis Status:         {color}{redis_status}\033[0m')
except:
    print('  Error loading audit statistics')
"
        echo
    fi

    # Recent denied access attempts
    if [ "$WATCH_DENIALS" = true ] || [ "$mode" = "ENFORCED" ]; then
        log_section "Recent Denied Access Attempts (Last Hour)"
        local denials=$(get_recent_denials)

        if [ -z "$denials" ]; then
            echo -e "  ${GREEN}✓ No denied access attempts${NC}"
        else
            echo "$denials" | head -10
        fi
        echo
    fi

    # Backend health
    if [ "$AUDIT_ONLY" = false ]; then
        log_section "Backend Health"
        if curl -s -f "http://$BACKEND_HOST:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
            echo -e "  Backend API: ${GREEN}UP${NC} ($BACKEND_HOST:$BACKEND_PORT)"
        else
            echo -e "  Backend API: ${RED}DOWN${NC} ($BACKEND_HOST:$BACKEND_PORT)"
        fi

        if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
            echo -e "  Redis:       ${GREEN}UP${NC} ($REDIS_HOST:$REDIS_PORT)"
        else
            echo -e "  Redis:       ${RED}DOWN${NC} ($REDIS_HOST:$REDIS_PORT)"
        fi
        echo
    fi

    # Instructions
    if [ "$FOLLOW_MODE" = true ]; then
        echo -e "${CYAN}Press Ctrl+C to exit${NC}"
    fi
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [options]

Options:
  --interval SECONDS     Refresh interval (default: 5)
  --follow               Follow mode (continuous updates)
  --audit-only           Show only audit logs
  --stats-only           Show only statistics
  --watch-denials        Watch for denied access attempts
  -h, --help             Show this help message

Examples:
  $0 --follow                    # Continuous monitoring
  $0 --watch-denials             # Watch for access denials
  $0 --interval 10 --follow      # Slower refresh rate
EOF
}

# Main execution
main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --interval)
                INTERVAL="$2"
                shift 2
                ;;
            --follow)
                FOLLOW_MODE=true
                shift
                ;;
            --audit-only)
                AUDIT_ONLY=true
                shift
                ;;
            --stats-only)
                STATS_ONLY=true
                shift
                ;;
            --watch-denials)
                WATCH_DENIALS=true
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

    # Check if backend is accessible
    if ! python3 -c "import backend.services.feature_flags" 2>/dev/null; then
        log_error "Cannot import backend modules"
        log_info "Make sure you're in the project directory and venv is activated"
        exit 1
    fi

    # Show dashboard
    if [ "$FOLLOW_MODE" = true ]; then
        # Continuous monitoring
        while true; do
            show_dashboard
            sleep "$INTERVAL"
        done
    else
        # Single display
        show_dashboard
    fi
}

main "$@"
