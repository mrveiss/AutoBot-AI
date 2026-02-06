#!/bin/bash
#
# AutoBot Hyper-V Deployment Script
# Comprehensive deployment orchestration for migrating AutoBot from Docker to 5 VMs
#

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANSIBLE_DIR="$SCRIPT_DIR"
INVENTORY_FILE="$ANSIBLE_DIR/inventory/production.yml"
PLAYBOOK_DIR="$ANSIBLE_DIR/playbooks"
LOG_DIR="/tmp/autobot-deployment"
LOG_FILE="$LOG_DIR/deployment-$(date +%Y%m%d-%H%M%S).log"

# Issue #700: Vault configuration
VAULT_PASSWORD_FILE="${VAULT_PASSWORD_FILE:-}"
USE_VAULT="${USE_VAULT:-false}"
ASK_BECOME_PASS="${ASK_BECOME_PASS:-false}"

# Create log directory
mkdir -p "$LOG_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Create log directory if it doesn't exist
    mkdir -p "$LOG_DIR"

    # Color coding for different levels
    case "$level" in
        "INFO")  echo -e "${GREEN}[INFO]${NC}  $message" | tee -a "$LOG_FILE" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC}  $message" | tee -a "$LOG_FILE" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} $message" | tee -a "$LOG_FILE" ;;
        "DEBUG") echo -e "${BLUE}[DEBUG]${NC} $message" | tee -a "$LOG_FILE" ;;
        *)       echo "[$level] $message" | tee -a "$LOG_FILE" ;;
    esac
}

# Error handling
error_exit() {
    log "ERROR" "$1"
    exit 1
}

# Success message
success() {
    log "INFO" "✅ $1"
}

# Warning message
warn() {
    log "WARN" "⚠️  $1"
}

# Check prerequisites
check_prerequisites() {
    log "INFO" "Checking prerequisites..."

    # Check if ansible is installed
    if ! command -v ansible-playbook &> /dev/null; then
        error_exit "Ansible is not installed. Please install ansible first."
    fi

    # Check if inventory file exists
    if [[ ! -f "$INVENTORY_FILE" ]]; then
        error_exit "Inventory file not found: $INVENTORY_FILE"
    fi

    # Check if SSH key exists
    if [[ ! -f ~/.ssh/autobot_key ]]; then
        warn "SSH key not found at ~/.ssh/autobot_key"
        log "INFO" "You may need to generate SSH keys and copy them to VMs:"
        log "INFO" "  ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key -N ''"
        log "INFO" "  ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@VM_IP"
    fi

    success "Prerequisites checked"
}

# Test connectivity to all VMs
test_connectivity() {
    log "INFO" "Testing connectivity to all VMs..."

    if ansible all -i "$INVENTORY_FILE" -m ping --timeout=10; then
        success "All VMs are reachable"
    else
        error_exit "Some VMs are not reachable. Check your inventory and SSH configuration."
    fi
}

# Install Ansible requirements
install_requirements() {
    log "INFO" "Installing Ansible requirements..."

    if [[ -f "$ANSIBLE_DIR/requirements.yml" ]]; then
        ansible-galaxy install -r "$ANSIBLE_DIR/requirements.yml" --force
        success "Ansible requirements installed"
    else
        warn "No requirements.yml file found, skipping"
    fi
}

# Run playbook with proper error handling
run_playbook() {
    local playbook="$1"
    local description="$2"
    local extra_args="${3:-}"

    log "INFO" "🚀 Starting: $description"
    log "DEBUG" "Running playbook: $playbook"

    local playbook_path="$PLAYBOOK_DIR/$playbook"
    if [[ ! -f "$playbook_path" ]]; then
        error_exit "Playbook not found: $playbook_path"
    fi

    # Build ansible command
    local ansible_cmd="ansible-playbook -i $INVENTORY_FILE $playbook_path"

    # Add extra arguments if provided
    if [[ -n "$extra_args" ]]; then
        ansible_cmd="$ansible_cmd $extra_args"
    fi

    # Issue #700: Add vault support
    if [[ "$USE_VAULT" == "true" ]]; then
        if [[ -n "$VAULT_PASSWORD_FILE" && -f "$VAULT_PASSWORD_FILE" ]]; then
            ansible_cmd="$ansible_cmd --vault-password-file=$VAULT_PASSWORD_FILE"
        else
            ansible_cmd="$ansible_cmd --ask-vault-pass"
        fi
    fi

    # Issue #700: Add become password prompt if needed
    if [[ "$ASK_BECOME_PASS" == "true" ]]; then
        ansible_cmd="$ansible_cmd --ask-become-pass"
    fi

    # Add verbosity if debug mode
    if [[ "${DEBUG:-false}" == "true" ]]; then
        ansible_cmd="$ansible_cmd -vvv"
    fi

    # Execute playbook
    if eval "$ansible_cmd"; then
        success "$description completed successfully"
        return 0
    else
        error_exit "$description failed"
        return 1
    fi
}

