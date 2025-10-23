#!/bin/bash
set -e

# AutoBot Native Deployment Script
# Seamless deployment - user provides credentials once, everything else is automated

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        "INFO")
            echo -e "${BLUE}ℹ️  $message${NC}"
            ;;
        "SUCCESS")
            echo -e "${GREEN}✅ $message${NC}"
            ;;
        "WARN")
            echo -e "${YELLOW}⚠️  $message${NC}"
            ;;
        "ERROR")
            echo -e "${RED}❌ $message${NC}"
            ;;
    esac
    
    echo "[$timestamp] [$level] $message" >> "/tmp/autobot-native-deploy.log"
}

# Main execution
main() {
    log "INFO" "🚀 AutoBot Native Deployment - Seamless Setup"
    log "INFO" "This will deploy AutoBot natively across your 6-machine infrastructure"
    log "INFO" "You'll be asked for VM credentials once - everything else is automated"
    
    echo
    echo "========================================================="
    echo "  AutoBot Native VM Infrastructure Deployment"
    echo "========================================================="
    echo "• WSL Host (172.16.168.20): Backend + Terminal + noVNC"
    echo "• VM1 (172.16.168.21): Frontend (Vue.js + Nginx)"
    echo "• VM2 (172.16.168.22): NPU Worker + OpenVINO"
    echo "• VM3 (172.16.168.23): Redis Stack + RedisInsight"
    echo "• VM4 (172.16.168.24): AI Stack + Ollama"
    echo "• VM5 (172.16.168.25): Browser + Playwright + VNC"
    echo "========================================================="
    echo
    
    # Check prerequisites
    log "INFO" "Checking prerequisites..."
    if ! command -v ansible-playbook &> /dev/null; then
        log "ERROR" "Ansible not found. Installing..."
        sudo apt update && sudo apt install -y ansible sshpass
    fi
    
    if ! command -v sshpass &> /dev/null; then
        log "ERROR" "sshpass not found. Installing..."
        sudo apt update && sudo apt install -y sshpass
    fi
    
    log "SUCCESS" "Prerequisites checked"
    
    # Step 1: Setup SSH keys (credentials asked once)
    log "INFO" "Setting up SSH keys for seamless automation..."
    setup_ssh_keys
    
    # Step 2: Setup VMs (hostnames, LVM, packages)
    log "INFO" "Setting up VM infrastructure..."
    setup_vms
    
    # Step 3: Deploy services with exact Docker container versions
    log "INFO" "Deploying native services with Docker-matching versions..."
    deploy_services
    
    # Step 4: Configure WSL backend
    log "INFO" "Configuring WSL backend services..."
    configure_backend
    
    # Step 5: Validate deployment
    log "INFO" "Validating deployment..."
    validate_deployment
    
    # Success
    log "SUCCESS" "🎉 AutoBot Native Deployment Complete!"
    echo
    echo "========================================================="
    echo "  🎯 PRIMARY ACCESS POINT: http://172.16.168.21"
    echo "========================================================="
    echo "• AutoBot Application: http://172.16.168.21"
    echo "• Backend API: http://172.16.168.20:8001"
    echo "• Terminal: http://172.16.168.20:7681"
    echo "• noVNC Desktop: http://172.16.168.20:6080"
    echo "• RedisInsight: http://172.16.168.23:8002"
    echo "• AI Stack: http://172.16.168.24:8080"
    echo "========================================================="
    echo
}

setup_ssh_keys() {
    # Generate SSH key if it doesn't exist
    if [[ ! -f ~/.ssh/autobot_key ]]; then
        log "INFO" "Generating SSH key pair..."
        ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key -N "" -C "autobot@wsl" &>/dev/null
    fi
    
    # Get VM credentials once
    if [[ -z "$VM_PASSWORD" ]]; then
        echo
        read -s -p "🔐 Enter VM password (will be asked once only): " VM_PASSWORD
        echo
        export VM_PASSWORD
    fi
    
    # Copy SSH keys to all VMs
    log "INFO" "Installing SSH keys on all VMs (automated after this)..."
    for ip in 172.16.168.21 172.16.168.22 172.16.168.23 172.16.168.24 172.16.168.25; do
        log "INFO" "Setting up SSH key for $ip..."
        sshpass -p "$VM_PASSWORD" ssh-copy-id -i ~/.ssh/autobot_key autobot@$ip &>/dev/null
    done
    
    log "SUCCESS" "SSH keys installed - remaining deployment is fully automated"
}

