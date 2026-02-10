#!/bin/bash

# AutoBot Centralized Logging Setup Script
# Sets up centralized log collection from all 5 VMs to main machine

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
LOGS_DIR="$PROJECT_ROOT/logs"
CENTRALIZED_DIR="$LOGS_DIR/autobot-centralized"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# VM Configuration
declare -A VMS=(
    ["vm1-frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["vm2-npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["vm3-redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["vm4-ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["vm5-browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check SSH key
    if [[ ! -f "$SSH_KEY" ]]; then
        log_error "SSH key not found at $SSH_KEY"
        exit 1
    fi

    # Check SSH connectivity to all VMs
    for vm_name in "${!VMS[@]}"; do
        vm_ip="${VMS[$vm_name]}"
        if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o BatchMode=yes "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "echo 'test'" &>/dev/null; then
            log_error "Cannot connect to $vm_name ($vm_ip)"
            exit 1
        fi
    done

    log_success "All VMs are accessible"
}

create_directory_structure() {
    log_info "Creating centralized logging directory structure..."

    # Create main centralized logging directory
    mkdir -p "$CENTRALIZED_DIR"

    # Create VM-specific directories
    for vm_name in "${!VMS[@]}"; do
        mkdir -p "$CENTRALIZED_DIR/$vm_name"
        mkdir -p "$CENTRALIZED_DIR/$vm_name/system"
        mkdir -p "$CENTRALIZED_DIR/$vm_name/application"
        mkdir -p "$CENTRALIZED_DIR/$vm_name/service"
        mkdir -p "$CENTRALIZED_DIR/$vm_name/archived"
    done

    # Create main machine directory
    mkdir -p "$CENTRALIZED_DIR/main-wsl"
    mkdir -p "$CENTRALIZED_DIR/main-wsl/backend"
    mkdir -p "$CENTRALIZED_DIR/main-wsl/system"
    mkdir -p "$CENTRALIZED_DIR/main-wsl/archived"

    # Create aggregated logs directory
    mkdir -p "$CENTRALIZED_DIR/aggregated"
    mkdir -p "$CENTRALIZED_DIR/aggregated/errors"
    mkdir -p "$CENTRALIZED_DIR/aggregated/warnings"
    mkdir -p "$CENTRALIZED_DIR/aggregated/info"

    log_success "Directory structure created"
}

setup_rsyslog_client() {
    local vm_name="$1"
    local vm_ip="$2"

    log_info "Setting up rsyslog client on $vm_name ($vm_ip)..."

    # Create rsyslog configuration for remote logging
    local rsyslog_config="/tmp/autobot-remote-logging.conf"
    cat > "$rsyslog_config" << EOF
# AutoBot Remote Logging Configuration
# Forward logs to main machine (${AUTOBOT_BACKEND_HOST})

# Forward all logs to main machine
*.*  @@${AUTOBOT_BACKEND_HOST}:514

# Also log locally for redundancy
*.*  /var/log/autobot-local.log

# Specific application logs
local0.*  @@${AUTOBOT_BACKEND_HOST}:514
local1.*  @@${AUTOBOT_BACKEND_HOST}:514
EOF

    # Copy configuration to VM
    scp -i "$SSH_KEY" "$rsyslog_config" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip":/tmp/

    # Install and configure rsyslog on VM
    ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
        sudo apt-get update -qq && sudo apt-get install -y rsyslog
        sudo cp /tmp/autobot-remote-logging.conf /etc/rsyslog.d/10-autobot-remote.conf
        sudo systemctl enable rsyslog
        sudo systemctl restart rsyslog
        sudo systemctl status rsyslog --no-pager
    "

    rm "$rsyslog_config"
    log_success "Rsyslog client configured on $vm_name"
}

setup_rsyslog_server() {
    log_info "Setting up rsyslog server on main machine..."

    # Create rsyslog server configuration
    local server_config="/tmp/autobot-rsyslog-server.conf"
    cat > "$server_config" << EOF
# AutoBot Centralized Logging Server Configuration

# Enable UDP and TCP reception
module(load="imudp")
input(type="imudp" port="514")

module(load="imtcp")
input(type="imtcp" port="514")

# Template for file naming based on source IP
template(name="AutoBotLogFile" type="string"
         string="$CENTRALIZED_DIR/%fromhost-ip%/system/%\$year%-%\$month%-%\$day%-syslog.log")

# Template for application logs
template(name="AutoBotAppLogFile" type="string"
         string="$CENTRALIZED_DIR/%fromhost-ip%/application/%\$year%-%\$month%-%\$day%-app.log")

# Rule to log remote messages
if \$fromhost-ip != '127.0.0.1' then {
    if \$syslogfacility-text == 'local0' or \$syslogfacility-text == 'local1' then {
        action(type="omfile" dynaFile="AutoBotAppLogFile")
    } else {
        action(type="omfile" dynaFile="AutoBotLogFile")
    }
    stop
}
EOF

    # Install rsyslog if not present
    if ! command -v rsyslogd &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y rsyslog
    fi

    # Copy configuration
    sudo cp "$server_config" /etc/rsyslog.d/10-autobot-server.conf

    # Restart rsyslog
    sudo systemctl enable rsyslog
    sudo systemctl restart rsyslog

    rm "$server_config"
    log_success "Rsyslog server configured on main machine"
}

setup_log_rotation() {
    log_info "Setting up log rotation..."

    local logrotate_config="/tmp/autobot-centralized-logrotate"
    cat > "$logrotate_config" << EOF
$CENTRALIZED_DIR/*/*.log $CENTRALIZED_DIR/*/*/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 kali kali
    postrotate
        /bin/systemctl reload rsyslog > /dev/null 2>&1 || true
    endscript
}

$LOGS_DIR/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 644 kali kali
}
EOF

    sudo cp "$logrotate_config" /etc/logrotate.d/autobot-centralized
    rm "$logrotate_config"

    log_success "Log rotation configured"
}

create_log_collection_scripts() {
    log_info "Creating log collection scripts..."

    # Create service-specific log collection script
    cat > "$SCRIPT_DIR/collect-service-logs.sh" << 'EOF'
#!/bin/bash

# AutoBot Service Log Collection Script
# Collects service-specific logs from all VMs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"

# VM Configuration
declare -A VMS=(
    ["vm1-frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["vm2-npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["vm3-redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["vm4-ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["vm5-browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

collect_service_logs() {
    local vm_name="$1"
    local vm_ip="$2"
    local timestamp=$(date +%Y%m%d_%H%M%S)

    echo "Collecting service logs from $vm_name ($vm_ip)..."

    # Collect journald logs for autobot services
    ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
        sudo journalctl -u 'autobot*' --since '1 hour ago' --no-pager
    " > "$CENTRALIZED_DIR/$vm_name/service/autobot-services-$timestamp.log" 2>/dev/null

    # Collect system service logs
    case "$vm_name" in
        "vm1-frontend")
            ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
                sudo journalctl -u nginx --since '1 hour ago' --no-pager
            " > "$CENTRALIZED_DIR/$vm_name/service/nginx-$timestamp.log" 2>/dev/null
            ;;
        "vm3-redis")
            ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
                sudo journalctl -u redis-stack-server --since '1 hour ago' --no-pager
            " > "$CENTRALIZED_DIR/$vm_name/service/redis-$timestamp.log" 2>/dev/null
            ;;
        "vm5-browser")
            ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
                sudo journalctl -u 'docker*' --since '1 hour ago' --no-pager
            " > "$CENTRALIZED_DIR/$vm_name/service/docker-$timestamp.log" 2>/dev/null
            ;;
    esac

    echo "Service logs collected from $vm_name"
}

# Collect from all VMs
for vm_name in "${!VMS[@]}"; do
    collect_service_logs "$vm_name" "${VMS[$vm_name]}"
done

echo "Service log collection completed at $(date)"
EOF

    chmod +x "$SCRIPT_DIR/collect-service-logs.sh"

    # Create application log collection script
    cat > "$SCRIPT_DIR/collect-application-logs.sh" << 'EOF'
#!/bin/bash

# AutoBot Application Log Collection Script
# Collects application-specific logs from all VMs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"

# VM Configuration with their application log paths
declare -A VM_LOG_PATHS=(
    ["vm1-frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:/var/log/nginx/*.log"
    ["vm2-npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:/home/autobot/logs/*.log"
    ["vm3-redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}:/var/log/redis/*.log"
    ["vm4-ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:/home/autobot/logs/*.log"
    ["vm5-browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:/home/autobot/logs/*.log"
)

collect_application_logs() {
    local vm_name="$1"
    local vm_ip_and_path="$2"
    local vm_ip="${vm_ip_and_path%%:*}"
    local log_path="${vm_ip_and_path#*:}"

    echo "Collecting application logs from $vm_name ($vm_ip)..."

    # Use rsync to collect log files
    rsync -avz -e "ssh -i $SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip":"$log_path" "$CENTRALIZED_DIR/$vm_name/application/" 2>/dev/null || echo "No application logs found for $vm_name"

    echo "Application logs collected from $vm_name"
}

# Collect from all VMs
for vm_name in "${!VM_LOG_PATHS[@]}"; do
    collect_application_logs "$vm_name" "${VM_LOG_PATHS[$vm_name]}"
done

# Collect main machine logs
echo "Collecting local logs..."
cp "$PROJECT_ROOT/logs"/*.log "$CENTRALIZED_DIR/main-wsl/backend/" 2>/dev/null || echo "No backend logs to copy"

echo "Application log collection completed at $(date)"
EOF

    chmod +x "$SCRIPT_DIR/collect-application-logs.sh"

    log_success "Log collection scripts created"
}

setup_cron_jobs() {
    log_info "Setting up automated log collection cron jobs..."

    # Add cron jobs for automated log collection
    (crontab -l 2>/dev/null; echo "# AutoBot Centralized Logging") | crontab -
    (crontab -l 2>/dev/null; echo "*/15 * * * * $SCRIPT_DIR/collect-service-logs.sh >> $LOGS_DIR/log-collection.log 2>&1") | crontab -
    (crontab -l 2>/dev/null; echo "0 * * * * $SCRIPT_DIR/collect-application-logs.sh >> $LOGS_DIR/log-collection.log 2>&1") | crontab -

    log_success "Cron jobs configured for automated log collection"
}

create_log_viewer() {
    log_info "Creating centralized log viewer script..."

    cat > "$SCRIPT_DIR/view-centralized-logs.sh" << 'EOF'
#!/bin/bash

# AutoBot Centralized Log Viewer
# Interactive log viewing interface for centralized logs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

show_menu() {
    clear
    echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
    echo -e "${CYAN}    AutoBot Centralized Log Viewer${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}Available VMs:${NC}"
    echo "1. VM1 - Frontend (${AUTOBOT_FRONTEND_HOST:-172.16.168.21})"
    echo "2. VM2 - NPU Worker (${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22})"
    echo "3. VM3 - Redis (${AUTOBOT_REDIS_HOST:-172.16.168.23})"
    echo "4. VM4 - AI Stack (${AUTOBOT_AI_STACK_HOST:-172.16.168.24})"
    echo "5. VM5 - Browser (${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25})"
    echo "6. Main WSL Machine"
    echo "7. View aggregated error logs"
    echo "8. Search all logs"
    echo "9. Show disk usage"
    echo "0. Exit"
    echo ""
    echo -n "Select option [0-9]: "
}

view_vm_logs() {
    local vm_dir="$1"
    local vm_name="$2"

    if [[ ! -d "$CENTRALIZED_DIR/$vm_dir" ]]; then
        echo -e "${RED}No logs found for $vm_name${NC}"
        return
    fi

    echo -e "${CYAN}Logs for $vm_name:${NC}"
    echo ""
    echo -e "${YELLOW}Log Types:${NC}"
    echo "1. System logs"
    echo "2. Application logs"
    echo "3. Service logs"
    echo "4. All logs (tail -f)"
    echo ""
    echo -n "Select log type [1-4]: "
    read -r log_type

    case $log_type in
        1)
            find "$CENTRALIZED_DIR/$vm_dir/system" -name "*.log" -exec tail -n 50 {} + 2>/dev/null | less
            ;;
        2)
            find "$CENTRALIZED_DIR/$vm_dir/application" -name "*.log" -exec tail -n 50 {} + 2>/dev/null | less
            ;;
        3)
            find "$CENTRALIZED_DIR/$vm_dir/service" -name "*.log" -exec tail -n 50 {} + 2>/dev/null | less
            ;;
        4)
            echo -e "${YELLOW}Press Ctrl+C to stop tailing logs${NC}"
            sleep 2
            find "$CENTRALIZED_DIR/$vm_dir" -name "*.log" -exec tail -f {} + 2>/dev/null
            ;;
    esac
}

search_logs() {
    echo -n "Enter search term: "
    read -r search_term

    if [[ -n "$search_term" ]]; then
        echo -e "${CYAN}Searching for '$search_term' in all logs...${NC}"
        grep -r -i --color=always "$search_term" "$CENTRALIZED_DIR/" | head -100
    fi
}

show_disk_usage() {
    echo -e "${CYAN}Centralized Logging Disk Usage:${NC}"
    du -h -d 2 "$CENTRALIZED_DIR" | sort -hr
}

# Main loop
while true; do
    show_menu
    read -r choice

    case $choice in
        1)
            view_vm_logs "vm1-frontend" "Frontend VM"
            ;;
        2)
            view_vm_logs "vm2-npu-worker" "NPU Worker VM"
            ;;
        3)
            view_vm_logs "vm3-redis" "Redis VM"
            ;;
        4)
            view_vm_logs "vm4-ai-stack" "AI Stack VM"
            ;;
        5)
            view_vm_logs "vm5-browser" "Browser VM"
            ;;
        6)
            view_vm_logs "main-wsl" "Main WSL Machine"
            ;;
        7)
            find "$CENTRALIZED_DIR" -name "*error*" -o -name "*Error*" -exec tail -n 20 {} + 2>/dev/null | less
            ;;
        8)
            search_logs
            ;;
        9)
            show_disk_usage
            ;;
        0)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option${NC}"
            sleep 1
            ;;
    esac

    echo ""
    echo -n "Press Enter to continue..."
    read -r
