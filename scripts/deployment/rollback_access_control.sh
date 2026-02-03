#!/bin/bash

################################################################################
# Access Control Rollback Script
#
# Emergency rollback for access control enforcement.
# Restores system to DISABLED mode in < 5 minutes.
#
# Usage:
#   ./rollback_access_control.sh [options]
#
# Options:
#   --reason TEXT          Reason for rollback (required)
#   --restore-backup DATE  Restore Redis backup from specific date
#   --force                Skip confirmation
#   --no-backup            Don't create rollback backup
#
# Examples:
#   ./rollback_access_control.sh --reason "Blocking legitimate users"
#   ./rollback_access_control.sh --restore-backup 20251006_143000
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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REDIS_HOST="172.16.168.23"
REDIS_PORT="6379"

# Options
ROLLBACK_REASON=""
RESTORE_BACKUP=""
FORCE=false
NO_BACKUP=false

# Logging functions
log_header() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${1}${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
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

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Confirmation prompt
confirm() {
    if [ "$FORCE" = true ]; then
        return 0
    fi

    echo -e "${YELLOW}$1${NC}"
    read -p "Continue? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_warn "Cancelled by user"
        exit 1
    fi
}

# Record rollback event
record_rollback_event() {
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local log_file="$PROJECT_ROOT/logs/rollback_events.log"

    mkdir -p "$(dirname "$log_file")"

    cat >> "$log_file" << EOF

=== ROLLBACK EVENT ===
Timestamp: $timestamp
Reason: $ROLLBACK_REASON
Operator: $USER
Restore Backup: ${RESTORE_BACKUP:-"none"}
=====================

EOF

    log_success "Rollback event recorded"
}

# Create rollback backup
create_rollback_backup() {
    if [ "$NO_BACKUP" = true ]; then
        log_warn "Skipping rollback backup (--no-backup flag)"
        return 0
    fi

    log_step "Creating rollback backup..."

    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_dir="$PROJECT_ROOT/backups/redis"
    mkdir -p "$backup_dir"

    # Trigger Redis BGSAVE
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BGSAVE > /dev/null

    log_success "Rollback backup initiated: $timestamp"
}

# Disable enforcement
disable_enforcement() {
    log_step "Disabling access control enforcement..."

    python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags, EnforcementMode

async def main():
    flags = await get_feature_flags()

    # Get current mode
    current_mode = await flags.get_enforcement_mode()
    print(f'Current mode: {current_mode.value}')

    # Set to DISABLED
    await flags.set_enforcement_mode(EnforcementMode.DISABLED)

    # Verify
    new_mode = await flags.get_enforcement_mode()
    if new_mode == EnforcementMode.DISABLED:
        print('✓ Enforcement disabled successfully')
        return 0
    else:
        print('✗ Failed to disable enforcement')
        return 1

import sys
sys.exit(asyncio.run(main()))
" || {
        log_error "Failed to disable enforcement"
        return 1
    }

    log_success "Access control enforcement DISABLED"
}

# Clear endpoint overrides
clear_endpoint_overrides() {
    log_step "Clearing endpoint-specific enforcement overrides..."

    python3 -c "
import asyncio
from backend.utils.async_redis_manager import get_redis_manager

async def main():
    redis_manager = await get_redis_manager()
    redis = await redis_manager.temp()

    # Find all endpoint overrides
    cursor = 0
    deleted = 0
    while True:
        cursor, keys = await redis.scan(
            cursor,
            match='feature_flag:access_control:endpoint:*',
            count=100
        )
        if keys:
            deleted += await redis.delete(*keys)
        if cursor == 0:
            break

    print(f'✓ Cleared {deleted} endpoint overrides')

asyncio.run(main())
" || log_warn "Failed to clear some endpoint overrides"

    log_success "Endpoint overrides cleared"
}

