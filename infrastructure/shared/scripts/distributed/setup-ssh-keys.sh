#!/bin/bash
# Setup SSH keys for passwordless access to distributed AutoBot VMs

# Load SSOT configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

echo "🔑 Setting up SSH keys for distributed AutoBot access..."

# Generate SSH key for AutoBot distributed access
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_distributed}"
if [ ! -f "$SSH_KEY" ]; then
    echo "Generating SSH key pair for AutoBot distributed access..."
    ssh-keygen -t rsa -b 4096 -f "$SSH_KEY" -N "" -C "autobot-distributed-$(whoami)@$(hostname)"
    echo "✅ SSH key generated: $SSH_KEY"
fi

# VM list (from SSOT)
VMS=(
    "${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:frontend"
    "${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:npu-worker"
    "${AUTOBOT_REDIS_HOST:-172.16.168.23}:redis"
    "${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:ai-stack"
    "${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:browser"
)

echo ""
echo "🌐 Setting up SSH access to remote VMs..."
echo "Note: You will be prompted for passwords for each VM"

for vm_entry in "${VMS[@]}"; do
    IFS=':' read -r vm_ip vm_name <<< "$vm_entry"
    echo ""
    echo "Setting up access to $vm_name ($vm_ip)..."

    # Copy SSH key to remote VM
    if ssh-copy-id -i "$SSH_KEY.pub" "kali@$vm_ip" 2>/dev/null; then
        echo "✅ SSH key copied to $vm_name"

        # Test passwordless access
        if ssh -i "$SSH_KEY" -o BatchMode=yes "kali@$vm_ip" "echo 'SSH test successful'" 2>/dev/null; then
            echo "✅ Passwordless access confirmed to $vm_name"
        else
            echo "⚠️  Passwordless access test failed for $vm_name"
        fi
    else
        echo "❌ Failed to copy SSH key to $vm_name"
        echo "   Make sure the VM is accessible and SSH is enabled"
    fi
done

# Update SSH config
echo ""
echo "📝 Updating SSH config..."
SSH_CONFIG="$HOME/.ssh/config"

# Backup existing config
[ -f "$SSH_CONFIG" ] && cp "$SSH_CONFIG" "${SSH_CONFIG}.backup.$(date +%s)"

# Add AutoBot distributed access configuration
cat >> "$SSH_CONFIG" << SSHCONFIG

# AutoBot Distributed Infrastructure
Host autobot-frontend
    HostName ${AUTOBOT_FRONTEND_HOST:-172.16.168.21}
    User kali
    IdentityFile ${SSH_KEY}
    StrictHostKeyChecking no

Host autobot-npu-worker
    HostName ${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}
    User kali
    IdentityFile ${SSH_KEY}
    StrictHostKeyChecking no

Host autobot-redis
    HostName ${AUTOBOT_REDIS_HOST:-172.16.168.23}
    User kali
    IdentityFile ${SSH_KEY}
    StrictHostKeyChecking no

Host autobot-ai-stack
    HostName ${AUTOBOT_AI_STACK_HOST:-172.16.168.24}
    User kali
    IdentityFile ${SSH_KEY}
    StrictHostKeyChecking no

Host autobot-browser
    HostName ${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}
    User kali
    IdentityFile ${SSH_KEY}
    StrictHostKeyChecking no
SSHCONFIG

echo "✅ SSH config updated with AutoBot VM aliases"
echo ""
echo "🎉 SSH setup complete! You can now access VMs using:"
echo "  ssh autobot-frontend    # Frontend VM (${AUTOBOT_FRONTEND_HOST:-172.16.168.21})"
echo "  ssh autobot-npu-worker  # NPU Worker VM (${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22})"
echo "  ssh autobot-redis       # Redis VM (${AUTOBOT_REDIS_HOST:-172.16.168.23})"
echo "  ssh autobot-ai-stack    # AI Stack VM (${AUTOBOT_AI_STACK_HOST:-172.16.168.24})"
echo "  ssh autobot-browser     # Browser VM (${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25})"