# Validate deployment
validate_deployment() {
    log "INFO" "Validating deployment..."

    # Run health check playbook
    run_playbook "health-check.yml" "Health check validation"

    # Check individual services
    log "INFO" "Checking individual services..."

    # Frontend check
    if curl -s -f "http://192.168.100.10/health" > /dev/null; then
        success "Frontend service is healthy"
    else
        warn "Frontend service health check failed"
    fi

    # Backend check
    if curl -s -f "http://192.168.100.20:8001/api/health" > /dev/null; then
        success "Backend service is healthy"
    else
        warn "Backend service health check failed"
    fi

    # Database check
    if redis-cli -h 192.168.100.50 ping | grep -q PONG; then
        success "Database service is healthy"
    else
        warn "Database service health check failed"
    fi

    # AI/ML services check
    if curl -s -f "http://192.168.100.30:8080/health" > /dev/null; then
        success "AI Stack service is healthy"
    else
        warn "AI Stack service health check failed"
    fi

    if curl -s -f "http://192.168.100.40:8081/health" > /dev/null; then
        success "NPU Worker service is healthy"
    else
        warn "NPU Worker service health check failed"
    fi

    # Browser service check
    if curl -s -f "http://192.168.100.40:3000/health" > /dev/null; then
        success "Browser service is healthy"
    else
        warn "Browser service health check failed"
    fi
}

# Show deployment summary
show_summary() {
    log "INFO" "🎉 AutoBot Deployment Summary"
    log "INFO" "=============================="
    log "INFO" ""
    log "INFO" "Service Endpoints:"
    log "INFO" "  Frontend:    http://192.168.100.10"
    log "INFO" "  Backend API: http://192.168.100.20:8001"
    log "INFO" "  Redis:       redis://192.168.100.50:6379"
    log "INFO" "  RedisInsight: http://192.168.100.50:8002"
    log "INFO" "  AI Stack:    http://192.168.100.30:8080"
    log "INFO" "  NPU Worker:  http://192.168.100.40:8081"
    log "INFO" "  Browser:     http://192.168.100.40:3000"
    log "INFO" "  VNC Server:  vnc://192.168.100.40:5901"
    log "INFO" ""
    log "INFO" "Management:"
    log "INFO" "  SSH Frontend: ssh autobot@192.168.100.10"
    log "INFO" "  SSH Backend:  ssh autobot@192.168.100.20"
    log "INFO" "  SSH Database: ssh autobot@192.168.100.50"
    log "INFO" "  SSH AI/ML:    ssh autobot@192.168.100.30"
    log "INFO" "  SSH Browser:  ssh autobot@192.168.100.40"
    log "INFO" ""
    log "INFO" "Next Steps:"
    log "INFO" "  1. Access AutoBot at http://192.168.100.10"
    log "INFO" "  2. Monitor services with: ./deploy.sh --health-check"
    log "INFO" "  3. View logs: ./utils/view-logs.sh"
    log "INFO" "  4. Create backups: ./utils/backup.sh --full"
    log "INFO" ""
    log "INFO" "Deployment completed in $(( $(date +%s) - START_TIME )) seconds"
}

# Main deployment functions
setup_vms() {
    log "INFO" "🏗️ Setting up VM hostnames and expanding LVM storage..."
    run_playbook "setup-vm-names-and-lvm.yml" "VM setup and LVM expansion"
}

deploy_base_system() {
    log "INFO" "📦 Deploying base system configuration..."
    run_playbook "deploy-base.yml" "Base system deployment"
}

