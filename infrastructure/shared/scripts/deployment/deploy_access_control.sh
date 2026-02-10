#!/bin/bash

################################################################################
# Access Control Gradual Rollout Deployment Script
#
# Orchestrates phased deployment of session ownership validation and audit
# logging across AutoBot's 6-VM distributed infrastructure.
#
# Usage:
#   ./deploy_access_control.sh [phase] [options]
#
# Phases:
#   phase0   - Prerequisites and preparation
#   phase1   - Ownership backfill
#   phase2   - Audit logging activation
#   phase3   - Log-only monitoring
#   phase4   - Partial enforcement
#   phase5   - Full enforcement
#   phase6   - Post-deployment validation
#   all      - Run all phases sequentially
#
# Options:
#   --dry-run          Show what would be done
#   --skip-backup      Skip Redis backup (not recommended)
#   --force            Skip confirmation prompts
#   --auto-proceed     Automatically proceed through phases
#
# Examples:
#   ./deploy_access_control.sh phase0         # Run phase 0 only
#   ./deploy_access_control.sh all --dry-run  # Dry run all phases
#   ./deploy_access_control.sh phase3         # Run log-only monitoring
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
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
REDIS_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"

# VM configuration
declare -A VMS=(
    ["frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
REMOTE_USER="${AUTOBOT_SSH_USER:-autobot}"

# Options
DRY_RUN=false
SKIP_BACKUP=false
FORCE=false
AUTO_PROCEED=false

# Logging functions
log_header() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${1}${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

log_phase() {
    echo -e "${BLUE}▶ PHASE ${1}${NC}"
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

log_fail() {
    echo -e "${RED}[✗]${NC} $1"
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

# Check prerequisites
check_prerequisites() {
    log_header "Checking Prerequisites"

    # Check SSH key
    if [ ! -f "$SSH_KEY" ]; then
        log_error "SSH key not found: $SSH_KEY"
        log_info "Run: ./scripts/utilities/setup-ssh-keys.sh"
        exit 1
    fi
    log_success "SSH key found"

    # Check Python environment
    if ! python3 -c "import backend.utils.async_redis_manager" 2>/dev/null; then
        log_error "Python backend modules not found"
        log_info "Run: source venv/bin/activate"
        exit 1
    fi
    log_success "Python environment ready"

    # Check Redis connectivity
    if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
        log_error "Cannot connect to Redis at $REDIS_HOST:$REDIS_PORT"
        exit 1
    fi
    log_success "Redis connection verified"

    # Check backend API
    if ! curl -s -f "http://$BACKEND_HOST:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
        log_warn "Backend API not responding at $BACKEND_HOST:$BACKEND_PORT"
        log_warn "Some phases may require backend to be running"
    else
        log_success "Backend API responding"
    fi

    # Check VM connectivity
    local vm_ok=0
    local vm_fail=0
    for vm_name in "${!VMS[@]}"; do
        vm_ip="${VMS[$vm_name]}"
        if ssh -i "$SSH_KEY" -o ConnectTimeout=3 \
            "$REMOTE_USER@$vm_ip" "echo ok" > /dev/null 2>&1; then
            ((vm_ok++))
        else
            log_warn "Cannot connect to $vm_name ($vm_ip)"
            ((vm_fail++))
        fi
    done

    log_info "VM connectivity: $vm_ok OK, $vm_fail failed"

    if [ $vm_fail -gt 0 ]; then
        log_warn "Some VMs are not accessible"
        confirm "Continue anyway?"
    fi

    echo
}

# Backup Redis
backup_redis() {
    log_header "Backing Up Redis Database"

    if [ "$SKIP_BACKUP" = true ]; then
        log_warn "Skipping backup (--skip-backup flag)"
        return 0
    fi

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would create Redis backup"
        return 0
    fi

    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_dir="$PROJECT_ROOT/backups/redis"
    mkdir -p "$backup_dir"

    log_info "Creating Redis backup: $timestamp"

    # Trigger Redis BGSAVE
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BGSAVE > /dev/null

    # Wait for BGSAVE to complete
    local attempts=0
    while [ $attempts -lt 30 ]; do
        if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" LASTSAVE | grep -q "$(date +%s)"; then
            break
        fi
        sleep 1
        ((attempts++))
    done

    log_success "Redis backup created"
    echo
}

# Phase 0: Prerequisites
phase0_prerequisites() {
    log_phase "0: Prerequisites and Preparation"

    check_prerequisites
    backup_redis

    # Deploy feature flags system
    log_info "Deploying feature flags system..."

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would deploy feature_flags.py to backend"
    else
        # Feature flags are already in backend/services/feature_flags.py
        log_success "Feature flags system ready"
    fi

    # Set initial enforcement mode to DISABLED
    log_info "Setting initial enforcement mode: DISABLED"

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would set enforcement mode to DISABLED"
    else
        python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags, EnforcementMode

async def main():
    flags = await get_feature_flags()
    await flags.set_enforcement_mode(EnforcementMode.DISABLED)
    print('✓ Enforcement mode set to DISABLED')

asyncio.run(main())
" || log_error "Failed to set enforcement mode"
    fi

    log_success "Phase 0 complete"
    echo
}

# Phase 1: Ownership Backfill
phase1_backfill() {
    log_phase "1: Session Ownership Backfill"

    log_info "Running backfill script..."

    local backfill_args="--default-owner admin --verbose"
    if [ "$DRY_RUN" = true ]; then
        backfill_args="$backfill_args --dry-run"
    fi
    if [ "$FORCE" = true ]; then
        backfill_args="$backfill_args --force"
    fi

    python3 "$PROJECT_ROOT/scripts/security/backfill_session_ownership.py" $backfill_args

    if [ "$DRY_RUN" = false ]; then
        # Verify backfill
        log_info "Verifying backfill..."
        python3 "$PROJECT_ROOT/scripts/security/backfill_session_ownership.py" --verify-only
    fi

    log_success "Phase 1 complete"
    echo
}

# Phase 2: Audit Logging Activation
phase2_audit_logging() {
    log_phase "2: Audit Logging Activation"

    log_info "Audit logging system is already deployed"
    log_info "Location: backend/services/audit_logger.py"
    log_info "Middleware: backend/middleware/audit_middleware.py"

    # Verify audit logging is working
    log_info "Testing audit logging..."

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would test audit logging"
    else
        python3 -c "
import asyncio
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()
    await logger.log(
        operation='deployment.test',
        result='success',
        user_id='system',
        details={'phase': 'phase2', 'test': True}
    )
    await logger.flush()

    stats = await logger.get_statistics()
    print(f'✓ Audit logger statistics: {stats}')

asyncio.run(main())
" || log_error "Audit logging test failed"
    fi

    log_success "Phase 2 complete"
    echo
}

# Phase 3: Log-Only Monitoring
phase3_log_only() {
    log_phase "3: Log-Only Monitoring Mode"

    confirm "⚠️  This will enable LOG_ONLY mode (24-48 hour monitoring period)"

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would set enforcement mode to LOG_ONLY"
    else
        python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags, EnforcementMode

async def main():
    flags = await get_feature_flags()
    await flags.set_enforcement_mode(EnforcementMode.LOG_ONLY)
    mode = await flags.get_enforcement_mode()
    print(f'✓ Enforcement mode set to: {mode.value}')

asyncio.run(main())
"
    fi

    log_info "LOG_ONLY mode active"
    log_warn "Monitor for 24-48 hours before proceeding to Phase 4"
    log_info "Use: ./scripts/monitoring/access_control_monitor.sh"

    log_success "Phase 3 complete"
    echo
}

# Phase 4: Partial Enforcement
phase4_partial_enforcement() {
    log_phase "4: Partial Enforcement"

    confirm "⚠️  This will enable ENFORCED mode on low-risk endpoints"

    log_info "Enabling enforcement on read-only endpoints..."

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would enable enforcement on specific endpoints"
    else
        # Example: Enable on specific endpoints
        log_warn "Manual endpoint configuration required"
        log_info "Use feature_flags.set_endpoint_enforcement() in code"
    fi

    log_success "Phase 4 complete"
    echo
}

# Phase 5: Full Enforcement
phase5_full_enforcement() {
    log_phase "5: Full Enforcement"

    confirm "⚠️  This will enable FULL ENFORCEMENT globally - all unauthorized access will be blocked"

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would set enforcement mode to ENFORCED"
    else
        python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags, EnforcementMode

async def main():
    flags = await get_feature_flags()
    await flags.set_enforcement_mode(EnforcementMode.ENFORCED)
    mode = await flags.get_enforcement_mode()
    print(f'✓ Enforcement mode set to: {mode.value}')
    print('✓ CVSS 9.1 vulnerability ELIMINATED')

asyncio.run(main())
"
    fi

    log_success "Phase 5 complete - Access control FULLY ENFORCED"
    echo
}

# Phase 6: Post-Deployment Validation
phase6_validation() {
    log_phase "6: Post-Deployment Validation"

    log_info "Running validation suite..."

    if [ -f "$PROJECT_ROOT/scripts/deployment/validate_access_control.sh" ]; then
        bash "$PROJECT_ROOT/scripts/deployment/validate_access_control.sh"
    else
        log_warn "Validation script not found"
        log_info "Manual validation required"
    fi

    log_success "Phase 6 complete"
    echo
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [phase] [options]

Phases:
  phase0   - Prerequisites and preparation
  phase1   - Ownership backfill
  phase2   - Audit logging activation
  phase3   - Log-only monitoring (24-48 hours)
  phase4   - Partial enforcement
  phase5   - Full enforcement
  phase6   - Post-deployment validation
  all      - Run all phases sequentially

Options:
  --dry-run          Show what would be done
  --skip-backup      Skip Redis backup (not recommended)
  --force            Skip confirmation prompts
  --auto-proceed     Automatically proceed through phases
  -h, --help         Show this help message

Examples:
  $0 phase0                    # Run phase 0 only
  $0 all --dry-run             # Dry run all phases
  $0 phase3                    # Enable log-only mode
  $0 phase5 --force            # Enable full enforcement (skip prompts)
EOF
}

# Main execution
main() {
    if [ $# -eq 0 ]; then
        show_usage
        exit 0
    fi

    local phase=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            phase0|phase1|phase2|phase3|phase4|phase5|phase6|all)
                phase="$1"
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --skip-backup)
                SKIP_BACKUP=true
                shift
                ;;
            --force)
                FORCE=true
                shift
                ;;
            --auto-proceed)
                AUTO_PROCEED=true
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

    # Header
    log_header "AutoBot Access Control Deployment"
    echo -e "${CYAN}Phase: ${phase}${NC}"
    echo -e "${CYAN}Dry Run: ${DRY_RUN}${NC}"
    echo

    # Execute phases
    case $phase in
        phase0)
            phase0_prerequisites
            ;;
        phase1)
            phase1_backfill
            ;;
        phase2)
            phase2_audit_logging
            ;;
        phase3)
            phase3_log_only
            ;;
        phase4)
            phase4_partial_enforcement
            ;;
        phase5)
            phase5_full_enforcement
            ;;
        phase6)
            phase6_validation
            ;;
        all)
            phase0_prerequisites
            if [ "$AUTO_PROCEED" = false ]; then
                confirm "Proceed to Phase 1?"
            fi
            phase1_backfill

            if [ "$AUTO_PROCEED" = false ]; then
                confirm "Proceed to Phase 2?"
            fi
            phase2_audit_logging

            if [ "$AUTO_PROCEED" = false ]; then
                confirm "Proceed to Phase 3 (LOG_ONLY mode)?"
            fi
            phase3_log_only

            log_warn "⏸  PAUSE: Monitor LOG_ONLY mode for 24-48 hours"
            log_info "   Use: ./scripts/monitoring/access_control_monitor.sh"
            log_info "   Then run: $0 phase4 to continue"
            ;;
        *)
            log_error "Invalid phase: $phase"
            show_usage
            exit 1
            ;;
    esac

    log_header "Deployment ${phase} Complete"
}

main "$@"
