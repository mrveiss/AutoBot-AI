#!/bin/bash
#
# AutoBot Hybrid VM Deployment Script
# Deploys Docker containers to VMs while keeping backend on host
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true
INVENTORY_FILE="$SCRIPT_DIR/inventory/production.yml"
PLAYBOOK_FILE="$SCRIPT_DIR/playbooks/deploy-hybrid-docker.yml"
LOG_DIR="/tmp/autobot-deployment"
LOG_FILE="$LOG_DIR/hybrid-deployment-$(date +%Y%m%d-%H%M%S).log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Create log directory
mkdir -p "$LOG_DIR"

# Logging
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$level" in
        INFO)  echo -e "${BLUE}ℹ️ ${message}${NC}" | tee -a "$LOG_FILE" ;;
        WARN)  echo -e "${YELLOW}⚠️ ${message}${NC}" | tee -a "$LOG_FILE" ;;
        ERROR) echo -e "${RED}❌ ${message}${NC}" | tee -a "$LOG_FILE" ;;
        SUCCESS) echo -e "${GREEN}✅ ${message}${NC}" | tee -a "$LOG_FILE" ;;
        DEBUG) echo -e "${timestamp} [DEBUG] ${message}" >> "$LOG_FILE" ;;
    esac
}

error_exit() {
    log "ERROR" "$1"
    exit 1
}

success() {
    log "SUCCESS" "$1"
}

# Check prerequisites
check_prerequisites() {
    log "INFO" "Checking prerequisites..."

    if ! command -v ansible-playbook &> /dev/null; then
        error_exit "Ansible is not installed. Please install ansible first."
    fi

    if [[ ! -f "$INVENTORY_FILE" ]]; then
        error_exit "Inventory file not found: $INVENTORY_FILE"
    fi

    if [[ ! -f "$PLAYBOOK_FILE" ]]; then
        error_exit "Playbook file not found: $PLAYBOOK_FILE"
    fi

    success "Prerequisites checked"
}

# Test VM connectivity
test_connectivity() {
    log "INFO" "Testing connectivity to all VMs..."

    if ansible all -i "$INVENTORY_FILE" -m ping --ask-pass; then
        success "All VMs are accessible"
    else
        error_exit "Some VMs are not accessible. Please check network connectivity."
    fi
}

# Show deployment plan
show_deployment_plan() {
    log "INFO" "🚀 AutoBot Hybrid Deployment Plan:"
    log "INFO" ""
    log "INFO" "VM1 (${AUTOBOT_FRONTEND_HOST:-172.16.168.21}) - autobot-frontend:"
    log "INFO" "  • Vue.js Frontend (port 5173)"
    log "INFO" "  • Nginx reverse proxy (port 80/443)"
    log "INFO" ""
    log "INFO" "VM2 (${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}) - Backend (STAYS ON HOST):"
    log "INFO" "  • FastAPI backend running locally"
    log "INFO" "  • Will connect to services on VMs"
    log "INFO" ""
    log "INFO" "VM3 (${AUTOBOT_REDIS_HOST:-172.16.168.23}) - autobot-database:"
    log "INFO" "  • Redis Stack (port 6379)"
    log "INFO" "  • RedisInsight (port 8002)"
    log "INFO" ""
    log "INFO" "VM4 (${AUTOBOT_AI_STACK_HOST:-172.16.168.24}) - autobot-aiml:"
    log "INFO" "  • AI Stack (port 8080)"
    log "INFO" "  • NPU Worker (port 8081)"
    log "INFO" "  • Ollama LLM server (port 11434)"
    log "INFO" ""
    log "INFO" "VM5 (${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}) - autobot-browser:"
    log "INFO" "  • Playwright browser service (port 3000)"
    log "INFO" "  • VNC server for desktop access (port 5900)"
    log "INFO" ""
}

# Deploy services to VMs
deploy_to_vms() {
    log "INFO" "🔄 Deploying Docker containers to VMs..."

    # Run the hybrid deployment playbook
    if ansible-playbook -i "$INVENTORY_FILE" "$PLAYBOOK_FILE" --ask-pass -v; then
        success "Deployment to VMs completed successfully"
    else
        error_exit "Deployment to VMs failed"
    fi
}

# Update local backend configuration
update_backend_config() {
    log "INFO" "🔧 Updating backend configuration for VM connections..."

    # Create environment file for backend with VM endpoints
    local env_file="/home/kali/Desktop/AutoBot/.env.hybrid"

    cat > "$env_file" << EOF
# AutoBot Hybrid Configuration - Backend on Host, Services on VMs
# Generated: $(date)

# Backend Configuration (stays on host)
AUTOBOT_BACKEND_HOST=127.0.0.1
AUTOBOT_BACKEND_PORT=8001

# VM Service Endpoints
AUTOBOT_REDIS_HOST=${AUTOBOT_REDIS_HOST:-172.16.168.23}
AUTOBOT_REDIS_PORT=6379
AUTOBOT_REDIS_PASSWORD=autobot123

AUTOBOT_AI_STACK_HOST=${AUTOBOT_AI_STACK_HOST:-172.16.168.24}
AUTOBOT_AI_STACK_PORT=8080

AUTOBOT_NPU_WORKER_HOST=${AUTOBOT_AI_STACK_HOST:-172.16.168.24}
AUTOBOT_NPU_WORKER_PORT=8081

AUTOBOT_OLLAMA_HOST=${AUTOBOT_AI_STACK_HOST:-172.16.168.24}
AUTOBOT_OLLAMA_PORT=11434

AUTOBOT_BROWSER_HOST=${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}
AUTOBOT_BROWSER_PORT=3000

AUTOBOT_FRONTEND_HOST=${AUTOBOT_FRONTEND_HOST:-172.16.168.21}
AUTOBOT_FRONTEND_PORT=5173

# Deployment mode
AUTOBOT_DEPLOYMENT_MODE=hybrid

# Database assignments for VM Redis
AUTOBOT_REDIS_DB_MAIN=0
AUTOBOT_REDIS_DB_KNOWLEDGE=1
AUTOBOT_REDIS_DB_PROMPTS=2
AUTOBOT_REDIS_DB_AGENTS=3
AUTOBOT_REDIS_DB_METRICS=4
AUTOBOT_REDIS_DB_LOGS=5
AUTOBOT_REDIS_DB_SESSIONS=6
AUTOBOT_REDIS_DB_WORKFLOWS=7
AUTOBOT_REDIS_DB_VECTORS=8
AUTOBOT_REDIS_DB_MODELS=9
AUTOBOT_REDIS_DB_TESTING=15
EOF

    success "Backend configuration updated: $env_file"
    log "INFO" "To use this config, run: export AUTOBOT_ENV_FILE=$env_file"
}

