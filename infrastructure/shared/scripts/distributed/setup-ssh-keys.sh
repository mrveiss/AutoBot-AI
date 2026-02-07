#!/bin/bash
# Setup SSH keys for passwordless access to distributed AutoBot VMs

echo "🔑 Setting up SSH keys for distributed AutoBot access..."

# Generate SSH key for AutoBot distributed access
SSH_KEY="$HOME/.ssh/autobot_distributed"
if [ ! -f "$SSH_KEY" ]; then
    echo "Generating SSH key pair for AutoBot distributed access..."
    ssh-keygen -t rsa -b 4096 -f "$SSH_KEY" -N "" -C "autobot-distributed-$(whoami)@$(hostname)"
    echo "✅ SSH key generated: $SSH_KEY"
fi

# VM list
VMS=(
    "172.16.168.21:frontend"
    "172.16.168.22:npu-worker"
    "172.16.168.23:redis"
    "172.16.168.24:ai-stack"
    "172.16.168.25:browser"
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
cat >> "$SSH_CONFIG" << 'SSHCONFIG'

# AutoBot Distributed Infrastructure
Host autobot-frontend
    HostName 172.16.168.21
    User kali
    IdentityFile ~/.ssh/autobot_distributed
    StrictHostKeyChecking no

Host autobot-npu-worker
    HostName 172.16.168.22
    User kali
    IdentityFile ~/.ssh/autobot_distributed
    StrictHostKeyChecking no

Host autobot-redis
    HostName 172.16.168.23
    User kali
    IdentityFile ~/.ssh/autobot_distributed
    StrictHostKeyChecking no

Host autobot-ai-stack
    HostName 172.16.168.24
    User kali
    IdentityFile ~/.ssh/autobot_distributed
    StrictHostKeyChecking no

Host autobot-browser
    HostName 172.16.168.25
    User kali
    IdentityFile ~/.ssh/autobot_distributed
    StrictHostKeyChecking no
SSHCONFIG

echo "✅ SSH config updated with AutoBot VM aliases"
echo ""
echo "🎉 SSH setup complete! You can now access VMs using:"
echo "  ssh autobot-frontend    # Frontend VM (172.16.168.21)"
echo "  ssh autobot-npu-worker  # NPU Worker VM (172.16.168.22)"
echo "  ssh autobot-redis       # Redis VM (172.16.168.23)"
echo "  ssh autobot-ai-stack    # AI Stack VM (172.16.168.24)"
echo "  ssh autobot-browser     # Browser VM (172.16.168.25)"
