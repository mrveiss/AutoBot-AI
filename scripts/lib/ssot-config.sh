#!/bin/bash
# =============================================================================
# AutoBot SSOT Configuration Helper for Shell Scripts
# Issue #694: Configuration Consolidation
# =============================================================================
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Single Source of Truth for shell scripts - reads from .env file.
# This mirrors src/config/ssot_config.py for Python code.
#
# Usage in other scripts:
#   # From scripts/ directory:
#   source "$(dirname "$0")/lib/ssot-config.sh"
#
#   # From scripts/subdirectory:
#   source "$(dirname "$0")/../lib/ssot-config.sh"
#
#   # Absolute path (recommended):
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || \
#       source "${SCRIPT_DIR}/lib/ssot-config.sh" 2>/dev/null || \
#       source "/home/kali/Desktop/AutoBot/scripts/lib/ssot-config.sh"
#
# This provides:
#   - Automatic .env loading from project root
#   - VM IP variables with fallbacks (matching ssot_config.py)
#   - Port configuration variables
#   - SSH configuration
#   - Common utility functions
#   - VM array for iteration
# =============================================================================

# Prevent double-sourcing
if [ -n "$_SSOT_CONFIG_LOADED" ]; then
    return 0 2>/dev/null || exit 0
fi
_SSOT_CONFIG_LOADED=1

# =============================================================================
# Project Root Discovery
# =============================================================================

_find_project_root() {
    local dir="$1"
    while [ "$dir" != "/" ]; do
        if [ -f "$dir/.env" ]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    # Fallback to expected location
    echo "/home/kali/Desktop/AutoBot"
}

# Set PROJECT_ROOT if not already set
if [ -z "$PROJECT_ROOT" ]; then
    _SSOT_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(_find_project_root "$_SSOT_SCRIPT_DIR")"
fi

# =============================================================================
# Load .env File (SSOT)
# =============================================================================

if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_ROOT/.env"
    set +a
fi

# =============================================================================
# VM Host Configuration (with fallbacks matching ssot_config.py)
# =============================================================================

# Primary host variables (AUTOBOT_ prefix - canonical names)
AUTOBOT_BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
AUTOBOT_FRONTEND_HOST="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
AUTOBOT_NPU_WORKER_HOST="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
AUTOBOT_REDIS_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
AUTOBOT_AI_STACK_HOST="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
AUTOBOT_BROWSER_SERVICE_HOST="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
AUTOBOT_OLLAMA_HOST="${AUTOBOT_OLLAMA_HOST:-127.0.0.1}"

# =============================================================================
# Port Configuration (with fallbacks matching ssot_config.py)
# =============================================================================

AUTOBOT_BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"
AUTOBOT_FRONTEND_PORT="${AUTOBOT_FRONTEND_PORT:-5173}"
AUTOBOT_REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
AUTOBOT_OLLAMA_PORT="${AUTOBOT_OLLAMA_PORT:-11434}"
AUTOBOT_VNC_PORT="${AUTOBOT_VNC_PORT:-6080}"
AUTOBOT_AI_STACK_PORT="${AUTOBOT_AI_STACK_PORT:-8080}"
AUTOBOT_NPU_WORKER_PORT="${AUTOBOT_NPU_WORKER_PORT:-8081}"
AUTOBOT_BROWSER_SERVICE_PORT="${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"

# =============================================================================
# SSH Configuration
# =============================================================================

AUTOBOT_SSH_USER="${AUTOBOT_SSH_USER:-autobot}"
AUTOBOT_SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"

# =============================================================================
# Convenience Variables (backward compatibility / shorter names)
# =============================================================================

# Host aliases for common usage patterns
MAIN_HOST="$AUTOBOT_BACKEND_HOST"
FRONTEND_HOST="$AUTOBOT_FRONTEND_HOST"
NPU_HOST="$AUTOBOT_NPU_WORKER_HOST"
REDIS_HOST="$AUTOBOT_REDIS_HOST"
AI_STACK_HOST="$AUTOBOT_AI_STACK_HOST"
BROWSER_HOST="$AUTOBOT_BROWSER_SERVICE_HOST"
OLLAMA_HOST="$AUTOBOT_OLLAMA_HOST"

