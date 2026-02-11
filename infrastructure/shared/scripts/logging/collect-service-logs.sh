#!/bin/bash

# AutoBot Service Log Collection Script
# Collects service-specific logs from all VMs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

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

    echo -e "${CYAN}Collecting service logs from $vm_name ($vm_ip)...${NC}"

    # Collect journald logs for autobot services (without sudo)
    ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
        journalctl --user -u 'autobot*' --since '1 hour ago' --no-pager 2>/dev/null || echo 'No user autobot services found'
        journalctl --user --since '1 hour ago' --no-pager | grep -i autobot 2>/dev/null || echo 'No autobot-related logs in user journal'
    " > "$CENTRALIZED_DIR/$vm_name/service/autobot-services-$timestamp.log" 2>/dev/null

    # Collect available system logs (what we can access without sudo)
    ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
        # Get process information for autobot services
        ps aux | grep -i autobot | grep -v grep || echo 'No autobot processes found'
        echo '--- Docker containers ---'
        docker ps 2>/dev/null || echo 'Docker not accessible or not running'
        echo '--- System uptime ---'
        uptime
        echo '--- Memory usage ---'
        free -h
        echo '--- Disk usage ---'
        df -h
    " > "$CENTRALIZED_DIR/$vm_name/system/system-info-$timestamp.log" 2>/dev/null

    # Collect service-specific logs based on VM type
    case "$vm_name" in
        "vm1-frontend")
            ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
                # Nginx access logs if readable
                tail -n 100 /var/log/nginx/access.log 2>/dev/null || echo 'Nginx access log not accessible'
                echo '--- Nginx error log ---'
                tail -n 100 /var/log/nginx/error.log 2>/dev/null || echo 'Nginx error log not accessible'
                echo '--- Vue.js dev server (if running) ---'
                ps aux | grep -i 'npm\|yarn\|node.*vue' | grep -v grep || echo 'No Vue.js processes found'
            " > "$CENTRALIZED_DIR/$vm_name/service/nginx-$timestamp.log" 2>/dev/null
            ;;
        "vm3-redis")
            ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
                # Redis logs if accessible
                tail -n 100 /var/log/redis/redis-server.log 2>/dev/null || echo 'Redis log not accessible via file'
                echo '--- Redis info ---'
                redis-cli info 2>/dev/null || echo 'Redis CLI not accessible'
                echo '--- Redis process ---'
                ps aux | grep redis | grep -v grep || echo 'No Redis processes found'
            " > "$CENTRALIZED_DIR/$vm_name/service/redis-$timestamp.log" 2>/dev/null
            ;;
        "vm5-browser")
            ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
                # Docker logs if accessible
                docker logs autobot-playwright --tail 100 2>/dev/null || echo 'Playwright container logs not accessible'
                echo '--- VNC processes ---'
                ps aux | grep -i vnc | grep -v grep || echo 'No VNC processes found'
                echo '--- Desktop environment ---'
                ps aux | grep -i 'xfce\|desktop' | grep -v grep || echo 'No desktop processes found'
            " > "$CENTRALIZED_DIR/$vm_name/service/browser-$timestamp.log" 2>/dev/null
            ;;
        "vm2-npu-worker")
            ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
                # NPU and AI workload information
                echo '--- Intel GPU info ---'
                intel_gpu_top -l 2>/dev/null || echo 'Intel GPU tools not available'
                echo '--- AI processes ---'
                ps aux | grep -i 'python.*ai\|openvino\|inference' | grep -v grep || echo 'No AI processes found'
            " > "$CENTRALIZED_DIR/$vm_name/service/npu-worker-$timestamp.log" 2>/dev/null
            ;;
        "vm4-ai-stack")
            ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "
                # AI stack processes
                echo '--- Python AI processes ---'
                ps aux | grep -i 'python.*api\|flask\|fastapi\|uvicorn' | grep -v grep || echo 'No Python API processes found'
                echo '--- GPU usage ---'
                nvidia-smi 2>/dev/null || echo 'NVIDIA tools not available'
            " > "$CENTRALIZED_DIR/$vm_name/service/ai-stack-$timestamp.log" 2>/dev/null
            ;;
    esac

    echo -e "${GREEN}Service logs collected from $vm_name${NC}"
}

# Create summary of collection
echo -e "${YELLOW}AutoBot Service Log Collection - $(date)${NC}"
echo "======================================================"

# Collect from all VMs
for vm_name in "${!VMS[@]}"; do
    collect_service_logs "$vm_name" "${VMS[$vm_name]}"
done

# Collect local backend logs
echo -e "${CYAN}Collecting local backend logs...${NC}"
cp "$PROJECT_ROOT/logs"/*.log "$CENTRALIZED_DIR/main-wsl/service/" 2>/dev/null || echo "No backend logs to copy"

echo ""
echo -e "${GREEN}Service log collection completed at $(date)${NC}"
echo "Logs stored in: $CENTRALIZED_DIR"