# Restore Redis backup
restore_redis_backup() {
    if [ -z "$RESTORE_BACKUP" ]; then
        return 0
    fi

    log_step "Restoring Redis backup: $RESTORE_BACKUP"

    local backup_file="$PROJECT_ROOT/backups/redis/dump_${RESTORE_BACKUP}.rdb"

    if [ ! -f "$backup_file" ]; then
        log_error "Backup file not found: $backup_file"
        log_info "Available backups:"
        ls -lh "$PROJECT_ROOT/backups/redis/" 2>/dev/null || echo "  No backups found"
        return 1
    fi

    confirm "⚠️  This will OVERWRITE current Redis data with backup from $RESTORE_BACKUP"

    # Stop Redis (requires SSH to redis VM)
    log_warn "Manual Redis restore required:"
    log_info "1. SSH to Redis VM: ssh autobot@$REDIS_HOST"
    log_info "2. Stop Redis: sudo systemctl stop redis"
    log_info "3. Copy backup: $backup_file -> /var/lib/redis/dump.rdb"
    log_info "4. Start Redis: sudo systemctl start redis"

    return 0
}

# Verify rollback
verify_rollback() {
    log_step "Verifying rollback..."

    # Check enforcement mode
    local mode=$(python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    mode = await flags.get_enforcement_mode()
    print(mode.value)

asyncio.run(main())
" 2>/dev/null)

    if [ "$mode" = "disabled" ]; then
        log_success "Enforcement mode: DISABLED ✓"
    else
        log_error "Enforcement mode: $mode (expected DISABLED)"
        return 1
    fi

    # Check Redis connectivity
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
        log_success "Redis connectivity: OK ✓"
    else
        log_error "Redis connectivity: FAILED"
        return 1
    fi

    log_success "Rollback verification passed"
}

# Print rollback summary
print_summary() {
    log_header "Rollback Complete"

    echo -e "${GREEN}✓ Access control enforcement has been DISABLED${NC}"
    echo -e "${GREEN}✓ System restored to safe state${NC}"
    echo
    echo -e "${CYAN}Rollback Details:${NC}"
    echo "  Reason: $ROLLBACK_REASON"
    echo "  Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  Duration: $SECONDS seconds"
    echo
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "  1. Investigate root cause of rollback"
    echo "  2. Review audit logs: ./scripts/monitoring/access_control_monitor.sh"
    echo "  3. Fix underlying issues"
    echo "  4. Test fixes in isolated environment"
    echo "  5. Re-deploy with: ./scripts/deployment/deploy_access_control.sh"
    echo
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [options]

EMERGENCY ROLLBACK - Disables access control enforcement

Options:
  --reason TEXT          Reason for rollback (REQUIRED)
  --restore-backup DATE  Restore Redis backup from specific date (YYYYMMDD_HHMMSS)
  --force                Skip confirmation prompts
  --no-backup            Don't create rollback backup before changes
  -h, --help             Show this help message

Examples:
  $0 --reason "Blocking legitimate users"
  $0 --reason "Performance issues" --force
  $0 --restore-backup 20251006_143000 --reason "Data corruption"

Available Backups:
EOF

    ls -lh "$PROJECT_ROOT/backups/redis/" 2>/dev/null | tail -n +2 || echo "  No backups found"
}

# Main execution
main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --reason)
                ROLLBACK_REASON="$2"
                shift 2
                ;;
            --restore-backup)
                RESTORE_BACKUP="$2"
                shift 2
                ;;
            --force)
                FORCE=true
                shift
                ;;
            --no-backup)
                NO_BACKUP=true
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

    # Validate required arguments
    if [ -z "$ROLLBACK_REASON" ]; then
        log_error "Rollback reason is required"
        echo
        show_usage
        exit 1
    fi

    # Header
    log_header "🚨 ACCESS CONTROL ROLLBACK 🚨"
    echo -e "${RED}WARNING: This will disable access control enforcement${NC}"
    echo -e "${YELLOW}Reason: $ROLLBACK_REASON${NC}"
    echo

    confirm "⚠️  Proceed with rollback?"

    # Start timer
    SECONDS=0

    # Execute rollback steps
    create_rollback_backup
    restore_redis_backup
    disable_enforcement
    clear_endpoint_overrides
    record_rollback_event
    verify_rollback

    # Summary
    print_summary
}

main "$@"
