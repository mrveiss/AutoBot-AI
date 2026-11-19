#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# AutoBot Native VM Deployment Script
# Deploys AutoBot services natively on VMs (no Docker containers)
#

set -euo pipefail

# #13149: this defaulted to the deployed install, so running it from a checkout
# read or wrote the LIVE install instead of this tree. The shared helper resolves
# the root from this file's own location; AUTOBOT_PROJECT_ROOT still overrides.
# shellcheck source=scripts/lib/project_root.sh
source "$(dirname "${BASH_SOURCE[0]}")/../../scripts/lib/project_root.sh"

# Load unified configuration system
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/autobot-infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true; : "${AUTOBOT_AI_STACK_PORT:?ssot-config.sh not loaded — AUTOBOT_AI_STACK_PORT unset}"
CONFIG_SCRIPT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
if [[ -f "${CONFIG_SCRIPT_DIR}/config/load_config.sh" ]]; then
    export PATH="$HOME/bin:$PATH"  # Ensure yq is available
    source "${CONFIG_SCRIPT_DIR}/config/load_config.sh"
    echo -e "\033[0;32m✓ Loaded unified configuration system\033[0m"
else
    echo -e "\033[0;31m✗ Warning: Unified configuration not found, using fallback values\033[0m"
fi

# Configuration
INVENTORY_FILE="$SCRIPT_DIR/inventory/production.yml"
PLAYBOOK_FILE="$SCRIPT_DIR/playbooks/deploy-native-services.yml"
LOG_DIR="/tmp/autobot-native-deployment"
LOG_FILE="$LOG_DIR/native-deployment-$(date +%Y%m%d-%H%M%S).log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Create log directory
mkdir -p "$LOG_DIR"

# Logging + preflight helpers (log, error_exit, success, check_prerequisites, test_connectivity)
# shellcheck source=scripts/lib/deploy-common.sh
source "$(dirname "${BASH_SOURCE[0]}")/../../scripts/lib/deploy-common.sh"

# Show deployment plan
show_deployment_plan() {
    log "INFO" "🚀 AutoBot Native Deployment Plan:"
    log "INFO" ""
    log "INFO" "VM1 (${AUTOBOT_FRONTEND_HOST:-localhost}) - autobot-frontend:"
    log "INFO" "  • Node.js 18.x runtime"
    log "INFO" "  • Vue.js Frontend application"
    log "INFO" "  • Nginx reverse proxy (port 80/443)"
    log "INFO" "  • SystemD service: autobot-frontend"
    log "INFO" ""
    log "INFO" "WSL (${AUTOBOT_BACKEND_HOST:-localhost}) - autobot-backend:"
    log "INFO" "  • FastAPI backend service (port 8001)"
    log "INFO" "  • Terminal service (ttyd) on port 7681"
    log "INFO" "  • noVNC service on port 6080"
    log "INFO" "  • Connects to services on VMs"
    log "INFO" ""
    log "INFO" "VM2 (${AUTOBOT_NPU_WORKER_HOST:-localhost}) - autobot-npu:"
    log "INFO" "  • NPU Worker service (port 8081)"
    log "INFO" "  • OpenVINO runtime with NPU + GPU access"
    log "INFO" "  • Hardware passthrough for AI acceleration"
    log "INFO" "  • SystemD service: autobot-npu-worker"
    log "INFO" ""
    log "INFO" "VM3 (${AUTOBOT_REDIS_HOST:-localhost}) - autobot-database:"
    log "INFO" "  • Redis Stack 7.4 (native installation)"
    log "INFO" "  • RedisInsight web UI (port 8002)"
    log "INFO" "  • SystemD service: redis-stack-server"
    log "INFO" ""
    log "INFO" "VM4 (${AUTOBOT_AI_STACK_HOST:-localhost}) - autobot-aistack:"
    log "INFO" "  • Python 3.11 runtime environment"
    log "INFO" "  • AI Stack service (port ${AUTOBOT_AI_STACK_PORT})"
    log "INFO" "  • Ollama LLM server (port 11434)"
    log "INFO" "  • SystemD services: autobot-ai-stack, ollama"
    log "INFO" ""
    log "INFO" "VM5 (${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}) - autobot-browser:"
    log "INFO" "  • Node.js runtime for Playwright"
    log "INFO" "  • Browser service (port ${AUTOBOT_BROWSER_SERVICE_PORT})"
    log "INFO" "  • VNC server for desktop access (port 5900)"
    log "INFO" "  • SystemD services: autobot-browser, autobot-vnc"
    log "INFO" ""
}

