#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0

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

# Import roots for the inline Python below, derived from this script's own
# location. `services.*`/`security.*` live under autobot-backend and
# `autobot_shared.*` at the repo root; without both, every block below fails and
# falls through to its fabricated default (#14866).
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
export PYTHONPATH="${REPO_ROOT}/autobot-backend:${REPO_ROOT}:${PYTHONPATH:-}"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../lib/ssot-config.sh" || {
    echo "FATAL: ${SCRIPT_DIR}/../lib/ssot-config.sh could not be sourced -- refusing to run on hardcoded config fallbacks (#14172)" >&2
    return 1 2>/dev/null || exit 1
}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Configuration
REDIS_HOST="${AUTOBOT_REDIS_HOST:-localhost}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-localhost}"
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

# Checks that could not run during the current dashboard render.
#
# #14880: every getter below used to answer a failed check with a literal that
# impersonates a measurement -- "UNKNOWN", "{}", "0|0|0". Removing the stderr
# suppression (#14868) made the failure visible in a log; it did not make the
# reported VALUE distinguishable from a real one, so anything reading "{}" still
# saw "no findings" rather than "the check did not execute". The getters now
# print nothing and return non-zero, which forces each consumer to decide what
# to report, and this counter carries that decision into the exit status.
CHECK_FAILURES=0

record_check_failure() {
    CHECK_FAILURES=$((CHECK_FAILURES + 1))
    log_error "$1 could not be checked -- no value is reported for it below"
}

# Get current enforcement mode. Prints nothing and returns non-zero if the
# check could not run (#14880).
get_enforcement_mode() {
    python3 -c "
import asyncio
from services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    mode = await flags.get_enforcement_mode()
    print(mode.value.upper())

asyncio.run(main())
"
}

# Get rollout statistics. Prints nothing and returns non-zero on failure.
get_rollout_stats() {
    python3 -c "
import asyncio
import json
from services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    stats = await flags.get_rollout_statistics()
    print(json.dumps(stats, indent=2))

asyncio.run(main())
"
}

# Get audit statistics. Prints nothing and returns non-zero on failure.
get_audit_stats() {
    python3 -c "
import asyncio
import json
from services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()
    stats = await logger.get_statistics()
    print(json.dumps(stats, indent=2))

asyncio.run(main())
"
}

# Get recent denied access attempts
get_recent_denials() {
    python3 -c "
import asyncio
import json
from datetime import datetime, timedelta
from services.audit_logger import get_audit_logger

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
"
}

# Get session ownership coverage
get_ownership_coverage() {
    python3 -c "
import asyncio
from autobot_shared.redis_client import get_redis_client as get_redis_manager
from security.session_ownership import SessionOwnershipValidator

async def main():
    # Exactly what security/session_ownership.py:836 does. Calling it bare
    # returns the SYNC client (async_client defaults to False), so awaiting it
    # raises TypeError, and a .main() attribute exists on neither client. That
    # turned an import-time failure into a call-time one, which is the same
    # defect a step later (#14866). Written without backticks on purpose: this
    # block is a DOUBLE-QUOTED shell argument, so a backtick is command
    # substitution -- bash ran the words inside it and handed python a mangled
    # program, which no amount of import fixing could have made work (#14880).
    redis = await get_redis_manager(async_client=True, database="main")

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
"
}

# Display dashboard
show_dashboard() {
    clear

    log_header "Access Control Monitoring Dashboard - $(date '+%Y-%m-%d %H:%M:%S')"

    # Current enforcement mode. `mode` carries CHECK_FAILED only when the check
    # itself did not run — that is a different statement from any mode the
    # feature flags can report, and it must never be one of them (#14880).
    log_section "Enforcement Status"
    local mode
    if ! mode=$(get_enforcement_mode); then
        record_check_failure "Enforcement mode"
        mode="CHECK_FAILED"
    fi

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
        CHECK_FAILED)
            echo -e "  Mode: ${RED}CHECK FAILED${NC} (the check did not run — this is not a mode)"
            ;;
        *)
            echo -e "  Mode: ${MAGENTA}UNRECOGNISED${NC} (${mode})"
            ;;
    esac
    echo

    # Ownership coverage
    if [ "$AUDIT_ONLY" = false ]; then
        log_section "Session Ownership Coverage"
        local coverage
        if coverage=$(get_ownership_coverage); then
            IFS='|' read -r total owned percent <<< "$coverage"

            log_metric "Total Sessions" "$total"
            log_metric "Owned Sessions" "$owned"
            log_metric "Coverage" "${percent}%"

            if [ "$percent" = "100.0" ]; then
                echo -e "  ${GREEN}✓ Full ownership coverage${NC}"
            else
                echo -e "  ${YELLOW}⚠ Incomplete ownership coverage${NC}"
            fi
        else
            record_check_failure "Session ownership coverage"
            echo -e "  ${RED}✗ Coverage not measured${NC} (no sessions were counted — this is not zero coverage)"
        fi
        echo
    fi

    # Rollout statistics
    if [ "$AUDIT_ONLY" = false ] && [ "$STATS_ONLY" = false ]; then
        log_section "Rollout Statistics"
        local rollout_stats
        if ! rollout_stats=$(get_rollout_stats); then
            record_check_failure "Rollout statistics"
            echo -e "  ${RED}✗ Rollout statistics not read${NC} (no overrides or mode changes are reported)"
        elif ! echo "$rollout_stats" | python3 -c "
import sys, json

# Exits non-zero rather than printing a line and returning 0: the caller's
# record_check_failure is what makes an unreadable payload visible in the exit
# status, and a swallowed parse error would report zeros instead (#14880).
try:
    data = json.load(sys.stdin)
