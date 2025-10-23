#!/bin/bash
# Deploy service keys to all VMs
# Phase 2 of Day 3 Implementation

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Day 3 Phase 2: Service Key Distribution${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

# Service-to-VM mapping
declare -A VM_MAP
VM_MAP["main-backend"]="172.16.168.20"
VM_MAP["frontend"]="172.16.168.21"
VM_MAP["npu-worker"]="172.16.168.22"
VM_MAP["redis-stack"]="172.16.168.23"
VM_MAP["ai-stack"]="172.16.168.24"
VM_MAP["browser-service"]="172.16.168.25"

SSH_KEY="$HOME/.ssh/autobot_key"
SOURCE_DIR="/tmp/service-keys"

deploy_to_vm() {
    local service_id=$1
    local vm_ip=$2
    local key_file="${SOURCE_DIR}/${service_id}.env"

    echo -e "${YELLOW}Deploying to ${service_id} (${vm_ip})...${NC}"

    # Check if key file exists
    if [ ! -f "$key_file" ]; then
        echo -e "${RED}  ❌ Key file not found: ${key_file}${NC}"
        return 1
    fi

    # Create directory on VM
    ssh -i "$SSH_KEY" autobot@${vm_ip} \
        "sudo mkdir -p /etc/autobot/service-keys && \
         sudo chown autobot:autobot /etc/autobot/service-keys && \
         sudo chmod 700 /etc/autobot/service-keys" 2>/dev/null

    if [ $? -ne 0 ]; then
        echo -e "${RED}  ❌ Failed to create directory on ${vm_ip}${NC}"
        return 1
    fi

    # Copy file to temp location then move to final location
    scp -i "$SSH_KEY" "$key_file" autobot@${vm_ip}:/tmp/${service_id}.env 2>/dev/null

    if [ $? -ne 0 ]; then
        echo -e "${RED}  ❌ Failed to copy file to ${vm_ip}${NC}"
        return 1
    fi

    # Move to final location and set permissions
    ssh -i "$SSH_KEY" autobot@${vm_ip} \
        "sudo mv /tmp/${service_id}.env /etc/autobot/service-keys/${service_id}.env && \
         sudo chown autobot:autobot /etc/autobot/service-keys/${service_id}.env && \
         sudo chmod 600 /etc/autobot/service-keys/${service_id}.env" 2>/dev/null

    if [ $? -ne 0 ]; then
        echo -e "${RED}  ❌ Failed to set permissions on ${vm_ip}${NC}"
        return 1
    fi

    # Verify deployment
    local file_check=$(ssh -i "$SSH_KEY" autobot@${vm_ip} \
        "test -f /etc/autobot/service-keys/${service_id}.env && echo 'exists'" 2>/dev/null)

    if [ "$file_check" = "exists" ]; then
        echo -e "${GREEN}  ✅ Deployed successfully to ${service_id}${NC}"
        return 0
    else
        echo -e "${RED}  ❌ Verification failed for ${vm_ip}${NC}"
        return 1
    fi
}

# Deploy to all VMs
success_count=0
fail_count=0

for service_id in "${!VM_MAP[@]}"; do
    vm_ip="${VM_MAP[$service_id]}"

    if deploy_to_vm "$service_id" "$vm_ip"; then
        ((success_count++))
    else
        ((fail_count++))
    fi
    echo ""
done

# Summary
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Deployment Summary${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Total VMs: 6"
echo -e "  ${GREEN}Successful: ${success_count}${NC}"
if [ $fail_count -gt 0 ]; then
    echo -e "  ${RED}Failed: ${fail_count}${NC}"
fi
echo ""

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}✅ All service keys deployed successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Verify deployments: bash scripts/verify-service-keys.sh"
    echo "  2. Proceed to Phase 3: Service configuration update"
    exit 0
else
    echo -e "${RED}❌ Some deployments failed. Please review errors above.${NC}"
    exit 1
fi