setup_vms() {
    log "INFO" "Setting up VM infrastructure..."
    ansible-playbook -i inventory/production.yml playbooks/setup-vm-names-and-lvm.yml --limit "!autobot-host" &>/dev/null
    log "SUCCESS" "VMs configured with hostnames and expanded LVM"
}

deploy_services() {
    log "INFO" "Creating source distribution for VMs..."
    
    # Create a clean source distribution
    mkdir -p /tmp/autobot-deployment
    
    # Copy essential files for each service type
    log "INFO" "Preparing frontend sources..."
    cp -r ../autobot-vue /tmp/autobot-deployment/
    
    log "INFO" "Preparing backend sources..."  
    cp -r ../src /tmp/autobot-deployment/
    cp -r ../requirements.txt /tmp/autobot-deployment/
    
    log "INFO" "Preparing AI stack sources..."
    cp -r ../docker/ai-stack/requirements-ai.txt /tmp/autobot-deployment/
    
    # Deploy with pre-built sources
    log "INFO" "Deploying native services to VMs..."
    SOURCE_DIR="/tmp/autobot-deployment" ansible-playbook -i inventory/production.yml playbooks/deploy-native-services.yml
    
    log "SUCCESS" "All services deployed natively"
}

configure_backend() {
    log "INFO" "Configuring WSL backend services..."
    
    # Install backend dependencies if needed
    if [[ ! -f ../venv/bin/activate ]]; then
        log "INFO" "Creating Python virtual environment..."
        python3 -m venv ../venv
        source ../venv/bin/activate
        pip install -r ../requirements.txt
    fi
    
    # Configure environment for native deployment
    log "INFO" "Configuring environment for native VM deployment..."
    cat > ../.env.native << EOF
# Native VM Deployment Configuration
AUTOBOT_DEPLOYMENT_MODE=native
AUTOBOT_BACKEND_HOST=172.16.168.20
AUTOBOT_REDIS_HOST=172.16.168.23
AUTOBOT_AI_STACK_HOST=172.16.168.24
AUTOBOT_NPU_WORKER_HOST=172.16.168.22
AUTOBOT_BROWSER_HOST=172.16.168.25
AUTOBOT_FRONTEND_HOST=172.16.168.21

# Service Ports
BACKEND_PORT=8001
TERMINAL_PORT=7681
NOVNC_PORT=6080
REDIS_PORT=6379
AI_STACK_PORT=8080
NPU_WORKER_PORT=8081
BROWSER_PORT=3000
EOF
    
    log "SUCCESS" "Backend configured for native deployment"
}

validate_deployment() {
    log "INFO" "Validating all services..."
    
    # Test VM connectivity
    log "INFO" "Testing VM connectivity..."
    ansible all -i inventory/production.yml -m ping --limit "!autobot-host" &>/dev/null
    
    # Test service endpoints
    log "INFO" "Testing service endpoints..."
    local services=(
        "172.16.168.21:80:Frontend"
        "172.16.168.23:6379:Redis"
        "172.16.168.24:8080:AI-Stack"
        "172.16.168.22:8081:NPU-Worker"
        "172.16.168.25:3000:Browser"
    )
    
    for service in "${services[@]}"; do
        IFS=':' read -ra ADDR <<< "$service"
        local ip="${ADDR[0]}"
        local port="${ADDR[1]}"
        local name="${ADDR[2]}"
        
        if timeout 5 bash -c "</dev/tcp/$ip/$port" &>/dev/null; then
            log "SUCCESS" "$name service responding on $ip:$port"
        else
            log "WARN" "$name service not yet responding on $ip:$port"
        fi
    done
    
    log "SUCCESS" "Deployment validation complete"
}

# Run main function
main "$@"