done
EOF

    chmod +x "$SCRIPT_DIR/view-centralized-logs.sh"

    log_success "Log viewer created at $SCRIPT_DIR/view-centralized-logs.sh"
}

main() {
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo -e "${BLUE}    AutoBot Centralized Logging Setup${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo ""

    check_prerequisites
    create_directory_structure
    setup_rsyslog_server

    # Setup clients on each VM
    for vm_name in "${!VMS[@]}"; do
        setup_rsyslog_client "$vm_name" "${VMS[$vm_name]}"
    done

    setup_log_rotation
    create_log_collection_scripts
    setup_cron_jobs
    create_log_viewer

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
    echo -e "${GREEN}    Centralized Logging Setup Complete!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${CYAN}Available Commands:${NC}"
    echo "  View logs: $SCRIPT_DIR/view-centralized-logs.sh"
    echo "  Collect service logs: $SCRIPT_DIR/collect-service-logs.sh"
    echo "  Collect app logs: $SCRIPT_DIR/collect-application-logs.sh"
    echo ""
    echo -e "${CYAN}Centralized logs location:${NC} $CENTRALIZED_DIR"
    echo -e "${CYAN}Automated collection:${NC} Every 15 minutes (services), hourly (applications)"
    echo ""
}

# Check if running as main script
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
