#!/bin/bash

# Complete VM Sync Templates for AutoBot Distributed Architecture
# Provides comprehensive sync capabilities for all VMs and services

set -e  # Exit on error

# Configuration
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
AUTOBOT_ROOT="/home/kali/Desktop/AutoBot"
SSH_KEY="$HOME/.ssh/autobot_key"
SSH_OPTS="-i $SSH_KEY"

# VM Configuration
declare -A VM_IPS=(
    ["frontend"]="172.16.168.21"
    ["npu-worker"]="172.16.168.22"
    ["redis"]="172.16.168.23"
    ["ai-stack"]="172.16.168.24"
    ["browser"]="172.16.168.25"
)

declare -A VM_SERVICES=(
    ["frontend"]="autobot-frontend"
    ["npu-worker"]="autobot-npu-worker"
    ["redis"]="redis-server"
    ["ai-stack"]="autobot-ai-stack"
    ["browser"]="autobot-browser"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
    exit 1
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    if [[ ! -f "$SSH_KEY" ]]; then
        error "SSH key not found at $SSH_KEY. Run ./setup-ssh-keys.sh first."
    fi
    
    if [[ ! -d "$AUTOBOT_ROOT" ]]; then
        error "AutoBot root directory not found at $AUTOBOT_ROOT"
    fi
    
    success "Prerequisites check passed"
}

# Test SSH connectivity to all VMs
test_connectivity() {
    log "Testing SSH connectivity to all VMs..."
    
    for vm in "${!VM_IPS[@]}"; do
        ip="${VM_IPS[$vm]}"
        if ssh $SSH_OPTS autobot@"$ip" "echo 'Connected to $vm'" >/dev/null 2>&1; then
            success "$vm ($ip) - Connected"
        else
            error "$vm ($ip) - Connection failed"
        fi
    done
}

# Sync specific file to specific VM
sync_file_to_vm() {
    local vm="$1"
    local local_file="$2"
    local remote_path="$3"
    local restart_service="${4:-false}"
    
    if [[ -z "${VM_IPS[$vm]}" ]]; then
        error "Unknown VM: $vm"
    fi
    
    local vm_ip="${VM_IPS[$vm]}"
    
    log "Syncing $local_file to $vm ($vm_ip):$remote_path"
    
    # Ensure local file exists
    if [[ ! -e "$AUTOBOT_ROOT/$local_file" ]]; then
        error "Local file not found: $AUTOBOT_ROOT/$local_file"
    fi
    
    # Create remote directory if needed
    ssh $SSH_OPTS autobot@"$vm_ip" "mkdir -p $(dirname "$remote_path")"
    
    # Sync file
    rsync -avz -e "ssh $SSH_OPTS" \
        "$AUTOBOT_ROOT/$local_file" \
        "autobot@$vm_ip:$remote_path"
    
    success "Synced $local_file to $vm"
    
    # Restart service if requested
    if [[ "$restart_service" == "true" ]]; then
        restart_vm_service "$vm"
    fi
}

# Sync directory to specific VM
sync_directory_to_vm() {
    local vm="$1"
    local local_dir="$2"
    local remote_dir="$3"
    local restart_service="${4:-false}"
    
    if [[ -z "${VM_IPS[$vm]}" ]]; then
        error "Unknown VM: $vm"
    fi
    
    local vm_ip="${VM_IPS[$vm]}"
    
    log "Syncing directory $local_dir to $vm ($vm_ip):$remote_dir"
    
    # Ensure local directory exists
    if [[ ! -d "$AUTOBOT_ROOT/$local_dir" ]]; then
        error "Local directory not found: $AUTOBOT_ROOT/$local_dir"
    fi
    
    # Create remote directory if needed
    ssh $SSH_OPTS autobot@"$vm_ip" "mkdir -p $remote_dir"
    
    # Sync directory with --delete to remove old files
    rsync -avz --delete -e "ssh $SSH_OPTS" \
        "$AUTOBOT_ROOT/$local_dir/" \
        "autobot@$vm_ip:$remote_dir/"
    
    success "Synced directory $local_dir to $vm"
    
    # Restart service if requested
    if [[ "$restart_service" == "true" ]]; then
        restart_vm_service "$vm"
    fi
}

# Restart service on VM
restart_vm_service() {
    local vm="$1"
    local vm_ip="${VM_IPS[$vm]}"
    local service="${VM_SERVICES[$vm]}"
    
    log "Restarting $service on $vm"
    
    if ssh $SSH_OPTS autobot@"$vm_ip" "sudo systemctl restart $service" 2>/dev/null; then
        success "Service $service restarted on $vm"
    else
        warn "Failed to restart $service on $vm (service may not exist yet)"
    fi
}

# Service-specific sync functions
sync_frontend() {
    local component="$1"
    
    if [[ -n "$component" ]]; then
        # Sync specific component
        sync_file_to_vm "frontend" "autobot-vue/src/components/$component" \
            "/home/autobot/autobot-vue/src/components/$component"
    else
        # Sync entire frontend
        sync_directory_to_vm "frontend" "autobot-vue" "/home/autobot/autobot-vue"
        
        # Build on remote
        log "Building frontend on VM..."
        ssh $SSH_OPTS autobot@"${VM_IPS[frontend]}" \
            "cd /home/autobot/autobot-vue && npm install && npm run build"
        
        # Deploy to nginx
        ssh $SSH_OPTS autobot@"${VM_IPS[frontend]}" \
            "sudo cp -r /home/autobot/autobot-vue/dist/* /var/www/html/"
        
        success "Frontend deployed to nginx"
    fi
}

