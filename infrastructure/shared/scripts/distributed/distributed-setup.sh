#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# AutoBot Distributed Architecture Setup
# Configures the main WSL machine to coordinate with remote VMs

set -e

# =============================================================================
# SSOT Configuration - Issue #694
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/ssot-config.sh" 2>/dev/null || source "$SCRIPT_DIR/lib/ssot-config.sh" 2>/dev/null || {
    # Fallback if lib not found
    PROJECT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
    [ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }
}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}AutoBot Distributed Architecture Setup${NC}"
echo -e "${BLUE}Main WSL Coordinator: ${AUTOBOT_BACKEND_HOST:-172.16.168.20}${NC}"
echo ""

# Define remote VMs using SSOT configuration
declare -A REMOTE_VMS=(
    ["redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}:${AUTOBOT_REDIS_PORT:-6379}"
    ["npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:${AUTOBOT_NPU_WORKER_PORT:-8081}"
    ["frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}"
    ["ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:${AUTOBOT_AI_STACK_PORT:-8080}"
    ["browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"
)

echo -e "${CYAN}Testing Remote VM Connectivity...${NC}"

# Test connectivity to all remote VMs
for vm_name in "${!REMOTE_VMS[@]}"; do
    IFS=':' read -r ip port <<< "${REMOTE_VMS[$vm_name]}"
    echo -n "Testing $vm_name ($ip:$port)... "

    if nc -z -w3 "$ip" "$port" 2>/dev/null; then
        echo -e "${GREEN}Connected${NC}"
    else
        echo -e "${RED}Failed${NC}"
        echo -e "${YELLOW}  Warning: $vm_name VM at $ip:$port is not accessible${NC}"
    fi
done

echo ""
echo -e "${CYAN}Installing Redis CLI Tools...${NC}"

# Try multiple methods to install redis-cli
if command -v redis-cli >/dev/null 2>&1; then
    echo -e "${GREEN}redis-cli already available${NC}"
else
    echo "Attempting to install redis-tools..."

    # Try package manager first (may require password)
    if command -v apt >/dev/null 2>&1; then
        echo "Attempting apt install (may require sudo password)..."
        if sudo -n apt update && sudo -n apt install -y redis-tools 2>/dev/null; then
            echo -e "${GREEN}redis-tools installed via apt${NC}"
        else
            echo -e "${YELLOW}Could not install via apt (no sudo access)${NC}"
            echo "Redis CLI will be installed via alternative method..."

            # Alternative: compile from source
            REDIS_VERSION="7.4.0"
            REDIS_DIR="/tmp/redis-$REDIS_VERSION"

            if [ ! -d "$REDIS_DIR" ]; then
                echo "Downloading and compiling redis-cli..."
                cd /tmp
                curl -fsSL "http://download.redis.io/releases/redis-$REDIS_VERSION.tar.gz" | tar xz
                cd "$REDIS_DIR"
                make redis-cli

                # Install to local bin
                mkdir -p "$HOME/.local/bin"
                cp src/redis-cli "$HOME/.local/bin/"

                # Add to PATH if not already there
                if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
                    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
                    export PATH="$HOME/.local/bin:$PATH"
                fi

                echo -e "${GREEN}redis-cli installed to ~/.local/bin${NC}"
            fi
        fi
    fi
fi

echo ""
echo -e "${CYAN}Testing Redis Connection...${NC}"

# Test Redis connection with authentication using SSOT variables
REDIS_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"

if command -v redis-cli >/dev/null 2>&1; then
    if [ -n "$REDIS_PASSWORD" ]; then
        REDIS_RESPONSE=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" ping 2>/dev/null || echo "ERROR")
    else
        REDIS_RESPONSE=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null || echo "ERROR")
    fi

    if [ "$REDIS_RESPONSE" = "PONG" ]; then
        echo -e "${GREEN}Redis connection successful${NC}"

        # Get Redis info
        if [ -n "$REDIS_PASSWORD" ]; then
            DB_COUNT=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" config get databases | tail -1)
        else
            DB_COUNT=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" config get databases | tail -1)
        fi

        echo -e "${BLUE}  Redis databases available: $DB_COUNT${NC}"

    else
        echo -e "${YELLOW}Redis connection failed. Response: $REDIS_RESPONSE${NC}"
        echo "This is expected if Redis requires authentication or has specific configuration."
    fi
else
    echo -e "${YELLOW}redis-cli not available for testing${NC}"
fi

echo ""
echo -e "${CYAN}Creating Distributed Service Helpers...${NC}"

# Create directory for distributed scripts
mkdir -p scripts/distributed/

# Create service health check script (regenerate with SSOT config)
cat > scripts/distributed/check-health.sh << 'EOF'
#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Check health of all distributed AutoBot services

# =============================================================================
# SSOT Configuration - Issue #694
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/ssot-config.sh" 2>/dev/null || source "$SCRIPT_DIR/lib/ssot-config.sh" 2>/dev/null || {
    # Fallback if lib not found
    PROJECT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
    [ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }
}

echo "AutoBot Distributed Services Health Check"
echo "============================================="

# Service configuration using SSOT variables
declare -A SERVICES=(
    ["Backend (Local)"]="127.0.0.1:${AUTOBOT_BACKEND_PORT:-8001}/api/health"
    ["Redis VM"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}:${AUTOBOT_REDIS_PORT:-6379}"
    ["NPU Worker VM"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:${AUTOBOT_NPU_WORKER_PORT:-8081}/health"
    ["Frontend VM"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}"
    ["AI Stack VM"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:${AUTOBOT_AI_STACK_PORT:-8080}/health"
    ["Browser VM"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}/health"
    ["Ollama (Local)"]="${AUTOBOT_OLLAMA_HOST:-127.0.0.1}:${AUTOBOT_OLLAMA_PORT:-11434}/api/tags"
)

for service_name in "${!SERVICES[@]}"; do
    endpoint="${SERVICES[$service_name]}"
    echo -n "Checking $service_name... "

    if [[ $endpoint == *":"*"/api/"* ]] || [[ $endpoint == *":"*"/health"* ]]; then
        # HTTP endpoint
        if curl -s --max-time 5 "http://$endpoint" >/dev/null 2>&1; then
            echo "OK"
        else
            echo "Failed"
        fi
    else
        # TCP port check
        IFS=':' read -r host port <<< "$endpoint"
        if nc -z -w3 "$host" "$port" 2>/dev/null; then
            echo "OK"
        else
            echo "Failed"
        fi
    fi
done

echo ""
echo "Service URLs:"
echo "  Backend API: http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}"
echo "  Frontend: http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}"
echo "  Redis Insight: http://${AUTOBOT_REDIS_HOST:-172.16.168.23}:8002"
echo "  AI Stack: http://${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:${AUTOBOT_AI_STACK_PORT:-8080}"
echo "  NPU Worker: http://${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:${AUTOBOT_NPU_WORKER_PORT:-8081}"
echo "  Browser Service: http://${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"
echo "  Ollama: http://${AUTOBOT_OLLAMA_HOST:-127.0.0.1}:${AUTOBOT_OLLAMA_PORT:-11434}"
echo "  VNC Desktop: http://${AUTOBOT_BACKEND_HOST:-127.0.0.1}:${AUTOBOT_VNC_PORT:-6080}"

echo ""
echo "Distributed Architecture Status:"
echo "  Main WSL (${AUTOBOT_BACKEND_HOST:-172.16.168.20}): Backend API + Ollama + VNC"
echo "  Frontend VM (${AUTOBOT_FRONTEND_HOST:-172.16.168.21}): Vue.js Web Interface"
echo "  NPU Worker VM (${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}): Intel OpenVINO + Hardware Acceleration"
echo "  Redis VM (${AUTOBOT_REDIS_HOST:-172.16.168.23}): Redis Stack + Vector Storage"
echo "  AI Stack VM (${AUTOBOT_AI_STACK_HOST:-172.16.168.24}): AI Processing Services"
echo "  Browser VM (${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}): Playwright Automation"

echo ""
echo "Testing Distributed Redis Connection:"
cd "${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
if python src/utils/distributed_redis_client.py 2>/dev/null | grep -q "connection working correctly"; then
    echo "  Redis Connection: OK"
else
    echo "  Redis Connection: Failed"
fi
EOF

chmod +x scripts/distributed/check-health.sh

# Create backup collection script with SSOT config
cat > scripts/distributed/collect-backups.sh << 'EOF'
#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Collect backups from all distributed AutoBot VMs via SSH

set -e

# =============================================================================
# SSOT Configuration - Issue #694
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/ssot-config.sh" 2>/dev/null || source "$SCRIPT_DIR/lib/ssot-config.sh" 2>/dev/null || {
    # Fallback if lib not found
    PROJECT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
    [ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }
}

BACKUP_DIR="./backups/distributed/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "Collecting backups from distributed AutoBot infrastructure..."
echo "Backup directory: $BACKUP_DIR"

# VM SSH configurations using SSOT variables
declare -A VM_HOSTS=(
    ["redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

REDIS_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"

# Backup Redis data
echo "Backing up Redis data..."
if command -v redis-cli >/dev/null 2>&1; then
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BGSAVE
    sleep 2

    # Try to copy Redis dump via SSH (may require key setup)
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$REDIS_HOST" "test -f /var/lib/redis/dump.rdb" 2>/dev/null; then
        scp "$REDIS_HOST:/var/lib/redis/dump.rdb" "$BACKUP_DIR/redis_dump.rdb"
        echo "Redis backup collected"
    else
        echo "Could not collect Redis dump file (SSH key setup required)"
    fi
else
    echo "redis-cli not available for backup"
fi

# Backup logs from each VM (requires SSH key setup)
for vm_name in "${!VM_HOSTS[@]}"; do
    vm_host="${VM_HOSTS[$vm_name]}"
    echo "Collecting logs from $vm_name ($vm_host)..."

    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$vm_host" "test -d /var/log/autobot" 2>/dev/null; then
        mkdir -p "$BACKUP_DIR/logs/$vm_name"
        scp -r "$vm_host:/var/log/autobot/*" "$BACKUP_DIR/logs/$vm_name/" 2>/dev/null || true
        echo "$vm_name logs collected"
    else
        echo "Could not collect logs from $vm_name (SSH key setup required)"
    fi
done

# Backup local data
echo "Backing up local data..."
[ -d "./data" ] && cp -r ./data "$BACKUP_DIR/local_data"
[ -d "./config" ] && cp -r ./config "$BACKUP_DIR/local_config"
[ -f "./.env" ] && cp ./.env "$BACKUP_DIR/environment"

echo "Backup collection complete: $BACKUP_DIR"
echo ""
echo "SSH Key Setup Instructions:"
echo "  To enable automatic SSH access to remote VMs:"
echo "  1. ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_distributed"
echo "  2. Run: bash scripts/utilities/setup-ssh-keys.sh"
echo "  3. Add 'IdentityFile ~/.ssh/autobot_distributed' to ~/.ssh/config"
EOF

chmod +x scripts/distributed/collect-backups.sh

# Create SSH key setup script reference
cat > scripts/distributed/setup-ssh-keys.sh << 'EOF'
#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Setup SSH keys for passwordless access to distributed AutoBot VMs
# This script is a wrapper - delegates to scripts/utilities/setup-ssh-keys.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/../utilities/setup-ssh-keys.sh" "$@"
EOF

chmod +x scripts/distributed/setup-ssh-keys.sh

# Create NPU setup script for remote execution with SSOT config
cat > scripts/distributed/setup-npu-remote.sh << 'EOF'
#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Setup NPU acceleration on remote NPU Worker VM

# =============================================================================
# SSOT Configuration - Issue #694
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/ssot-config.sh" 2>/dev/null || source "$SCRIPT_DIR/lib/ssot-config.sh" 2>/dev/null || {
    # Fallback if lib not found
    PROJECT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
    [ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }
}

NPU_VM="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
NPU_HOST="autobot-npu-worker"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${AUTOBOT_SSH_USER:-autobot}"

echo "Setting up NPU acceleration on remote worker VM ($NPU_VM)..."

# Check SSH connectivity
if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o BatchMode=yes "$SSH_USER@$NPU_VM" "echo 'SSH connection test'" 2>/dev/null; then
    echo "Cannot connect to NPU Worker VM via SSH"
    echo "Please run: bash scripts/utilities/setup-ssh-keys.sh first"
    exit 1
fi

echo "SSH connection to NPU Worker VM confirmed"

# Create remote setup script
REMOTE_SETUP_SCRIPT=$(cat << 'REMOTE_EOF'
#!/bin/bash
# NPU Worker VM Setup Script (runs on remote VM)

echo "Setting up NPU acceleration on $(hostname)..."

# Update system
sudo apt update

# Install OpenVINO dependencies
echo "Installing OpenVINO dependencies..."
sudo apt install -y \
    build-essential \
    cmake \
    git \
    wget \
    python3-dev \
    python3-pip \
    libssl-dev \
    libtbb-dev \
    libusb-1.0-0-dev \
    pkg-config

# Download and install OpenVINO
OPENVINO_VERSION="2024.4.0"
OPENVINO_DIR="/opt/intel/openvino_$OPENVINO_VERSION"

if [ ! -d "$OPENVINO_DIR" ]; then
    echo "Downloading OpenVINO $OPENVINO_VERSION..."
    cd /tmp
    wget "https://storage.openvinotoolkit.org/repositories/openvino/packages/2024.4/linux/l_openvino_toolkit_ubuntu20_${OPENVINO_VERSION}_x86_64.tgz"

    echo "Installing OpenVINO..."
    tar -xzf "l_openvino_toolkit_ubuntu20_${OPENVINO_VERSION}_x86_64.tgz"
    sudo mv "l_openvino_toolkit_ubuntu20_${OPENVINO_VERSION}" "$OPENVINO_DIR"
    sudo chown -R root:root "$OPENVINO_DIR"

    # Create symlink for easy access
    sudo ln -sf "$OPENVINO_DIR" /opt/intel/openvino
fi

# Setup OpenVINO environment
echo "Setting up OpenVINO environment..."
echo "source $OPENVINO_DIR/setupvars.sh" >> ~/.bashrc

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install --user openvino openvino-dev

# Setup NPU device permissions (if available)
echo "Setting up hardware device permissions..."
sudo usermod -a -G render $(whoami)

# Install Intel GPU drivers (for Intel Arc support)
echo "Installing Intel GPU drivers..."
sudo apt install -y intel-media-va-driver-non-free libmfx1 libmfxhw64-1

# Create NPU test script
cat > ~/test_npu.py << 'PYTHON_EOF'
#!/usr/bin/env python3
import openvino as ov
import sys

def test_npu_availability():
    """Test NPU and other Intel hardware availability"""
    print("Testing OpenVINO device availability...")

    try:
        # Initialize OpenVINO runtime
        core = ov.Core()

        # List all available devices
        available_devices = core.available_devices
        print(f"Available devices: {available_devices}")

        # Test specific devices
        devices_to_test = ['NPU', 'GPU', 'CPU']

        for device in devices_to_test:
            try:
                if device in available_devices:
                    device_name = core.get_property(device, "FULL_DEVICE_NAME")
                    print(f"{device}: {device_name}")
                else:
                    print(f"{device}: Not available")
            except Exception as e:
                print(f"{device}: Error - {e}")

        return True

    except Exception as e:
        print(f"OpenVINO initialization failed: {e}")
        return False

if __name__ == "__main__":
    success = test_npu_availability()
    sys.exit(0 if success else 1)
PYTHON_EOF

chmod +x ~/test_npu.py

echo "NPU Worker VM setup complete!"
echo ""
echo "Running hardware detection test..."
python3 ~/test_npu.py

echo ""
echo "NPU Worker VM is ready for AutoBot acceleration!"
echo "Available at: http://$(hostname -I | awk '{print $1}'):8081"
REMOTE_EOF
)

# Execute setup script on remote NPU VM
echo "Executing setup script on NPU Worker VM..."
ssh -i "$SSH_KEY" "$SSH_USER@$NPU_VM" "bash -s" <<< "$REMOTE_SETUP_SCRIPT"

echo ""
echo "NPU Worker VM setup completed!"
echo "The NPU Worker is now configured for Intel OpenVINO acceleration"
EOF

chmod +x scripts/distributed/setup-npu-remote.sh

echo ""
echo -e "${GREEN}Distributed Architecture Setup Complete!${NC}"
echo ""
echo -e "${CYAN}Next Steps:${NC}"
echo "1. Setup SSH keys for remote VM access:"
echo -e "   ${BLUE}bash scripts/utilities/setup-ssh-keys.sh${NC}"
echo ""
echo "2. Setup NPU acceleration on remote worker:"
echo -e "   ${BLUE}bash scripts/distributed/setup-npu-remote.sh${NC}"
echo ""
echo "3. Check health of all distributed services:"
echo -e "   ${BLUE}bash scripts/distributed/check-health.sh${NC}"
echo ""
echo "4. Collect backups from all VMs:"
echo -e "   ${BLUE}bash scripts/distributed/collect-backups.sh${NC}"
echo ""
echo -e "${YELLOW}Distributed Service URLs:${NC}"
echo "  Backend API (Local): http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:${AUTOBOT_BACKEND_PORT:-8001}"
echo "  Frontend VM: http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}"
echo "  Redis VM: http://${AUTOBOT_REDIS_HOST:-172.16.168.23}:${AUTOBOT_REDIS_PORT:-6379}"
echo "  NPU Worker VM: http://${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}:${AUTOBOT_NPU_WORKER_PORT:-8081}"
echo "  AI Stack VM: http://${AUTOBOT_AI_STACK_HOST:-172.16.168.24}:${AUTOBOT_AI_STACK_PORT:-8080}"
echo "  Browser VM: http://${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}:${AUTOBOT_BROWSER_SERVICE_PORT:-3000}"
echo "  Ollama (Local): http://${AUTOBOT_OLLAMA_HOST:-127.0.0.1}:${AUTOBOT_OLLAMA_PORT:-11434}"
echo "  VNC Desktop (Local): http://${AUTOBOT_BACKEND_HOST:-127.0.0.1}:${AUTOBOT_VNC_PORT:-6080}"
