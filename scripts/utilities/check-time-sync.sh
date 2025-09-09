#!/bin/bash

# Simple time sync check for multi-VM infrastructure
# Monitors time differences across all reachable VMs

# Load unified configuration system
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." &> /dev/null && pwd)"
if [[ -f "${SCRIPT_DIR}/config/load_config.sh" ]]; then
    export PATH="$HOME/bin:$PATH"  # Ensure yq is available
    source "${SCRIPT_DIR}/config/load_config.sh"
    echo -e "\033[0;32m✓ Loaded unified configuration system\033[0m"
else
    echo -e "\033[0;31m✗ Warning: Unified configuration not found, using fallback values\033[0m"
fi

echo "AutoBot Multi-VM Time Check"
echo "==========================="

declare -A VMS=(
    ["vm0-backend"]=$(get_config "infrastructure.hosts.backend" 2>/dev/null || echo "172.16.168.20")
    ["vm1-frontend"]=$(get_config "infrastructure.hosts.frontend" 2>/dev/null || echo "172.16.168.21")
    ["vm2-npu-worker"]=$(get_config "infrastructure.hosts.npu_worker" 2>/dev/null || echo "172.16.168.22")
    ["vm3-redis"]=$(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23")
    ["vm4-ai-stack"]=$(get_config "infrastructure.hosts.ai_stack" 2>/dev/null || echo "172.16.168.24")
    ["vm5-browser"]=$(get_config "infrastructure.hosts.browser_service" 2>/dev/null || echo "172.16.168.25")
)

echo "Checking time on all VMs (UTC):"
echo ""

# Get current time in UTC seconds for comparison
base_time=$(date -u +%s)

for vm_name in "${!VMS[@]}"; do
    vm_ip="${VMS[$vm_name]}"
    
    backend_host=$(get_config "infrastructure.hosts.backend" 2>/dev/null || echo "172.16.168.20")
    if [ "$vm_ip" == "$backend_host" ]; then
        # Local VM
        vm_time=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
        vm_seconds=$(date -u +%s)
        diff_seconds=$((vm_seconds - base_time))
        echo "✓ $vm_name (LOCAL): $vm_time [+${diff_seconds}s]"
    else
        # Remote VM - try to ping first
        if ping -c 1 -W 2 "$vm_ip" >/dev/null 2>&1; then
            vm_time=$(ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no "kali@$vm_ip" 'date -u "+%Y-%m-%d %H:%M:%S UTC %s"' 2>/dev/null)
            if [ $? -eq 0 ]; then
                vm_datetime=$(echo "$vm_time" | cut -d' ' -f1-3)
                vm_seconds=$(echo "$vm_time" | awk '{print $4}')
                diff_seconds=$((vm_seconds - base_time))
                if [ ${diff_seconds#-} -gt 5 ]; then
                    echo "⚠ $vm_name ($vm_ip): $vm_datetime [${diff_seconds}s DRIFT]"
                else
                    echo "✓ $vm_name ($vm_ip): $vm_datetime [${diff_seconds}s]"
                fi
            else
                echo "✗ $vm_name ($vm_ip): SSH connection failed"
            fi
        else
            echo "✗ $vm_name ($vm_ip): Unreachable"
        fi
    fi
done

echo ""
echo "Time sync recommendations:"
echo "- Drift > 5s requires attention"
echo "- Use 'sudo timedatectl set-ntp true' on VMs with large drift"