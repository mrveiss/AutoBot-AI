#!/bin/bash

# Time Synchronization Script for Multi-VM Infrastructure
# Ensures all VMs have synchronized time for AutoBot operation

set -e

# Load unified configuration system
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." &> /dev/null && pwd)"
if [[ -f "${SCRIPT_DIR}/config/load_config.sh" ]]; then
    export PATH="$HOME/bin:$PATH"  # Ensure yq is available
    source "${SCRIPT_DIR}/config/load_config.sh"
    echo -e "\033[0;32m✓ Loaded unified configuration system\033[0m"
else
    echo -e "\033[0;31m✗ Warning: Unified configuration not found, using fallback values\033[0m"
fi

# VM configuration (from unified config)
declare -A VMS=(
    ["vm0-backend"]=$(get_config "infrastructure.hosts.backend" 2>/dev/null || echo "172.16.168.20")
    ["vm1-frontend"]=$(get_config "infrastructure.hosts.frontend" 2>/dev/null || echo "172.16.168.21")
    ["vm2-npu-worker"]=$(get_config "infrastructure.hosts.npu_worker" 2>/dev/null || echo "172.16.168.22")
    ["vm3-redis"]=$(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23")
    ["vm4-ai-stack"]=$(get_config "infrastructure.hosts.ai_stack" 2>/dev/null || echo "172.16.168.24")
    ["vm5-browser"]=$(get_config "infrastructure.hosts.browser_service" 2>/dev/null || echo "172.16.168.25")
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}AutoBot Multi-VM Time Synchronization${NC}"
echo "========================================"

# Function to execute command on remote VM
execute_on_vm() {
    local vm_name="$1"
    local vm_ip="$2" 
    local command="$3"
    local description="$4"
    
    echo -e "${YELLOW}[$vm_name] $description${NC}"
    
    if [ "$vm_ip" == "172.16.168.20" ]; then
        # Local VM (current)
        echo "  → Executing locally"
        eval "$command"
    else
        # Remote VM
        echo "  → Executing on $vm_ip"
        ssh -o ConnectTimeout=5 "kali@$vm_ip" "$command" 2>/dev/null || {
            echo -e "${RED}  → Failed to connect to $vm_name ($vm_ip)${NC}"
            return 1
        }
    fi
}

# Function to check VM connectivity
check_vm_connectivity() {
    local vm_name="$1"
    local vm_ip="$2"
    
    if [ "$vm_ip" == "172.16.168.20" ]; then
        echo -e "${GREEN}  → $vm_name: Local VM (reachable)${NC}"
        return 0
    fi
    
    if ping -c 1 -W 2 "$vm_ip" >/dev/null 2>&1; then
        echo -e "${GREEN}  → $vm_name: Reachable${NC}"
        return 0
    else
        echo -e "${RED}  → $vm_name: Unreachable${NC}"
        return 1
    fi
}

# Function to get current time info
get_time_info() {
    local vm_name="$1"
    local vm_ip="$2"
    
    local time_cmd="date '+%Y-%m-%d %H:%M:%S %Z' && timedatectl status | grep -E '(System clock|NTP service)'"
    
    if [ "$vm_ip" == "172.16.168.20" ]; then
        echo "Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
        timedatectl status | grep -E "(System clock|NTP service)" | sed 's/^/  /'
    else
        ssh -o ConnectTimeout=5 "kali@$vm_ip" "$time_cmd" 2>/dev/null | sed 's/^/  /' || {
            echo -e "${RED}  → Failed to get time info${NC}"
        }
    fi
}

# Function to install and configure NTP
setup_ntp() {
    local vm_name="$1"
    local vm_ip="$2"
    
    local ntp_cmd="
        # Install chrony if not present
        if ! command -v chrony >/dev/null 2>&1; then
            sudo apt-get update -qq && sudo apt-get install -y chrony >/dev/null 2>&1
        fi
        
        # Configure chrony with reliable NTP servers
        sudo tee /etc/chrony/chrony.conf > /dev/null <<EOF
# NTP Servers (reliable public servers)
server 0.pool.ntp.org iburst
server 1.pool.ntp.org iburst
server 2.pool.ntp.org iburst
server 3.pool.ntp.org iburst

# Fallback servers
server time.cloudflare.com iburst
server time.google.com iburst

# Allow synchronization even with large time differences
makestep 1.0 3

# Local network synchronization (VM0 as reference)
server 172.16.168.20 minpoll 4 maxpoll 6

# Log directory
driftfile /var/lib/chrony/chrony.drift
logdir /var/log/chrony

# Enable kernel synchronization
rtcsync

# Allow other VMs to sync from this one
allow 172.16.168.0/24

# Step threshold
maxupdateskew 100.0
EOF

        # Restart and enable chrony
        sudo systemctl restart chrony
        sudo systemctl enable chrony
        
        # Force immediate synchronization
        sudo chrony sources -v
        sudo chronyc makestep
        
        echo 'NTP setup completed'
    "
    
    execute_on_vm "$vm_name" "$vm_ip" "$ntp_cmd" "Setting up NTP synchronization"
}

# Function to synchronize time
sync_time() {
    local vm_name="$1"
    local vm_ip="$2"
    
    local sync_cmd="
        # Force time synchronization
        sudo chronyc makestep 2>/dev/null || echo 'Chrony not available'
        sudo systemctl restart systemd-timesyncd 2>/dev/null || echo 'timesyncd not available'
        
        # Manual NTP sync as fallback
        if command -v ntpdate >/dev/null 2>&1; then
            sudo ntpdate -s time.nist.gov 2>/dev/null || echo 'ntpdate failed'
        fi
        
        echo 'Time sync attempted'
    "
    
    execute_on_vm "$vm_name" "$vm_ip" "$sync_cmd" "Synchronizing time"
}

echo -e "\n${BLUE}Step 1: Checking VM Connectivity${NC}"
echo "=================================="

reachable_vms=()
for vm_name in "${!VMS[@]}"; do
    vm_ip="${VMS[$vm_name]}"
    if check_vm_connectivity "$vm_name" "$vm_ip"; then
        reachable_vms+=("$vm_name:$vm_ip")
    fi
done

echo -e "\n${BLUE}Step 2: Current Time Status${NC}"
echo "============================"

echo -e "${YELLOW}Checking current time on all reachable VMs:${NC}"
for vm_info in "${reachable_vms[@]}"; do
    IFS=':' read -r vm_name vm_ip <<< "$vm_info"
    echo -e "\n${GREEN}[$vm_name - $vm_ip]${NC}"
    get_time_info "$vm_name" "$vm_ip"
done

echo -e "\n${BLUE}Step 3: Installing/Configuring NTP${NC}"
echo "=================================="

for vm_info in "${reachable_vms[@]}"; do
    IFS=':' read -r vm_name vm_ip <<< "$vm_info"
    echo -e "\n${GREEN}[$vm_name - $vm_ip]${NC}"
    setup_ntp "$vm_name" "$vm_ip"
done

echo -e "\n${BLUE}Step 4: Force Time Synchronization${NC}"
echo "=================================="

for vm_info in "${reachable_vms[@]}"; do
    IFS=':' read -r vm_name vm_ip <<< "$vm_info"
    echo -e "\n${GREEN}[$vm_name - $vm_ip]${NC}"
    sync_time "$vm_name" "$vm_ip"
done

# Wait a moment for sync to complete
echo -e "\n${YELLOW}Waiting 5 seconds for synchronization to complete...${NC}"
sleep 5

echo -e "\n${BLUE}Step 5: Final Time Verification${NC}"
echo "==============================="

echo -e "${YELLOW}Final time status on all VMs:${NC}"
for vm_info in "${reachable_vms[@]}"; do
    IFS=':' read -r vm_name vm_ip <<< "$vm_info"
    echo -e "\n${GREEN}[$vm_name - $vm_ip]${NC}"
    get_time_info "$vm_name" "$vm_ip"
done

echo -e "\n${GREEN}Time synchronization process completed!${NC}"
echo ""
echo "All reachable VMs now have NTP configured and time synchronized."
echo "Chrony will maintain synchronization automatically."
echo ""
echo "To manually check sync status: sudo chronyc sources -v"
echo "To force resync: sudo chronyc makestep"