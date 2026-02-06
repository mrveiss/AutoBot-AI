#!/bin/bash
#
# AutoBot Native VM Deployment Script
# Deploys AutoBot services natively on VMs (no Docker containers)
#

set -euo pipefail

# Load unified configuration system
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
    log "INFO" "🚀 AutoBot Native Deployment Plan:"
    log "INFO" ""
    log "INFO" "VM1 (172.16.168.21) - autobot-frontend:"
    log "INFO" "  • Node.js 18.x runtime"
    log "INFO" "  • Vue.js Frontend application"
    log "INFO" "  • Nginx reverse proxy (port 80/443)"
    log "INFO" "  • SystemD service: autobot-frontend"
    log "INFO" ""
    log "INFO" "WSL (172.16.168.20) - autobot-backend:"
    log "INFO" "  • FastAPI backend service (port 8001)"
    log "INFO" "  • Terminal service (ttyd) on port 7681"
    log "INFO" "  • noVNC service on port 6080"
    log "INFO" "  • Connects to services on VMs"
    log "INFO" ""
    log "INFO" "VM2 (172.16.168.22) - autobot-npu:"
    log "INFO" "  • NPU Worker service (port 8081)"
    log "INFO" "  • OpenVINO runtime with NPU + GPU access"
    log "INFO" "  • Hardware passthrough for AI acceleration"
    log "INFO" "  • SystemD service: autobot-npu-worker"
    log "INFO" ""
    log "INFO" "VM3 (172.16.168.23) - autobot-database:"
    log "INFO" "  • Redis Stack 7.4 (native installation)"
    log "INFO" "  • RedisInsight web UI (port 8002)"
    log "INFO" "  • SystemD service: redis-stack-server"
    log "INFO" ""
    log "INFO" "VM4 (172.16.168.24) - autobot-aistack:"
    log "INFO" "  • Python 3.11 runtime environment"
    log "INFO" "  • AI Stack service (port 8080)"
    log "INFO" "  • Ollama LLM server (port 11434)"
    log "INFO" "  • SystemD services: autobot-ai-stack, ollama"
    log "INFO" ""
    log "INFO" "VM5 (172.16.168.25) - autobot-browser:"
    log "INFO" "  • Node.js runtime for Playwright"
    log "INFO" "  • Browser service (port 3000)"
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
    local env_file="/home/kali/Desktop/AutoBot/.env.native"

    cat > "$env_file" << EOF
# AutoBot Native Configuration - Backend on Host, Services on VMs
# Generated: $(date)

# Backend Configuration (stays on host)
AUTOBOT_BACKEND_HOST=127.0.0.1
AUTOBOT_BACKEND_PORT=8001

# VM Service Endpoints - NATIVE DEPLOYMENT
AUTOBOT_REDIS_HOST=172.16.168.23
AUTOBOT_REDIS_PORT=6379
AUTOBOT_REDIS_PASSWORD=autobot123

AUTOBOT_AI_STACK_HOST=172.16.168.24
AUTOBOT_AI_STACK_PORT=8080

AUTOBOT_NPU_WORKER_HOST=172.16.168.24
AUTOBOT_NPU_WORKER_PORT=8081

AUTOBOT_OLLAMA_HOST=172.16.168.24
AUTOBOT_OLLAMA_PORT=11434

AUTOBOT_BROWSER_HOST=172.16.168.25
AUTOBOT_BROWSER_PORT=3000

AUTOBOT_FRONTEND_HOST=172.16.168.21
AUTOBOT_FRONTEND_PORT=80

# Deployment mode
AUTOBOT_DEPLOYMENT_MODE=native
AUTOBOT_USE_CONTAINERS=false

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

# Validate native deployment
validate_deployment() {
    log "INFO" "✅ Validating native deployment..."

    # Test VM services
    local services=(
        "172.16.168.21:80|Frontend"
        "172.16.168.23:6379|Redis Stack"
        "172.16.168.23:8002|RedisInsight"
        "172.16.168.24:8080|AI Stack"
        "172.16.168.24:8081|NPU Worker"
        "172.16.168.24:11434|Ollama"
        "172.16.168.25:3000|Browser Service"
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
    r = redis.Redis(host='172.16.168.23', port=6379, password=os.environ.get('REDIS_PASSWORD', os.environ.get('AUTOBOT_REDIS_PASSWORD', '')), decode_responses=True)
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
    log "INFO" "  AutoBot App:  http://172.16.168.21"
    log "INFO" ""
    log "INFO" "📡 Service Endpoints:"
    log "INFO" "  Frontend:     http://172.16.168.21 (PRIMARY APP ACCESS)"
    log "INFO" "  Backend:      http://172.16.168.20:8001 (WSL)"
    log "INFO" "  NPU Worker:   http://172.16.168.22:8081"
    log "INFO" "  Redis:        redis://172.16.168.23:6379"
    log "INFO" "  RedisInsight: http://172.16.168.23:8002"
    log "INFO" "  AI Stack:     http://172.16.168.24:8080"
    log "INFO" "  Ollama:       http://172.16.168.24:11434"
    log "INFO" "  Browser:      http://172.16.168.25:3000"
    log "INFO" ""
    log "INFO" "🖥️  Management Access:"
    log "INFO" "  Terminal:     http://172.16.168.20:7681 (WSL)"
    log "INFO" "  noVNC:        http://172.16.168.20:6080 (WSL)"
    log "INFO" "  VNC:          vnc://172.16.168.25:5900 (Browser VM)"
    log "INFO" ""
    log "INFO" "💻 SystemD Services:"
    log "INFO" "  WSL (172.16.168.20): autobot-backend, ttyd, tigervnc"
    log "INFO" "  VM1 (172.16.168.21): autobot-frontend, nginx"
    log "INFO" "  VM2 (172.16.168.22): autobot-npu-worker"
    log "INFO" "  VM3 (172.16.168.23): redis-stack-server"
    log "INFO" "  VM4 (172.16.168.24): autobot-ai-stack, ollama"
    log "INFO" "  VM5 (172.16.168.25): autobot-browser, autobot-vnc"
    log "INFO" ""
    log "INFO" "🚀 Next Steps:"
    log "INFO" "  1. Update backend environment: export AUTOBOT_ENV_FILE=/home/kali/Desktop/AutoBot/.env.native"
    log "INFO" "  2. Start backend on WSL: python backend/main.py"
    log "INFO" "  3. Access AutoBot: http://172.16.168.21"
    log "INFO" ""
    log "INFO" "🎯 PRIMARY APP ACCESS: http://172.16.168.21"
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