deploy_services() {
    log "INFO" "🔧 Deploying AutoBot services..."

    # Deploy in dependency order
    run_playbook "deploy-database.yml" "Database deployment"
    sleep 10  # Wait for database to be ready

    run_playbook "deploy-backend.yml" "Backend deployment"
    sleep 10  # Wait for backend to be ready

    run_playbook "deploy-aiml.yml" "AI/ML deployment"
    sleep 10  # Wait for AI services to be ready

    run_playbook "deploy-frontend.yml" "Frontend deployment"
    sleep 5   # Wait for frontend to be ready

    run_playbook "deploy-browser.yml" "Browser deployment"
}

migrate_data() {
    log "INFO" "📋 Migrating data from Docker containers..."
    run_playbook "data-migration.yml" "Data migration"
}

start_services() {
    log "INFO" "🚀 Starting AutoBot services..."

    # Start services in proper order
    ansible database -i "$INVENTORY_FILE" -m systemd -a "name=redis-stack-server state=started enabled=yes" --become
    sleep 5

    ansible backend -i "$INVENTORY_FILE" -m systemd -a "name=autobot-backend state=started enabled=yes" --become
    sleep 5

    ansible aiml -i "$INVENTORY_FILE" -m systemd -a "name=autobot-ai-stack state=started enabled=yes" --become
    ansible aiml -i "$INVENTORY_FILE" -m systemd -a "name=autobot-npu-worker state=started enabled=yes" --become
    sleep 5

    ansible frontend -i "$INVENTORY_FILE" -m systemd -a "name=nginx state=started enabled=yes" --become
    ansible frontend -i "$INVENTORY_FILE" -m systemd -a "name=autobot-frontend state=started enabled=yes" --become
    sleep 5

    ansible browser -i "$INVENTORY_FILE" -m systemd -a "name=autobot-vnc-server state=started enabled=yes" --become
    ansible browser -i "$INVENTORY_FILE" -m systemd -a "name=autobot-playwright state=started enabled=yes" --become

    success "All services started"
}

stop_services() {
    log "INFO" "🛑 Stopping AutoBot services..."

    # Stop services in reverse order
    ansible browser -i "$INVENTORY_FILE" -m systemd -a "name=autobot-playwright state=stopped" --become || true
    ansible browser -i "$INVENTORY_FILE" -m systemd -a "name=autobot-vnc-server state=stopped" --become || true

    ansible frontend -i "$INVENTORY_FILE" -m systemd -a "name=autobot-frontend state=stopped" --become || true
    ansible frontend -i "$INVENTORY_FILE" -m systemd -a "name=nginx state=stopped" --become || true

    ansible aiml -i "$INVENTORY_FILE" -m systemd -a "name=autobot-npu-worker state=stopped" --become || true
    ansible aiml -i "$INVENTORY_FILE" -m systemd -a "name=autobot-ai-stack state=stopped" --become || true

    ansible backend -i "$INVENTORY_FILE" -m systemd -a "name=autobot-backend state=stopped" --become || true

    ansible database -i "$INVENTORY_FILE" -m systemd -a "name=redis-stack-server state=stopped" --become || true

    success "All services stopped"
}

restart_services() {
    log "INFO" "🔄 Restarting AutoBot services..."
    stop_services
    sleep 10
    start_services
}

# Rollback functionality
rollback_deployment() {
    log "INFO" "🔙 Rolling back deployment..."

    # Stop current services
    stop_services

    # Run rollback playbook
    run_playbook "rollback.yml" "Deployment rollback"

    success "Rollback completed"
}

# Dependency patching - Issue #682
# oVirt-style rolling updates for Python dependencies
patch_dependencies() {
    local dry_run="${1:-false}"
    local extra_args=""

    log "INFO" "🔧 Starting dependency patching (rolling updates)..."
    log "INFO" "Mode: $([ "$dry_run" = "true" ] && echo "DRY RUN" || echo "LIVE UPDATE")"

    if [[ "$dry_run" == "true" ]]; then
        extra_args="-e dry_run=true --check"
    else
        extra_args="-e auto_confirm=true"
    fi

    run_playbook "patch-dependencies.yml" "Dependency patching (CVE remediation)" "$extra_args"

    if [[ "$dry_run" != "true" ]]; then
        log "INFO" "Running pip-audit to verify CVE remediation..."
        # Verify on backend (primary Python service)
        ansible backend -i "$INVENTORY_FILE" -m shell -a "source /opt/autobot/venv/bin/activate && pip-audit 2>/dev/null | head -20" --become || true
    fi

    success "Dependency patching completed"
}