# Port aliases
BACKEND_PORT="$AUTOBOT_BACKEND_PORT"
FRONTEND_PORT="$AUTOBOT_FRONTEND_PORT"
REDIS_PORT="$AUTOBOT_REDIS_PORT"
OLLAMA_PORT="$AUTOBOT_OLLAMA_PORT"
VNC_PORT="$AUTOBOT_VNC_PORT"

# =============================================================================
# VM Array for Iteration (name:ip format)
# =============================================================================

# Associative array for VM lookups
declare -A VMS=(
    ["main"]="$AUTOBOT_BACKEND_HOST"
    ["frontend"]="$AUTOBOT_FRONTEND_HOST"
    ["npu-worker"]="$AUTOBOT_NPU_WORKER_HOST"
    ["redis"]="$AUTOBOT_REDIS_HOST"
    ["ai-stack"]="$AUTOBOT_AI_STACK_HOST"
    ["browser"]="$AUTOBOT_BROWSER_SERVICE_HOST"
)

# VM with ports for service checks (name:ip:port format)
declare -A VM_SERVICES=(
    ["backend"]="$AUTOBOT_BACKEND_HOST:$AUTOBOT_BACKEND_PORT"
    ["frontend"]="$AUTOBOT_FRONTEND_HOST:$AUTOBOT_FRONTEND_PORT"
    ["npu-worker"]="$AUTOBOT_NPU_WORKER_HOST:$AUTOBOT_NPU_WORKER_PORT"
    ["redis"]="$AUTOBOT_REDIS_HOST:$AUTOBOT_REDIS_PORT"
    ["ai-stack"]="$AUTOBOT_AI_STACK_HOST:$AUTOBOT_AI_STACK_PORT"
    ["browser"]="$AUTOBOT_BROWSER_SERVICE_HOST:$AUTOBOT_BROWSER_SERVICE_PORT"
    ["ollama"]="$AUTOBOT_OLLAMA_HOST:$AUTOBOT_OLLAMA_PORT"
)

# =============================================================================
# Computed URLs (matching ssot_config.py properties)
# =============================================================================

AUTOBOT_BACKEND_URL="${AUTOBOT_BACKEND_URL:-http://${AUTOBOT_BACKEND_HOST}:${AUTOBOT_BACKEND_PORT}}"
AUTOBOT_FRONTEND_URL="${AUTOBOT_FRONTEND_URL:-http://${AUTOBOT_FRONTEND_HOST}:${AUTOBOT_FRONTEND_PORT}}"
AUTOBOT_REDIS_URL="${AUTOBOT_REDIS_URL:-redis://${AUTOBOT_REDIS_HOST}:${AUTOBOT_REDIS_PORT}}"
AUTOBOT_OLLAMA_URL="${AUTOBOT_OLLAMA_URL:-http://${AUTOBOT_OLLAMA_HOST}:${AUTOBOT_OLLAMA_PORT}}"
AUTOBOT_AI_STACK_URL="${AUTOBOT_AI_STACK_URL:-http://${AUTOBOT_AI_STACK_HOST}:${AUTOBOT_AI_STACK_PORT}}"
AUTOBOT_NPU_WORKER_URL="${AUTOBOT_NPU_WORKER_URL:-http://${AUTOBOT_NPU_WORKER_HOST}:${AUTOBOT_NPU_WORKER_PORT}}"
AUTOBOT_BROWSER_SERVICE_URL="${AUTOBOT_BROWSER_SERVICE_URL:-http://${AUTOBOT_BROWSER_SERVICE_HOST}:${AUTOBOT_BROWSER_SERVICE_PORT}}"
AUTOBOT_WS_URL="${AUTOBOT_WS_URL:-ws://${AUTOBOT_BACKEND_HOST}:${AUTOBOT_BACKEND_PORT}/ws}"

# =============================================================================
# Utility Functions
# =============================================================================

# Check if a host is reachable via TCP
# Usage: check_host <host> [port]
check_host() {
    local host="$1"
    local port="${2:-22}"
    nc -z -w 2 "$host" "$port" 2>/dev/null
}

