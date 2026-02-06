#!/bin/bash

# AutoBot Application Log Collection Script
# Collects application-specific logs from all VMs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"
SSH_KEY="$HOME/.ssh/autobot_key"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

# VM Configuration with their application log paths
declare -A VMS=(
    ["vm1-frontend"]="172.16.168.21"
    ["vm2-npu-worker"]="172.16.168.22"
    ["vm3-redis"]="172.16.168.23"
    ["vm4-ai-stack"]="172.16.168.24"
    ["vm5-browser"]="172.16.168.25"
)

collect_application_logs() {
    local vm_name="$1"
    local vm_ip="$2"
    local timestamp=$(date +%Y%m%d_%H%M%S)

    echo -e "${CYAN}Collecting application logs from $vm_name ($vm_ip)...${NC}"

    # Try to collect application logs from common locations
    ssh -i "$SSH_KEY" autobot@"$vm_ip" "
        echo 'Searching for application logs...'

        # Look for logs in home directory
        find /home/autobot -name '*.log' -type f -mtime -1 2>/dev/null | head -20

        # Look for logs in common application directories
        find /opt -name '*.log' -type f -readable -mtime -1 2>/dev/null | head -10
        find /var/log -name '*.log' -type f -readable -mtime -1 2>/dev/null | head -10

        # Collect specific application logs
        echo '--- Application-specific logs ---'
    " > "$CENTRALIZED_DIR/$vm_name/application/app-search-$timestamp.log" 2>/dev/null

    # Collect readable log files
    ssh -i "$SSH_KEY" autobot@"$vm_ip" "
        # Copy readable log files from home directory
        for log_file in \$(find /home/autobot -name '*.log' -type f -mtime -1 2>/dev/null); do
            if [[ -r \"\$log_file\" ]]; then
                echo \"=== \$log_file ===\"
                tail -n 50 \"\$log_file\"
                echo
            fi
        done
    " > "$CENTRALIZED_DIR/$vm_name/application/home-logs-$timestamp.log" 2>/dev/null

    # VM-specific application log collection
    case "$vm_name" in
        "vm1-frontend")
            ssh -i "$SSH_KEY" autobot@"$vm_ip" "
                # Vue.js application logs
                echo '--- Vue.js build logs ---'
                find /home/autobot -name 'npm-debug.log' -o -name 'yarn-error.log' 2>/dev/null | xargs cat 2>/dev/null || echo 'No Vue.js build logs found'

                # Nginx access logs (if readable)
                echo '--- Web server access logs (last 100 lines) ---'
                tail -n 100 /var/log/nginx/access.log 2>/dev/null || echo 'Nginx access log not readable'
            " > "$CENTRALIZED_DIR/$vm_name/application/frontend-app-$timestamp.log" 2>/dev/null
            ;;
        "vm3-redis")
            ssh -i "$SSH_KEY" autobot@"$vm_ip" "
                # Redis application data
                echo '--- Redis database info ---'
                redis-cli info keyspace 2>/dev/null || echo 'Redis not accessible'

                echo '--- Redis memory usage ---'
                redis-cli info memory 2>/dev/null || echo 'Redis memory info not accessible'

                echo '--- Redis client connections ---'
                redis-cli info clients 2>/dev/null || echo 'Redis client info not accessible'
            " > "$CENTRALIZED_DIR/$vm_name/application/redis-data-$timestamp.log" 2>/dev/null
            ;;
        "vm4-ai-stack")
            ssh -i "$SSH_KEY" autobot@"$vm_ip" "
                # AI application logs
                echo '--- Python application logs ---'
                find /home/autobot -name '*.log' -path '*/python*' -o -path '*/ai*' -o -path '*/ml*' 2>/dev/null | xargs tail -n 20 2>/dev/null || echo 'No AI application logs found'

                echo '--- API server logs ---'
                ps aux | grep -i 'uvicorn\|fastapi\|flask\|python.*api' | grep -v grep || echo 'No API server processes found'
            " > "$CENTRALIZED_DIR/$vm_name/application/ai-app-$timestamp.log" 2>/dev/null
            ;;
        "vm5-browser")
            ssh -i "$SSH_KEY" autobot@"$vm_ip" "
                # Browser automation logs
                echo '--- Playwright logs ---'
                find /home/autobot -name '*playwright*' -name '*.log' 2>/dev/null | xargs tail -n 50 2>/dev/null || echo 'No Playwright logs found'

                echo '--- VNC session logs ---'
                find /tmp -name '*vnc*' -name '*.log' 2>/dev/null | xargs tail -n 20 2>/dev/null || echo 'No VNC logs found'

                echo '--- Desktop session logs ---'
                find /home/autobot/.cache -name '*.log' 2>/dev/null | head -5 | xargs tail -n 10 2>/dev/null || echo 'No desktop session logs found'
            " > "$CENTRALIZED_DIR/$vm_name/application/browser-app-$timestamp.log" 2>/dev/null
            ;;
        "vm2-npu-worker")
            ssh -i "$SSH_KEY" autobot@"$vm_ip" "
                # NPU worker application logs
                echo '--- AI inference logs ---'
                find /home/autobot -name '*inference*' -name '*.log' 2>/dev/null | xargs tail -n 30 2>/dev/null || echo 'No inference logs found'

                echo '--- OpenVINO logs ---'
                find /opt/intel -name '*.log' -readable 2>/dev/null | head -3 | xargs tail -n 20 2>/dev/null || echo 'No OpenVINO logs accessible'

                echo '--- Hardware acceleration logs ---'
                dmesg | grep -i 'intel\|gpu\|npu' | tail -10 2>/dev/null || echo 'No hardware acceleration logs in dmesg'
            " > "$CENTRALIZED_DIR/$vm_name/application/npu-app-$timestamp.log" 2>/dev/null
            ;;
    esac

    # Try to use rsync for any additional log files (non-blocking)
    rsync -avz --timeout=10 -e "ssh -i $SSH_KEY -o ConnectTimeout=5" \
        autobot@"$vm_ip":/home/autobot/logs/ \
        "$CENTRALIZED_DIR/$vm_name/application/" 2>/dev/null || echo "Rsync to $vm_name not available"

    echo -e "${GREEN}Application logs collected from $vm_name${NC}"
}

# Create summary of collection
echo -e "${YELLOW}AutoBot Application Log Collection - $(date)${NC}"
echo "========================================================="

# Collect from all VMs
for vm_name in "${!VMS[@]}"; do
    collect_application_logs "$vm_name" "${VMS[$vm_name]}"
done

# Collect main machine logs
echo -e "${CYAN}Collecting local backend and system logs...${NC}"
cp "$PROJECT_ROOT/logs"/*.log "$CENTRALIZED_DIR/main-wsl/application/" 2>/dev/null || echo "No backend logs to copy"

# Copy recent system logs to main-wsl
dmesg | tail -100 > "$CENTRALIZED_DIR/main-wsl/system/dmesg-$(date +%Y%m%d_%H%M%S).log" 2>/dev/null
journalctl --user --since "1 hour ago" --no-pager > "$CENTRALIZED_DIR/main-wsl/system/user-journal-$(date +%Y%m%d_%H%M%S).log" 2>/dev/null

echo ""
echo -e "${GREEN}Application log collection completed at $(date)${NC}"
echo "Logs stored in: $CENTRALIZED_DIR"
echo ""
echo -e "${CYAN}Log summary:${NC}"
find "$CENTRALIZED_DIR" -name "*.log" -type f -printf "%TY-%Tm-%Td %TH:%TM  %p\n" | sort | tail -20