# Rollback dependencies - Issue #682
rollback_dependencies() {
    log "INFO" "🔙 Rolling back dependencies to last backup..."

    # Use dedicated rollback playbook (targets Python hosts only: backend, ai_stack, npu_workers)
    run_playbook "rollback-dependencies.yml" "Dependency rollback" "-e auto_confirm=true"

    # Verify health after rollback
    log "INFO" "Verifying service health after rollback..."
    health_check

    success "Dependency rollback completed"
}

# System package patching - Issue #682
# oVirt-style rolling updates for apt packages
patch_system() {
    local dry_run="${1:-false}"
    local security_only="${2:-false}"
    local reboot="${3:-false}"
    local extra_args=""

    log "INFO" "🔧 Starting system package patching (rolling updates)..."
    log "INFO" "Mode: $([ "$dry_run" = "true" ] && echo "DRY RUN" || echo "LIVE UPDATE")"
    log "INFO" "Security only: $security_only"
    log "INFO" "Reboot if required: $reboot"

    extra_args="-e auto_confirm=true"

    if [[ "$dry_run" == "true" ]]; then
        extra_args="$extra_args --check"
    fi

    if [[ "$security_only" == "true" ]]; then
        extra_args="$extra_args -e security_only=true"
    fi

    if [[ "$reboot" == "true" ]]; then
        extra_args="$extra_args -e reboot_if_required=true"
    fi

    run_playbook "patch-system-packages.yml" "System package patching (apt updates)" "$extra_args"

    success "System package patching completed"
}

# Rollback system packages - Issue #682
rollback_system() {
    log "INFO" "🔙 Rolling back system packages..."

    # Use dedicated rollback playbook
    run_playbook "rollback-system-packages.yml" "System package rollback" "-e auto_confirm=true"

    # Verify health after rollback
    log "INFO" "Verifying service health after rollback..."
    health_check

    success "System package rollback completed"
}

# Health check
health_check() {
    log "INFO" "🏥 Running health checks..."
    run_playbook "health-check.yml" "Health check"
    validate_deployment
}

# Issue #700: Setup passwordless sudo on all VMs
setup_passwordless_sudo() {
    log "INFO" "🔐 Setting up passwordless sudo for autobot user..."
    log "INFO" "This requires one-time password authentication"

    # Force ask-become-pass for this operation
    local saved_ask_become="$ASK_BECOME_PASS"
    ASK_BECOME_PASS="true"

    run_playbook "setup-passwordless-sudo.yml" "Passwordless sudo configuration"

    ASK_BECOME_PASS="$saved_ask_become"
    success "Passwordless sudo configured - future operations won't require passwords"
}