except Exception as exc:
    print(f'rollout statistics are not readable JSON: {exc}', file=sys.stderr)
    sys.exit(1)
print(f'  Current Mode:         {data.get(\"current_mode\", \"unknown\").upper()}')
print(f'  Endpoint Overrides:   {data.get(\"total_endpoints_configured\", 0)}')
print(f'  Mode Changes:         {len(data.get(\"history\", []))}')
"; then
            record_check_failure "Rollout statistics (unreadable payload)"
        fi
        echo
    fi

    # Audit statistics
    if [ "$STATS_ONLY" = false ]; then
        log_section "Audit Logging Statistics"
        local audit_stats
        if ! audit_stats=$(get_audit_stats); then
            record_check_failure "Audit logging statistics"
            echo -e "  ${RED}✗ Audit statistics not read${NC} (no counts are reported — this is not zero failures)"
        elif ! echo "$audit_stats" | python3 -c "
import sys, json

try:
    data = json.load(sys.stdin)
except Exception as exc:
    print(f'audit statistics are not readable JSON: {exc}', file=sys.stderr)
    sys.exit(1)
print(f'  Total Logged:         {data.get(\"total_logged\", 0)}')
print(f'  Failed:               {data.get(\"total_failed\", 0)}')
print(f'  Redis Failures:       {data.get(\"redis_failures\", 0)}')
print(f'  Queue Size:           {data.get(\"batch_queue_size\", 0)}')
print(f'  Last 24h Entries:     {data.get(\"entries_last_24h\", \"N/A\")}')
redis_status = 'UP' if data.get('redis_available') else 'DOWN'
color = '\033[0;32m' if data.get('redis_available') else '\033[0;31m'
print(f'  Redis Status:         {color}{redis_status}\033[0m')
"; then
            record_check_failure "Audit logging statistics (unreadable payload)"
        fi
        echo
    fi

    # Recent denied access attempts
    if [ "$WATCH_DENIALS" = true ] || [ "$mode" = "ENFORCED" ]; then
        log_section "Recent Denied Access Attempts (Last Hour)"
        # An empty result and a failed query print the same thing unless they
        # are separated here: "no denials" is the single most reassuring line
        # this dashboard emits, and it is exactly what a broken query produced
        # (#14880).
        local denials
        if ! denials=$(get_recent_denials); then
            record_check_failure "Recent denied access attempts"
            echo -e "  ${RED}✗ Denial query failed${NC} (absence of denials cannot be concluded from this)"
        elif [ -z "$denials" ]; then
            echo -e "  ${GREEN}✓ No denied access attempts${NC}"
        else
            echo "$denials" | head -10
        fi
        echo
    fi

    # Backend health
    if [ "$AUDIT_ONLY" = false ]; then
        log_section "Backend Health"
        # A missing probe binary is not a down service. Without this branch an
        # absent curl or redis-cli reports both as DOWN, which is the same
        # defect pointing the other way — a value that did not come from a
        # measurement (#14880).
        if ! command -v curl > /dev/null 2>&1; then
            record_check_failure "Backend API health (curl is not installed)"
            echo -e "  Backend API: ${MAGENTA}UNCHECKED${NC} (curl unavailable)"
        elif curl -s -f "http://$BACKEND_HOST:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
            echo -e "  Backend API: ${GREEN}UP${NC} ($BACKEND_HOST:$BACKEND_PORT)"
        else
            echo -e "  Backend API: ${RED}DOWN${NC} ($BACKEND_HOST:$BACKEND_PORT)"
        fi

        if ! command -v redis-cli > /dev/null 2>&1; then
            record_check_failure "Redis reachability (redis-cli is not installed)"
            echo -e "  Redis:       ${MAGENTA}UNCHECKED${NC} (redis-cli unavailable)"
        elif redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
            echo -e "  Redis:       ${GREEN}UP${NC} ($REDIS_HOST:$REDIS_PORT)"
        else
            echo -e "  Redis:       ${RED}DOWN${NC} ($REDIS_HOST:$REDIS_PORT)"
        fi
        echo
    fi

    # The dashboard's own verdict on itself. Printed last so it is the line an
    # operator leaves with, and mirrored into the exit status by main().
    if [ "$CHECK_FAILURES" -gt 0 ]; then
        log_error "${CHECK_FAILURES} check(s) did not run — this dashboard is INCOMPLETE, not clean"
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

    # Check if backend is accessible. `backend.services.feature_flags` names a
    # package that has never existed in this repo, so this pre-flight failed on
    # every run and the dashboard below was never reached — the same #14866
    # defect as the getters, one step earlier. The importable name is
    # `services.feature_flags`, reachable through the PYTHONPATH exported at the
    # top of this script. stderr is deliberately not suppressed, so a failure
    # says why (#14868).
    if ! python3 -c "import services.feature_flags"; then
        log_error "Cannot import services.feature_flags"
        log_info "PYTHONPATH must cover the backend directory and the repo root"
        exit 1
    fi

    # Show dashboard
    if [ "$FOLLOW_MODE" = true ]; then
        # Continuous monitoring
        while true; do
            CHECK_FAILURES=0
            show_dashboard
            sleep "$INTERVAL"
        done
    else
        # Single display
        show_dashboard
        # #14880: a run whose checks could not execute must not exit 0. Anything
        # scraping this status would otherwise read "the monitor ran and found
        # nothing wrong" from a monitor that measured nothing.
        [ "$CHECK_FAILURES" -eq 0 ] || exit 2
    fi
}

main "$@"