# Deploy native services to VMs
deploy_native_services() {
    log "INFO" "🔄 Deploying native services to VMs..."

    # Run the native deployment playbook
    if ansible-playbook -i "$INVENTORY_FILE" "$PLAYBOOK_FILE" --ask-pass -v; then
        success "Native deployment completed successfully"
    else
        error_exit "Native deployment failed"
    fi
}

# Update local backend configuration
update_backend_config() {
    log "INFO" "🔧 Updating backend configuration for VM connections..."

    # Create environment file for backend with VM endpoints
    local env_file="${PROJECT_ROOT}/.env.native"

    # #16686: the Redis credential is the SLM-generated one -- the file roles read through
    # _shared/tasks/read_redis_password.yml -- never a literal; its username goes with it (#16668).
    local slm_secrets=/etc/autobot/slm-secrets.env
    local redis_password="${AUTOBOT_REDIS_PASSWORD:-}" redis_username="${AUTOBOT_REDIS_USERNAME:-}"
    if [ -z "$redis_password" ] && [ -r "$slm_secrets" ]; then
        # `|| true`: under pipefail a missing key would abort the deploy (as read_redis_password.yml guards)
        redis_password=$(grep -oP '^AUTOBOT_REDIS_PASSWORD=\K.*' "$slm_secrets" | head -n1 || true)
        redis_username=${redis_username:-$(grep -oP '^AUTOBOT_REDIS_USERNAME=\K.*' "$slm_secrets" | head -n1 || true)}
    fi
    if [ -n "$redis_password" ]; then redis_username=${redis_username:-default}; fi

    cat > "$env_file" << EOF
# AutoBot Native Configuration - Backend on Host, Services on VMs
# Generated: $(date)

# Backend Configuration (stays on host)
AUTOBOT_BACKEND_HOST=127.0.0.1
AUTOBOT_BACKEND_PORT=8001

# VM Service Endpoints - NATIVE DEPLOYMENT
AUTOBOT_REDIS_HOST=${AUTOBOT_REDIS_HOST:-localhost}
AUTOBOT_REDIS_PORT=6379
AUTOBOT_REDIS_PASSWORD=${redis_password}
AUTOBOT_REDIS_USERNAME=${redis_username}

AUTOBOT_AI_STACK_HOST=${AUTOBOT_AI_STACK_HOST:-localhost}
AUTOBOT_AI_STACK_PORT=${AUTOBOT_AI_STACK_PORT}

AUTOBOT_NPU_WORKER_HOST=${AUTOBOT_AI_STACK_HOST:-localhost}
AUTOBOT_NPU_WORKER_PORT=8081

AUTOBOT_OLLAMA_HOST=${AUTOBOT_AI_STACK_HOST:-localhost}
AUTOBOT_OLLAMA_PORT=11434

AUTOBOT_BROWSER_SERVICE_HOST=${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}
AUTOBOT_BROWSER_SERVICE_PORT=${AUTOBOT_BROWSER_SERVICE_PORT}

AUTOBOT_FRONTEND_HOST=${AUTOBOT_FRONTEND_HOST:-localhost}
# nginx serves the UI (#19326): the URL is the HTTP port below, not the Vite port
AUTOBOT_FRONTEND_SERVED_BY=nginx
AUTOBOT_FRONTEND_HTTP_PORT=${AUTOBOT_FRONTEND_HTTP_PORT}

# Deployment mode
AUTOBOT_DEPLOYMENT_MODE=native
AUTOBOT_USE_CONTAINERS=false

# Redis database numbers: redis-databases.yaml (#19232). Set AUTOBOT_REDIS_DB_<NAME> only
# where this deployment differs; a copy of the whole table here is a second source.
EOF

    success "Backend configuration updated: $env_file"
    log "INFO" "To use this config, run: export AUTOBOT_ENV_FILE=$env_file"
}