# Migrate existing data to VMs
migrate_data() {
    log "INFO" "💾 Migrating data from local Docker to VM Redis..."

    # Export current Redis data
    local backup_dir="/tmp/autobot-migration"
    mkdir -p "$backup_dir"

    # Export from local Redis
    if docker exec autobot-redis redis-cli --rdb "$backup_dir/redis-backup.rdb" save; then
        log "INFO" "Local Redis data exported"
    else
        log "WARN" "Failed to export local Redis data"
    fi

    # Copy backup to VM and import
    if scp "$backup_dir/redis-backup.rdb" ${AUTOBOT_SSH_USER:-autobot}@${AUTOBOT_REDIS_HOST:-172.16.168.23}:/tmp/; then
        log "INFO" "Backup copied to VM"

        # Import to VM Redis
        ssh ${AUTOBOT_SSH_USER:-autobot}@${AUTOBOT_REDIS_HOST:-172.16.168.23} "docker exec autobot-redis redis-cli --rdb /tmp/redis-backup.rdb restore"
        success "Data migration completed"
    else
        log "WARN" "Data migration failed - you may need to manually transfer data"
    fi
}

# Validate deployment
validate_deployment() {
    log "INFO" "✅ Validating hybrid deployment..."

    # Test VM services
    local services=(
        "${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:5173|Frontend"
        "${AUTOBOT_REDIS_HOST:-172.16.168.23}:6379|Redis"
        "${AUTOBOT_REDIS_HOST:-172.16.168.23}:8002|RedisInsight"
        "${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:8080|AI Stack"
        "${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:8081|NPU Worker"
        "${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:11434|Ollama"
        "${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:3000|Browser Service"
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
    r = redis.Redis(host='${AUTOBOT_REDIS_HOST:-172.16.168.23}', port=6379, password=os.environ.get('REDIS_PASSWORD', os.environ.get('AUTOBOT_REDIS_PASSWORD', '')), decode_responses=True)
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
    log "INFO" "🎉 AutoBot Hybrid Deployment Complete!"
    log "INFO" ""
    log "INFO" "Service Endpoints:"
    log "INFO" "  Frontend (VM):    http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:5173"
    log "INFO" "  Backend (Host):   http://localhost:8001"
    log "INFO" "  Redis (VM):       redis://${AUTOBOT_REDIS_HOST:-172.16.168.23}:6379"
    log "INFO" "  RedisInsight:     http://${AUTOBOT_REDIS_HOST:-172.16.168.23}:8002"
    log "INFO" "  AI Stack (VM):    http://${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:8080"
    log "INFO" "  NPU Worker (VM):  http://${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:8081"
    log "INFO" "  Ollama (VM):      http://${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:11434"
    log "INFO" "  Browser (VM):     http://${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:3000"
    log "INFO" ""
    log "INFO" "Next Steps:"
    log "INFO" "  1. Update backend environment: export AUTOBOT_ENV_FILE=/home/kali/Desktop/AutoBot/.env.hybrid"
    log "INFO" "  2. Restart backend: python backend/main.py"
    log "INFO" "  3. Access frontend: http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:5173"
    log "INFO" ""
    log "INFO" "Log file: $LOG_FILE"
}

# Usage information
show_usage() {
    cat << EOF
AutoBot Hybrid VM Deployment Script

Usage: $0 [OPTIONS]

Options:
    --plan              Show deployment plan
    --deploy            Deploy services to VMs
    --migrate           Migrate data from local to VMs
    --validate          Validate deployment
    --full              Complete deployment (deploy + migrate + validate)
    --help              Show this help message

Examples:
    $0 --plan           # Show what will be deployed
    $0 --full           # Complete hybrid deployment
    $0 --validate       # Check if services are running

EOF
}

# Main execution
main() {
    local start_time=$(date +%s)

    log "INFO" "🤖 AutoBot Hybrid VM Deployment Starting..."
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
        --deploy)
            check_prerequisites
            test_connectivity
            deploy_to_vms
            update_backend_config
            ;;
        --migrate)
            check_prerequisites
            migrate_data
            ;;
        --validate)
            validate_deployment
            ;;
        --full)
            check_prerequisites
            test_connectivity
            show_deployment_plan
            log "INFO" "Press Enter to continue with deployment..."
            read
            deploy_to_vms
            update_backend_config
            migrate_data
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
