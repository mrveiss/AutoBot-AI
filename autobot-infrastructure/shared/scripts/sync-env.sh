#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# sync-env.sh - Environment File Synchronization Script
# ======================================================
#
# Generates frontend .env file from master .env file.
# Maps AUTOBOT_* variables to VITE_* variables for Vite compatibility.
#
# Usage:
#   ./scripts/sync-env.sh           # Sync from master .env
#   ./scripts/sync-env.sh --check   # Check if sync is needed
#   ./scripts/sync-env.sh --force   # Force sync even if up to date
#
# Issue: #601 - SSOT Phase 1: Foundation
# Related: #599 - SSOT Configuration System Epic

set -uo pipefail
# Note: -e not used as count=$((count + 1)) returns 1 when count is 0

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

MASTER_ENV="$PROJECT_ROOT/.env"
FRONTEND_ENV="$PROJECT_ROOT/autobot-slm-frontend/.env"
FRONTEND_DIR="$PROJECT_ROOT/autobot-slm-frontend"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if master .env exists
check_master_env() {
    if [[ ! -f "$MASTER_ENV" ]]; then
        log_error "Master .env not found at: $MASTER_ENV"
        log_info "Please copy from .env.example and configure:"
        echo "  cp $PROJECT_ROOT/.env.example $MASTER_ENV"
        exit 1
    fi
}

# Check if frontend directory exists
check_frontend_dir() {
    if [[ ! -d "$FRONTEND_DIR" ]]; then
        log_error "Frontend directory not found at: $FRONTEND_DIR"
        exit 1
    fi
}

# =============================================================================
# Main Sync Function
# =============================================================================

sync_env() {
    local force="${1:-false}"

    check_master_env
    check_frontend_dir

    # Check if sync is needed (unless force mode)
    if [[ "$force" != "true" ]] && [[ -f "$FRONTEND_ENV" ]]; then
        if [[ "$MASTER_ENV" -ot "$FRONTEND_ENV" ]]; then
            log_info "Frontend .env is up to date (newer than master .env)"
            log_info "Use --force to regenerate anyway"
            return 0
        fi
    fi

    log_info "Generating frontend .env from master .env..."

    # Create the frontend .env file
    cat > "$FRONTEND_ENV" << 'HEADER'
# AUTO-GENERATED from master .env - DO NOT EDIT DIRECTLY
# ========================================================
# Run: ./scripts/sync-env.sh to regenerate from master .env
#
# This file maps AUTOBOT_* variables to VITE_* for Vite compatibility.
# All configuration should be done in the master .env file.
#
# Issue: #601 - SSOT Configuration System
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

HEADER

    # Add generation timestamp
    echo "# Generated: $(date '+%Y-%m-%d %H:%M:%S')" >> "$FRONTEND_ENV"
    echo "" >> "$FRONTEND_ENV"

    # Process the master .env file
    local count=0

    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip empty lines and comments
        [[ -z "$line" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue

        # Extract key and value
        if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local value="${BASH_REMATCH[2]}"

            # Map AUTOBOT_* to VITE_*
            case "$key" in
                # Host mappings
                AUTOBOT_BACKEND_HOST)
                    echo "VITE_BACKEND_HOST=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_FRONTEND_HOST)
                    echo "VITE_FRONTEND_HOST=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_REDIS_HOST)
                    echo "VITE_REDIS_HOST=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_OLLAMA_HOST)
                    echo "VITE_OLLAMA_HOST=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_AI_STACK_HOST)
                    echo "VITE_AI_STACK_HOST=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_NPU_WORKER_HOST)
                    echo "VITE_NPU_WORKER_HOST=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_BROWSER_SERVICE_HOST)
                    echo "VITE_BROWSER_HOST=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;

                # Port mappings
                AUTOBOT_BACKEND_PORT)
                    echo "VITE_BACKEND_PORT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_FRONTEND_PORT)
                    echo "VITE_FRONTEND_PORT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_REDIS_PORT)
                    echo "VITE_REDIS_PORT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_OLLAMA_PORT)
                    echo "VITE_OLLAMA_PORT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_AI_STACK_PORT)
                    echo "VITE_AI_STACK_PORT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_NPU_WORKER_PORT)
                    echo "VITE_NPU_WORKER_PORT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_BROWSER_SERVICE_PORT)
                    echo "VITE_BROWSER_PORT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_VNC_PORT)
                    echo "VITE_DESKTOP_VNC_PORT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;

                # Timeout mappings
                AUTOBOT_API_TIMEOUT)
                    echo "VITE_API_TIMEOUT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_LLM_TIMEOUT)
                    echo "VITE_LLM_TIMEOUT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_API_RETRY_ATTEMPTS)
                    echo "VITE_API_RETRY_ATTEMPTS=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_API_RETRY_DELAY)
                    echo "VITE_API_RETRY_DELAY=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_WEBSOCKET_TIMEOUT)
                    echo "VITE_WEBSOCKET_TIMEOUT=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;

                # Deployment settings
                AUTOBOT_DEPLOYMENT_MODE)
                    echo "VITE_DEPLOYMENT_MODE=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_DEBUG)
                    echo "VITE_DEBUG=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_DEBUG_MODE)
                    echo "VITE_ENABLE_DEBUG=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;

                # LLM settings
                AUTOBOT_DEFAULT_LLM_MODEL)
                    echo "VITE_LLM_DEFAULT_MODEL=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
                AUTOBOT_EMBEDDING_MODEL)
                    echo "VITE_LLM_EMBEDDING_MODEL=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;

                # Variables that already have VITE_ prefix - pass through
                VITE_*)
                    echo "$key=$value" >> "$FRONTEND_ENV"
                    count=$((count + 1))
                    ;;
            esac
        fi
    done < "$MASTER_ENV"

    log_success "Frontend .env synchronized: $count variables mapped"
    log_info "Output: $FRONTEND_ENV"
}

# =============================================================================
# Check Function
# =============================================================================

check_sync() {
    check_master_env

    if [[ ! -f "$FRONTEND_ENV" ]]; then
        log_warning "Frontend .env does not exist"
        log_info "Run: ./scripts/sync-env.sh to generate"
        exit 1
    fi

    if [[ "$MASTER_ENV" -nt "$FRONTEND_ENV" ]]; then
        log_warning "Frontend .env is out of date"
        log_info "Master .env is newer than frontend .env"
        log_info "Run: ./scripts/sync-env.sh to regenerate"
        exit 1
    fi

    log_success "Frontend .env is up to date"
}

# =============================================================================
# Main Entry Point
# =============================================================================

case "${1:-}" in
    --check)
        check_sync
        ;;
    --force)
        sync_env true
        ;;
    --help|-h)
        echo "Usage: $0 [--check|--force|--help]"
        echo ""
        echo "Options:"
        echo "  (none)   Sync if master .env is newer"
        echo "  --check  Check if sync is needed (exit 1 if needed)"
        echo "  --force  Force sync even if up to date"
        echo "  --help   Show this help message"
        echo ""
        echo "This script generates autobot-slm-frontend/.env from the master .env file,"
        echo "mapping AUTOBOT_* variables to VITE_* for Vite compatibility."
        ;;
    *)
        sync_env false
        ;;
esac
