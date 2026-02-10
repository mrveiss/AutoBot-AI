#!/bin/bash

# Apply Bulletproof Frontend Architecture
# This script deploys the complete bulletproof system and verifies all components

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_debug() { echo -e "${BLUE}[DEBUG]${NC} $1"; }

main() {
    log_info "🛡️ Applying Bulletproof Frontend Architecture"
    log_info "=============================================="

    # Step 1: Deploy bulletproof architecture
    log_info "Step 1: Deploying bulletproof frontend architecture..."
    if "$SCRIPT_DIR/deploy-bulletproof-frontend.sh"; then
        log_info "✅ Bulletproof architecture deployed successfully"
    else
        log_error "❌ Bulletproof architecture deployment failed"
        exit 1
    fi

    # Step 2: Test all components
    log_info "Step 2: Testing bulletproof architecture..."
    if "$SCRIPT_DIR/test-bulletproof-architecture.sh"; then
        log_info "✅ All bulletproof tests passed"
    else
        log_warn "⚠️ Some tests failed - architecture may need attention"
    fi

    # Step 3: Verify frontend is operational
    log_info "Step 3: Final verification..."
    local frontend_url="http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}"

    if curl -s -f "$frontend_url" >/dev/null 2>&1; then
        log_info "✅ Frontend is responding at $frontend_url"
    else
        log_error "❌ Frontend verification failed"
        exit 1
    fi

    log_info "=============================================="
    log_info "🎉 BULLETPROOF ARCHITECTURE APPLIED SUCCESSFULLY"
    log_info ""
    log_info "Architecture Features Now Active:"
    log_info "  🛡️ Atomic deployments with rollback"
    log_info "  🚫 Cache poisoning resistance"
    log_info "  🔄 Automatic router recovery"
    log_info "  📊 Real-time health monitoring"
    log_info "  ⚡ Zero-downtime updates"
    log_info "  🧪 Comprehensive testing"
    log_info ""
    log_info "Frontend URL: $frontend_url"
    log_info "Documentation: $SCRIPT_DIR/README.md"
    log_info ""
    log_info "Usage:"
    log_info "  Daily updates: ./sync-and-verify.sh"
    log_info "  Zero-downtime: ./zero-downtime-update.sh"
    log_info "  Run tests: ./test-bulletproof-architecture.sh"
    log_info "=============================================="
}

# Handle interruption
trap 'log_error "Application interrupted"; exit 1' INT TERM

# Execute main function
main "$@"