# Usage information
show_usage() {
    cat << EOF
AutoBot Hyper-V Deployment Script

USAGE:
  $0 [OPTIONS]

OPTIONS:
  --full              Complete deployment (base + services + data + start)
  --base-system       Deploy base system only (Ubuntu updates, users, security)
  --services          Deploy AutoBot services only
  --data-migration    Migrate data from Docker/existing system
  --start             Start AutoBot services
  --stop              Stop AutoBot services
  --restart           Restart AutoBot services
  --health-check      Validate all services are healthy
  --rollback          Rollback to previous version

  Security & Authentication (Issue #700):
  --setup-sudo        Configure passwordless sudo for autobot user (one-time setup)
  --ask-become-pass   Prompt for become (sudo) password
  --use-vault         Use Ansible Vault for encrypted credentials
  --vault-file FILE   Path to vault password file (default: prompt)

  Dependency Patching (Issue #682):
  --patch-dependencies        Update Python dependencies with CVE fixes (rolling update)
  --patch-dependencies-check  Dry run - preview dependency updates
  --rollback-dependencies     Rollback dependencies to last backup

  System Package Updates (Issue #682):
  --patch-system              Update all system packages (apt upgrade)
  --patch-system-check        Dry run - preview system updates
  --patch-system-security     Security updates only (apt security upgrades)
  --patch-system-reboot       Update and reboot if required (kernel updates)
  --rollback-system           Rollback system packages (restore services)

  --test-connectivity Test SSH connectivity to all VMs
  --install-reqs      Install Ansible requirements
  --validate          Validate deployment configuration
  --debug             Enable debug output
  --help              Show this help message

EXAMPLES:
  # Full deployment from scratch
  $0 --full

  # Deploy only services (after base system is ready)
  $0 --services

  # Migrate data and start services
  $0 --data-migration --start

  # Health check and validation
  $0 --health-check

  # Emergency stop
  $0 --stop

  # First-time setup: configure passwordless sudo (Issue #700)
  $0 --setup-sudo

  # Deploy with vault-encrypted credentials
  $0 --use-vault --full

  # Deploy with become password prompt (if sudo not passwordless)
  $0 --ask-become-pass --services

PREREQUISITES:
  1. Ansible installed and configured
  2. SSH key generated and copied to all VMs:
     ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key -N ''
     ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@VM_IP
  3. Update inventory/production.yml with actual VM IP addresses
  4. VMs running Ubuntu 22.04 LTS with 'autobot' user
  5. (Optional) Run --setup-sudo once to enable passwordless sudo

SECURITY (Issue #700):
  - SSH key authentication is used (no password auth)
  - Become passwords stored in encrypted vault (inventory/group_vars/vault.yml)
  - Run --setup-sudo to configure passwordless sudo (recommended)
  - To encrypt vault: ansible-vault encrypt inventory/group_vars/vault.yml

EOF
}

# Main execution
main() {
    # Record start time
    START_TIME=$(date +%s)

    log "INFO" "🤖 AutoBot Hyper-V Deployment Script Starting..."
    log "INFO" "Timestamp: $(date)"
    log "INFO" "Log file: $LOG_FILE"

    # Parse command line arguments
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi

    while [[ $# -gt 0 ]]; do
        case $1 in
            --full)
                check_prerequisites
                install_requirements
                test_connectivity
                setup_vms           # NEW: VM hostname and LVM setup
                deploy_base_system
                deploy_services
                migrate_data
                start_services
                validate_deployment
                show_summary
                ;;
            --setup-vms)
                check_prerequisites
                test_connectivity
                setup_vms
                ;;
            --base-system)
                check_prerequisites
                test_connectivity
                deploy_base_system
                ;;
            --services)
                check_prerequisites
                test_connectivity
                deploy_services
                ;;
            --data-migration)
                check_prerequisites
                test_connectivity
                migrate_data
                ;;
            --start)
                check_prerequisites
                test_connectivity
                start_services
                ;;
            --stop)
                check_prerequisites
                test_connectivity
                stop_services
                ;;
            --restart)
                check_prerequisites
                test_connectivity
                restart_services
                ;;
            --health-check)
                check_prerequisites
                test_connectivity
                health_check
                ;;
            --rollback)
                check_prerequisites
                test_connectivity
                rollback_deployment
                ;;
            # Issue #700: Security & Authentication options
            --setup-sudo)
                check_prerequisites
                test_connectivity
                setup_passwordless_sudo
                ;;
            --ask-become-pass)
                ASK_BECOME_PASS="true"
                ;;
            --use-vault)
                USE_VAULT="true"
                ;;
            --vault-file)
                shift
                if [[ -n "${1:-}" && ! "$1" =~ ^-- ]]; then
                    VAULT_PASSWORD_FILE="$1"
                    USE_VAULT="true"
                else
                    error_exit "--vault-file requires a file path argument"
                fi
                ;;
            --patch-dependencies)
                check_prerequisites
                test_connectivity
                patch_dependencies false
                ;;
            --patch-dependencies-check)
                check_prerequisites
                test_connectivity
                patch_dependencies true
                ;;
            --rollback-dependencies)
                check_prerequisites
                test_connectivity
                rollback_dependencies
                ;;
            --patch-system)
                check_prerequisites
                test_connectivity
                patch_system false false false
                ;;
            --patch-system-check)
                check_prerequisites
                test_connectivity
                patch_system true false false
                ;;
            --patch-system-security)
                check_prerequisites
                test_connectivity
                patch_system false true false
                ;;
            --patch-system-reboot)
                check_prerequisites
                test_connectivity
                patch_system false false true
                ;;
            --rollback-system)
                check_prerequisites
                test_connectivity
                rollback_system
                ;;
            --test-connectivity)
                check_prerequisites
                test_connectivity
                ;;
            --install-reqs)
                install_requirements
                ;;
            --validate)
                check_prerequisites
                validate_deployment
                ;;
            --debug)
                export DEBUG=true
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                error_exit "Unknown option: $1. Use --help for usage information."
                ;;
        esac
        shift
    done

    success "Script execution completed"
}

# Trap for cleanup on exit
trap 'log "INFO" "Script execution finished"' EXIT

# Execute main function with all arguments
main "$@"