# Validate native deployment
validate_deployment() {
    log "INFO" "✅ Validating native deployment..."

    # Test VM services
    local services=(
        "${AUTOBOT_FRONTEND_HOST:-localhost}:80|Frontend"
        "${AUTOBOT_REDIS_HOST:-localhost}:6379|Redis Stack"
        "${AUTOBOT_REDIS_HOST:-localhost}:8002|RedisInsight"
        "${AUTOBOT_AI_STACK_HOST:-localhost}:${AUTOBOT_AI_STACK_PORT}|AI Stack"
        "${AUTOBOT_AI_STACK_HOST:-localhost}:8081|NPU Worker"
        "${AUTOBOT_AI_STACK_HOST:-localhost}:11434|Ollama"
        "${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}:${AUTOBOT_BROWSER_SERVICE_PORT}|Browser Service"
    )

    local failed_services=()

    for service in "${services[@]}"; do
        local endpoint="${service%%|*}"
        local name="${service##*|}"
        local host="${endpoint%%:*}"
        local port="${endpoint##*:}"

        log "INFO" "Testing $name at $host:$port..."

        if nc -z -w5 "$host" "$port"; then
            success "$name is responding"
        else
            log "ERROR" "$name is not responding"
            failed_services+=("$name")
        fi
    done

    # Test backend connectivity to VM services
    log "INFO" "Testing backend connectivity to VM services..."

    # Test Redis connection
    if python3 -c "
import redis
import os
try:
    r = redis.Redis(host='${AUTOBOT_REDIS_HOST:-localhost}', port=6379, password=os.environ.get('REDIS_PASSWORD', os.environ.get('AUTOBOT_REDIS_PASSWORD', '')), decode_responses=True)
    r.ping()
    print('✅ Backend can connect to VM Redis')
except Exception as e:
    print(f'❌ Backend cannot connect to VM Redis: {e}')
    exit(1)
"; then
        success "Backend → VM Redis connection verified"
    else
        failed_services+=("Backend → Redis connection")
    fi

    if [[ ${#failed_services[@]} -eq 0 ]]; then
        success "All services are running and accessible!"
    else
        log "ERROR" "Failed services: ${failed_services[*]}"
        return 1
    fi
}

# Show deployment summary
show_summary() {
    log "INFO" "🎉 AutoBot Native Deployment Complete!"
    log "INFO" ""
    log "INFO" "🌐 PRIMARY ACCESS POINT:"
    log "INFO" "  AutoBot App:  http://${AUTOBOT_FRONTEND_HOST:-localhost}"
    log "INFO" ""
    log "INFO" "📡 Service Endpoints:"
    log "INFO" "  Frontend:     http://${AUTOBOT_FRONTEND_HOST:-localhost} (PRIMARY APP ACCESS)"
    log "INFO" "  Backend:      http://${AUTOBOT_BACKEND_HOST:-localhost}:8001 (WSL)"
    log "INFO" "  NPU Worker:   http://${AUTOBOT_NPU_WORKER_HOST:-localhost}:8081"
    log "INFO" "  Redis:        redis://${AUTOBOT_REDIS_HOST:-localhost}:6379"
    log "INFO" "  RedisInsight: http://${AUTOBOT_REDIS_HOST:-localhost}:8002"
    log "INFO" "  AI Stack:     http://${AUTOBOT_AI_STACK_HOST:-localhost}:${AUTOBOT_AI_STACK_PORT}"
    log "INFO" "  Ollama:       http://${AUTOBOT_AI_STACK_HOST:-localhost}:11434"
    log "INFO" "  Browser:      http://${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}:${AUTOBOT_BROWSER_SERVICE_PORT}"
    log "INFO" ""
    log "INFO" "🖥️  Management Access:"
    log "INFO" "  Terminal:     http://${AUTOBOT_BACKEND_HOST:-localhost}:7681 (WSL)"
    log "INFO" "  noVNC:        http://${AUTOBOT_BACKEND_HOST:-localhost}:6080 (WSL)"
    log "INFO" "  VNC:          vnc://${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}:5900 (Browser VM)"
    log "INFO" ""
    log "INFO" "💻 SystemD Services:"
    log "INFO" "  WSL (${AUTOBOT_BACKEND_HOST:-localhost}): autobot-backend, ttyd, tigervnc"
    log "INFO" "  VM1 (${AUTOBOT_FRONTEND_HOST:-localhost}): autobot-frontend, nginx"
    log "INFO" "  VM2 (${AUTOBOT_NPU_WORKER_HOST:-localhost}): autobot-npu-worker"
    log "INFO" "  VM3 (${AUTOBOT_REDIS_HOST:-localhost}): redis-stack-server"
    log "INFO" "  VM4 (${AUTOBOT_AI_STACK_HOST:-localhost}): autobot-ai-stack, ollama"
    log "INFO" "  VM5 (${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}): autobot-browser, autobot-vnc"
    log "INFO" ""
    log "INFO" "🚀 Next Steps:"
    log "INFO" "  1. Update backend environment: export AUTOBOT_ENV_FILE=${PROJECT_ROOT}/.env.native"
    log "INFO" "  2. Start backend on WSL: python backend/main.py"
    log "INFO" "  3. Access AutoBot: http://${AUTOBOT_FRONTEND_HOST:-localhost}"
    log "INFO" ""
    log "INFO" "🎯 PRIMARY APP ACCESS: http://${AUTOBOT_FRONTEND_HOST:-localhost}"
    log "INFO" ""
    log "INFO" "Log file: $LOG_FILE"
}

# Usage information
show_usage() {
    cat << EOF
AutoBot Native VM Deployment Script

Usage: $0 [OPTIONS]

Options:
    --plan              Show deployment plan
    --deploy            Deploy native services to VMs
    --validate          Validate deployment
    --full              Complete native deployment (deploy + validate)
    --setup-vms         Setup VM hostnames and LVM expansion
    --help              Show this help message

Examples:
    $0 --plan           # Show what will be deployed
    $0 --full           # Complete native deployment
    $0 --validate       # Check if services are running

EOF
}

# Main execution
main() {
    local start_time=$(date +%s)

    log "INFO" "🤖 AutoBot Native VM Deployment Starting..."
    log "INFO" "Timestamp: $(date)"
    log "INFO" "Log file: $LOG_FILE"

    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi

    case $1 in
        --plan)
            check_prerequisites
            show_deployment_plan
            ;;
        --setup-vms)
            check_prerequisites
            test_connectivity
            ansible-playbook -i "$INVENTORY_FILE" "$SCRIPT_DIR/playbooks/setup-vm-names-and-lvm.yml" --ask-pass -v
            ;;
        --deploy)
            check_prerequisites
            test_connectivity
            deploy_native_services
            update_backend_config
            ;;
        --validate)
            validate_deployment
            ;;
        --full)
            check_prerequisites
            test_connectivity
            show_deployment_plan
            log "INFO" "Press Enter to continue with native deployment..."
            read
            deploy_native_services
            update_backend_config
            validate_deployment
            show_summary
            ;;
        --help|-h)
            show_usage
            ;;
        *)
            log "ERROR" "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    log "INFO" "Deployment completed in ${duration} seconds"
}

# Run main function with all arguments
main "$@"