sync_backend() {
    local api_module="$1"
    
    if [[ -n "$api_module" ]]; then
        # Sync specific API module
        sync_file_to_vm "ai-stack" "backend/api/$api_module" \
            "/home/autobot/backend/api/$api_module" true
    else
        # Sync entire backend
        sync_directory_to_vm "ai-stack" "backend" "/home/autobot/backend" true
    fi
}

sync_npu_worker() {
    sync_directory_to_vm "npu-worker" "docker/npu_worker" "/home/autobot/npu_worker" true
}

sync_redis_config() {
    sync_file_to_vm "redis" "config/redis.conf" "/etc/redis/redis.conf" true
}

sync_docker_configs() {
    local vm="$1"
    sync_file_to_vm "$vm" "docker-compose.yml" "/home/autobot/docker-compose.yml"
}

sync_all_vms() {
    log "Syncing common files to all VMs..."
    
    for vm in "${!VM_IPS[@]}"; do
        log "Syncing to $vm..."
        
        # Sync common scripts
        sync_directory_to_vm "$vm" "scripts" "/home/autobot/scripts"
        
        # Sync environment files
        sync_file_to_vm "$vm" ".env" "/home/autobot/.env"
        
        # Sync docker-compose if it exists
        if [[ -f "$AUTOBOT_ROOT/docker-compose.yml" ]]; then
            sync_file_to_vm "$vm" "docker-compose.yml" "/home/autobot/docker-compose.yml"
        fi
        
        success "Common files synced to $vm"
    done
}

# Status check for all VMs
check_all_vm_status() {
    log "Checking status of all VMs..."
    
    for vm in "${!VM_IPS[@]}"; do
        local vm_ip="${VM_IPS[$vm]}"
        local service="${VM_SERVICES[$vm]}"
        
        echo -e "\n${BLUE}=== $vm ($vm_ip) ===${NC}"
        
        # Check connectivity
        if ssh $SSH_OPTS autobot@"$vm_ip" "echo 'Connected'" >/dev/null 2>&1; then
            success "SSH: Connected"
        else
            error "SSH: Failed"
        fi
        
        # Check service status
        if ssh $SSH_OPTS autobot@"$vm_ip" "systemctl is-active $service" >/dev/null 2>&1; then
            success "Service ($service): Running"
        else
            warn "Service ($service): Not running or doesn't exist"
        fi
        
        # Check disk space
        local disk_usage
        disk_usage=$(ssh $SSH_OPTS autobot@"$vm_ip" "df -h / | tail -1 | awk '{print \$5}'")
        echo "Disk Usage: $disk_usage"
        
        # Check memory
        local memory_usage
        memory_usage=$(ssh $SSH_OPTS autobot@"$vm_ip" "free -h | grep Mem | awk '{print \$3\"/\"\$2}'")
        echo "Memory Usage: $memory_usage"
    done
}

# Main command processing
case "${1:-help}" in
    "test")
        check_prerequisites
        test_connectivity
        ;;
    "frontend")
        check_prerequisites
        sync_frontend "$2"
        ;;
    "backend")
        check_prerequisites
        sync_backend "$2"
        ;;
    "npu-worker")
        check_prerequisites
        sync_npu_worker
        ;;
    "redis")
        check_prerequisites
        sync_redis_config
        ;;
    "docker")
        check_prerequisites
        sync_docker_configs "$2"
        ;;
    "all")
        check_prerequisites
        sync_all_vms
        ;;
    "status")
        check_prerequisites
        check_all_vm_status
        ;;
    "file")
        if [[ $# -lt 4 ]]; then
            error "Usage: $0 file <vm> <local_file> <remote_path> [restart_service]"
        fi
        check_prerequisites
        sync_file_to_vm "$2" "$3" "$4" "${5:-false}"
        ;;
    "dir")
        if [[ $# -lt 4 ]]; then
            error "Usage: $0 dir <vm> <local_dir> <remote_dir> [restart_service]"
        fi
        check_prerequisites
        sync_directory_to_vm "$2" "$3" "$4" "${5:-false}"
        ;;
    "help"|*)
        cat << EOF
AutoBot Complete VM Sync Tool

Usage: $0 <command> [options]

Commands:
  test                    Test SSH connectivity to all VMs
  frontend [component]    Sync frontend (specific component or all)
  backend [module]        Sync backend (specific API module or all)  
  npu-worker             Sync NPU worker code
  redis                  Sync Redis configuration
  docker <vm>            Sync docker-compose to specific VM
  all                    Sync common files to all VMs
  status                 Check status of all VMs
  file <vm> <src> <dst>  Sync specific file to VM
  dir <vm> <src> <dst>   Sync directory to VM
  help                   Show this help

VM Names: frontend, npu-worker, redis, ai-stack, browser

Examples:
  $0 test                                    # Test all connections
  $0 frontend App.vue                        # Sync specific component  
  $0 backend chat.py                         # Sync specific API module
  $0 frontend                                # Sync entire frontend and build
  $0 backend                                 # Sync entire backend
  $0 all                                     # Sync common files to all VMs
  $0 status                                  # Check all VM status
  $0 file ai-stack config.py /home/autobot/config.py  # Sync specific file

SSH Key: $SSH_KEY
AutoBot Root: $AUTOBOT_ROOT

Note: All edits MUST be made locally first, then synced to VMs.
NEVER edit files directly on remote VMs.
EOF
        ;;
esac