# Check if an HTTP endpoint is healthy
# Usage: check_http_health <url> [timeout_seconds]
check_http_health() {
    local url="$1"
    local timeout="${2:-3}"
    curl -sf --max-time "$timeout" "$url" > /dev/null 2>&1
}

# Get VM IP by name
# Usage: get_vm_ip <vm_name>
get_vm_ip() {
    local vm_name="$1"
    echo "${VMS[$vm_name]:-}"
}

# Get service address (ip:port) by name
# Usage: get_service_address <service_name>
get_service_address() {
    local service_name="$1"
    echo "${VM_SERVICES[$service_name]:-}"
}

# SSH to a VM with standard options
# Usage: ssh_to_vm <vm_name> [command...]
ssh_to_vm() {
    local vm_name="$1"
    shift
    local vm_ip="${VMS[$vm_name]}"
    if [ -z "$vm_ip" ]; then
        log_error "Unknown VM: $vm_name"
        return 1
    fi
    ssh -i "$AUTOBOT_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        "$AUTOBOT_SSH_USER@$vm_ip" "$@"
}

# SCP to/from a VM
# Usage: scp_to_vm <vm_name> <local_path> <remote_path>
scp_to_vm() {
    local vm_name="$1"
    local local_path="$2"
    local remote_path="$3"
    local vm_ip="${VMS[$vm_name]}"
    if [ -z "$vm_ip" ]; then
        log_error "Unknown VM: $vm_name"
        return 1
    fi
    scp -i "$AUTOBOT_SSH_KEY" -o StrictHostKeyChecking=no \
        "$local_path" "$AUTOBOT_SSH_USER@$vm_ip:$remote_path"
}

# Rsync to a VM (preferred for directories)
# Usage: rsync_to_vm <vm_name> <local_path> <remote_path> [--delete]
rsync_to_vm() {
    local vm_name="$1"
    local local_path="$2"
    local remote_path="$3"
    local delete_flag="${4:-}"
    local vm_ip="${VMS[$vm_name]}"
    if [ -z "$vm_ip" ]; then
        log_error "Unknown VM: $vm_name"
        return 1
    fi
    local rsync_opts="-avz --progress"
    if [ "$delete_flag" = "--delete" ]; then
        rsync_opts="$rsync_opts --delete"
    fi
    # shellcheck disable=SC2086
    rsync $rsync_opts \
        -e "ssh -i $AUTOBOT_SSH_KEY -o StrictHostKeyChecking=no" \
        "$local_path" "$AUTOBOT_SSH_USER@$vm_ip:$remote_path"
}

# =============================================================================
# Logging Functions (with timestamps and colors)
# =============================================================================

# Color codes
_LOG_RED='\033[0;31m'
_LOG_GREEN='\033[0;32m'
_LOG_YELLOW='\033[1;33m'
_LOG_BLUE='\033[0;34m'
_LOG_CYAN='\033[0;36m'
_LOG_NC='\033[0m'  # No Color

log_info() {
    echo -e "${_LOG_GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${_LOG_NC} $*"
}

log_error() {
    echo -e "${_LOG_RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${_LOG_NC} $*" >&2
}

log_warn() {
    echo -e "${_LOG_YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARN:${_LOG_NC} $*"
}

log_debug() {
    if [ "${AUTOBOT_DEBUG:-false}" = "true" ]; then
        echo -e "${_LOG_CYAN}[$(date '+%Y-%m-%d %H:%M:%S')] DEBUG:${_LOG_NC} $*"
    fi
}

log_header() {
    echo -e "${_LOG_BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${_LOG_NC} $*"
}

# =============================================================================
# Health Check Functions
# =============================================================================

# Check all VMs are reachable via SSH
# Returns: 0 if all reachable, 1 otherwise
check_all_vms() {
    local all_ok=0
    for vm_name in "${!VMS[@]}"; do
        local vm_ip="${VMS[$vm_name]}"
        if check_host "$vm_ip" 22; then
            log_info "$vm_name ($vm_ip): SSH reachable"
        else
            log_error "$vm_name ($vm_ip): SSH not reachable"
            all_ok=1
        fi
    done
    return $all_ok
}

# Check all services are responding
# Returns: 0 if all healthy, 1 otherwise
check_all_services() {
    local all_ok=0
    for service_name in "${!VM_SERVICES[@]}"; do
        IFS=':' read -r host port <<< "${VM_SERVICES[$service_name]}"
        if check_host "$host" "$port"; then
            log_info "$service_name ($host:$port): Port open"
        else
            log_error "$service_name ($host:$port): Port not responding"
            all_ok=1
        fi
    done
    return $all_ok
}

# =============================================================================
# Export All Variables
# =============================================================================

export PROJECT_ROOT

# Host exports
export AUTOBOT_BACKEND_HOST AUTOBOT_FRONTEND_HOST AUTOBOT_NPU_WORKER_HOST
export AUTOBOT_REDIS_HOST AUTOBOT_AI_STACK_HOST AUTOBOT_BROWSER_SERVICE_HOST
export AUTOBOT_OLLAMA_HOST

# Port exports
export AUTOBOT_BACKEND_PORT AUTOBOT_FRONTEND_PORT AUTOBOT_REDIS_PORT
export AUTOBOT_OLLAMA_PORT AUTOBOT_VNC_PORT AUTOBOT_AI_STACK_PORT
export AUTOBOT_NPU_WORKER_PORT AUTOBOT_BROWSER_SERVICE_PORT

# SSH exports
export AUTOBOT_SSH_USER AUTOBOT_SSH_KEY

# URL exports
export AUTOBOT_BACKEND_URL AUTOBOT_FRONTEND_URL AUTOBOT_REDIS_URL
export AUTOBOT_OLLAMA_URL AUTOBOT_AI_STACK_URL AUTOBOT_NPU_WORKER_URL
export AUTOBOT_BROWSER_SERVICE_URL AUTOBOT_WS_URL

# Convenience exports (backward compatibility)
export MAIN_HOST FRONTEND_HOST NPU_HOST REDIS_HOST AI_STACK_HOST BROWSER_HOST
export BACKEND_PORT FRONTEND_PORT REDIS_PORT OLLAMA_PORT VNC_PORT

# =============================================================================
# Self-Test (when run directly)
# =============================================================================

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    echo "=== AutoBot SSOT Config Shell Helper ==="
    echo "Issue #694: Configuration Consolidation"
    echo ""
    echo "PROJECT_ROOT: $PROJECT_ROOT"
    echo ""
    echo "=== VM Hosts ==="
    echo "Backend (Main):  $AUTOBOT_BACKEND_HOST"
    echo "Frontend:        $AUTOBOT_FRONTEND_HOST"
    echo "NPU Worker:      $AUTOBOT_NPU_WORKER_HOST"
    echo "Redis:           $AUTOBOT_REDIS_HOST"
    echo "AI Stack:        $AUTOBOT_AI_STACK_HOST"
    echo "Browser:         $AUTOBOT_BROWSER_SERVICE_HOST"
    echo "Ollama:          $AUTOBOT_OLLAMA_HOST"
    echo ""
    echo "=== Ports ==="
    echo "Backend:  $AUTOBOT_BACKEND_PORT"
    echo "Frontend: $AUTOBOT_FRONTEND_PORT"
    echo "Redis:    $AUTOBOT_REDIS_PORT"
    echo "Ollama:   $AUTOBOT_OLLAMA_PORT"
    echo "VNC:      $AUTOBOT_VNC_PORT"
    echo ""
    echo "=== URLs ==="
    echo "Backend:  $AUTOBOT_BACKEND_URL"
    echo "Frontend: $AUTOBOT_FRONTEND_URL"
    echo "Redis:    $AUTOBOT_REDIS_URL"
    echo "Ollama:   $AUTOBOT_OLLAMA_URL"
    echo ""
    echo "=== SSH Config ==="
    echo "User: $AUTOBOT_SSH_USER"
    echo "Key:  $AUTOBOT_SSH_KEY"
    echo ""
    echo "=== VMs Array ==="
    for vm_name in "${!VMS[@]}"; do
        echo "  $vm_name: ${VMS[$vm_name]}"
    done
    echo ""
    echo "Syntax check: PASSED"
fi
