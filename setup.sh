#!/bin/bash
# AutoBot - Distributed VM Setup Script
# Handles initial setup for distributed VM architecture

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_usage() {
    echo -e "${GREEN}AutoBot - Distributed VM Setup Script${NC}"
    echo "Configures AutoBot for distributed VM deployment across multiple machines"
    echo ""
    echo "Usage: $0 [setup_type] [options]"
    echo ""
    echo -e "${YELLOW}Setup Types:${NC}"
    echo "  initial         Complete distributed setup (default)"
    echo "  distributed     Same as initial - full distributed VM setup"
    echo "  backend-only    Setup only backend dependencies (WSL main machine)"
    echo "  agent           Agent and environment setup only"
    echo "  ssh-keys        Generate and distribute SSH keys for VM connectivity"
    echo "  vm-services     Install services on individual VMs"
    echo "  knowledge       Knowledge base setup and population"
    echo "  desktop         VNC desktop environment setup for headless servers"
    echo "  repair          Repair existing installation"
    echo ""
    echo -e "${YELLOW}Environment Options:${NC}"
    echo "  --distributed   Setup for distributed VM deployment (default)"
    echo "  --backend-only  Setup only backend on main machine"
    echo ""
    echo -e "${YELLOW}General Options:${NC}"
    echo "  --force         Force setup even if already configured"
    echo "  --skip-deps     Skip dependency installation"
    echo "  --help          Show this help"
    echo ""
    echo -e "${BLUE}Distributed Architecture:${NC}"
    echo "  Main (WSL):     172.16.168.20 - Backend API server"
    echo "  VM1 Frontend:   172.16.168.21 - Vue.js web interface (Native Vite)"
    echo "  VM2 NPU Worker: 172.16.168.22 - Hardware AI acceleration"
    echo "  VM3 Redis:      172.16.168.23 - Database and caching"
    echo "  VM4 AI Stack:   172.16.168.24 - AI processing services"
    echo "  VM5 Browser:    172.16.168.25 - Web automation (Playwright)"
    echo ""
    echo -e "${BLUE}Examples:${NC}"
    echo "  $0                          # Complete distributed setup"
    echo "  $0 distributed              # Same as above"
    echo "  $0 backend-only             # Setup only WSL backend"
    echo "  $0 ssh-keys --force         # Regenerate SSH keys"
    echo "  $0 vm-services              # Install services on VMs"
    echo "  $0 knowledge --force        # Force knowledge base re-setup"
}

# Default options
SETUP_TYPE="initial"
DEPLOYMENT_MODE="distributed"
FORCE_SETUP=false
SKIP_DEPS=false

# VM Configuration
SSH_KEY="$HOME/.ssh/autobot_key"
SSH_USER="autobot"
declare -A VMS=(
    ["frontend"]="172.16.168.21"
    ["npu-worker"]="172.16.168.22"
    ["redis"]="172.16.168.23"
    ["ai-stack"]="172.16.168.24"
    ["browser"]="172.16.168.25"
)

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        initial|distributed|backend-only|agent|ssh-keys|vm-services|knowledge|desktop|repair)
            SETUP_TYPE="$1"
            shift
            ;;
        --distributed)
            DEPLOYMENT_MODE="distributed"
            shift
            ;;
        --backend-only)
            DEPLOYMENT_MODE="backend-only"
            shift
            ;;
        --force)
            FORCE_SETUP=true
            shift
            ;;
        --skip-deps)
            SKIP_DEPS=true
            shift
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

run_setup_script() {
    local script_path="$1"
    local description="$2"
    
    if [ -f "$script_path" ]; then
        echo -e "${CYAN}🔧 $description...${NC}"
        if [ "${script_path##*.}" = "py" ]; then
            python3 "$script_path"
        else
            bash "$script_path"
        fi
    else
        echo -e "${YELLOW}⚠️  Setup script not found: $script_path${NC}"
        echo -e "${CYAN}ℹ️  You may need to create this script for distributed deployment${NC}"
    fi
}

setup_ssh_keys() {
    log "Setting up SSH keys for VM connectivity..."
    
    # Generate SSH key if it doesn't exist
    if [ ! -f "$SSH_KEY" ] || [ "$FORCE_SETUP" = true ]; then
        log "Generating SSH key for VM access..."
        ssh-keygen -t rsa -b 4096 -f "$SSH_KEY" -N "" -q
        chmod 600 "$SSH_KEY"
        chmod 644 "$SSH_KEY.pub"
        success "SSH key generated: $SSH_KEY"
    else
        log "SSH key already exists: $SSH_KEY"
    fi
    
    # Display public key for manual distribution
    echo ""
    echo -e "${YELLOW}📋 MANUAL STEP REQUIRED:${NC}"
    echo -e "${CYAN}Copy this public key to each VM's ~/.ssh/authorized_keys file:${NC}"
    echo ""
    echo -e "${BLUE}$(cat "$SSH_KEY.pub")${NC}"
    echo ""
    echo -e "${YELLOW}For each VM (172.16.168.21-25), run:${NC}"
    echo -e "${CYAN}  1. ssh autobot@VM_IP${NC}"
    echo -e "${CYAN}  2. mkdir -p ~/.ssh${NC}"
    echo -e "${CYAN}  3. echo 'PUBLIC_KEY_ABOVE' >> ~/.ssh/authorized_keys${NC}"
    echo -e "${CYAN}  4. chmod 600 ~/.ssh/authorized_keys${NC}"
    echo -e "${CYAN}  5. chmod 700 ~/.ssh${NC}"
    echo ""
    
    # Test connectivity
    log "Testing VM connectivity..."
    local connectivity_success=0
    local total_vms=${#VMS[@]}
    
    for vm_name in "${!VMS[@]}"; do
        vm_ip=${VMS[$vm_name]}
        echo -n "  Testing $vm_name ($vm_ip)... "
        
        if timeout 10 ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$SSH_USER@$vm_ip" "echo 'Connection successful'" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Connected${NC}"
            ((connectivity_success++))
        else
            echo -e "${RED}❌ Failed${NC}"
            echo -e "${YELLOW}    Ensure VM is running and SSH key is properly installed${NC}"
        fi
    done
    
    if [ $connectivity_success -eq $total_vms ]; then
        success "All VMs are accessible via SSH"
    else
        warning "$connectivity_success/$total_vms VMs are accessible"
        echo -e "${YELLOW}Please configure remaining VMs manually${NC}"
    fi
}

setup_backend_dependencies() {
    log "Setting up backend dependencies (WSL main machine)..."
    
    # Check if we're on WSL/Linux
    if [[ ! -f /etc/os-release ]]; then
        error "This setup is designed for Linux/WSL environments"
        exit 1
    fi
    
    # Install system dependencies
    if [ "$SKIP_DEPS" = false ]; then
        log "Installing system dependencies..."
        
        # Update package list
        sudo apt-get update -qq
        
        # Install essential packages
        sudo apt-get install -y \
            python3 \
            python3-pip \
            python3-venv \
            curl \
            wget \
            git \
            ssh \
            redis-tools \
            build-essential \
            pkg-config \
            libssl-dev \
            libffi-dev \
            nodejs \
            npm
        
        success "System dependencies installed"
    fi
    
    # Setup Python virtual environment
    if [ ! -d "venv" ] || [ "$FORCE_SETUP" = true ]; then
        log "Creating Python virtual environment..."
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        
        # Install Python dependencies
        if [ -f "requirements.txt" ]; then
            pip install -r requirements.txt
        fi
        
        success "Python environment configured"
    else
        log "Python virtual environment already exists"
    fi
    
    # Setup Node.js dependencies for frontend (if present)
    if [ -d "autobot-vue" ]; then
        log "Installing frontend dependencies..."
        cd autobot-vue
        npm install
        cd ..
        success "Frontend dependencies installed"
    fi
    
    # Create necessary directories
    mkdir -p logs data config backup
    
    success "Backend dependencies setup completed"
}

install_vm_services() {
    log "Installing services on distributed VMs..."
    
    if [ ! -f "$SSH_KEY" ]; then
        error "SSH key not found. Run: bash setup.sh ssh-keys"
        exit 1
    fi
    
    # Frontend VM (172.16.168.21) - NATIVE VITE ONLY
    log "Setting up Frontend VM (172.16.168.21) with native Vite server..."
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.21" << 'EOF'
        # Update system
        sudo apt-get update -qq
        sudo apt-get install -y nodejs npm git curl
        
        # Clone repository if not exists
        if [ ! -d "AutoBot" ]; then
            git clone https://github.com/your-org/AutoBot.git
        fi
        
        # Setup frontend with native Vite development server
        cd AutoBot/autobot-vue
        npm install
        
        # Create systemd service for Vite development server
        sudo tee /etc/systemd/system/autobot-frontend.service > /dev/null << 'SERVICE_EOF'
[Unit]
Description=AutoBot Frontend (Vite Development Server)
After=network.target

[Service]
Type=exec
User=autobot
WorkingDirectory=/home/autobot/AutoBot/autobot-vue
Environment=NODE_ENV=development
Environment=VITE_BACKEND_HOST=172.16.168.20
Environment=VITE_BACKEND_PORT=8001
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0 --port 5173
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE_EOF
        
        # Enable and start the service
        sudo systemctl daemon-reload
        sudo systemctl enable autobot-frontend.service
        
        echo "Frontend VM setup completed - using native Vite development server"
EOF
    
    # Redis VM (172.16.168.23)
    log "Setting up Redis VM (172.16.168.23)..."
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.23" << 'EOF'
        # Update system
        sudo apt-get update -qq
        sudo apt-get install -y docker.io docker-compose curl
        
        # Enable Docker
        sudo systemctl enable docker
        sudo systemctl start docker
        sudo usermod -aG docker autobot
        
        # Pull Redis Stack image
        sudo docker pull redis/redis-stack:latest
        
        echo "Redis VM setup completed"
EOF
    
    # NPU Worker VM (172.16.168.22)
    log "Setting up NPU Worker VM (172.16.168.22)..."
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.22" << 'EOF'
        # Update system
        sudo apt-get update -qq
        sudo apt-get install -y python3 python3-pip python3-venv git curl build-essential
        
        # Clone repository if not exists
        if [ ! -d "AutoBot" ]; then
            git clone https://github.com/your-org/AutoBot.git
        fi
        
        # Setup NPU worker environment
        cd AutoBot
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        
        # Install NPU-specific dependencies
        # (This would include OpenVINO, Intel NPU drivers, etc.)
        
        echo "NPU Worker VM setup completed"
EOF
    
    # AI Stack VM (172.16.168.24)
    log "Setting up AI Stack VM (172.16.168.24)..."
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.24" << 'EOF'
        # Update system
        sudo apt-get update -qq
        sudo apt-get install -y python3 python3-pip python3-venv git curl
        
        # Clone repository if not exists
        if [ ! -d "AutoBot" ]; then
            git clone https://github.com/your-org/AutoBot.git
        fi
        
        # Setup AI stack environment
        cd AutoBot
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        
        echo "AI Stack VM setup completed"
EOF
    
    # Browser VM (172.16.168.25)
    log "Setting up Browser VM (172.16.168.25)..."
    ssh -i "$SSH_KEY" "$SSH_USER@172.16.168.25" << 'EOF'
        # Update system
        sudo apt-get update -qq
        sudo apt-get install -y python3 python3-pip python3-venv nodejs npm git curl
        
        # Install browser dependencies
        sudo apt-get install -y chromium-browser firefox-esr xvfb
        
        # Clone repository if not exists
        if [ ! -d "AutoBot" ]; then
            git clone https://github.com/your-org/AutoBot.git
        fi
        
        # Setup browser service environment
        cd AutoBot
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        
        # Install Playwright
        npm install -g playwright
        playwright install
        
        echo "Browser VM setup completed"
EOF
    
    success "VM services installation completed - Frontend uses native Vite development server"
}

setup_vm_networking() {
    log "Configuring VM networking and firewall rules..."
    
    # This is a placeholder for network configuration
    # In a real setup, you'd configure:
    # - Firewall rules to allow communication between VMs
    # - DNS resolution for VM hostnames
    # - Load balancing if needed
    # - SSL/TLS certificates
    
    warning "Network configuration is environment-specific"
    echo -e "${CYAN}Please ensure the following network configuration:${NC}"
    echo -e "${BLUE}  1. VMs can communicate with each other on specified ports${NC}"
    echo -e "${BLUE}  2. Firewall rules allow required service ports${NC}"
    echo -e "${BLUE}  3. DNS resolution works for VM IP addresses${NC}"
    echo -e "${BLUE}  4. SSL/TLS certificates are configured if needed${NC}"
    
    success "Network configuration guidelines provided"
}

run_distributed_setup() {
    echo -e "${GREEN}🚀 AutoBot Distributed VM Setup${NC}"
    echo -e "${BLUE}======================================${NC}"
    echo ""
    
    log "Starting distributed VM setup..."
    log "Architecture: 6-VM distributed system"
    echo ""
    
    # Step 1: SSH Keys
    setup_ssh_keys
    echo ""
    
    # Step 2: Backend Dependencies
    setup_backend_dependencies
    echo ""
    
    # Step 3: VM Services
    install_vm_services
    echo ""
    
    # Step 4: Network Configuration
    setup_vm_networking
    echo ""
    
    # Step 5: Knowledge Base (if available)
    run_setup_script "scripts/setup/knowledge/fresh_kb_setup.py" "Setting up knowledge base"
    
    # Step 6: VNC Desktop (optional)
    run_setup_script "scripts/setup/install-vnc-headless.sh" "Setting up VNC desktop environment"
    
    success "Distributed VM setup completed!"
    echo ""
    echo -e "${BLUE}📋 Next Steps:${NC}"
    echo -e "${CYAN}  1. Verify all VMs are running: bash run_autobot.sh --status${NC}"
    echo -e "${CYAN}  2. Start backend only: bash run_autobot.sh --dev${NC}"
    echo -e "${CYAN}  3. Start all VM services: bash scripts/vm-management/start-all-vms.sh${NC}"
    echo -e "${CYAN}  4. Access frontend: http://172.16.168.21:5173${NC}"
    echo ""
}

run_backend_only_setup() {
    echo -e "${GREEN}🚀 AutoBot Backend-Only Setup${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo ""
    
    log "Setting up backend dependencies only..."
    setup_backend_dependencies
    
    # Basic agent setup
    run_setup_script "scripts/setup/setup_agent.sh" "Setting up AutoBot agent"
    
    # Knowledge base setup
    run_setup_script "scripts/setup/knowledge/fresh_kb_setup.py" "Setting up knowledge base"
    
    # VNC desktop setup
    run_setup_script "scripts/setup/install-vnc-headless.sh" "Setting up VNC desktop environment"
    
    success "Backend-only setup completed!"
    echo ""
    echo -e "${BLUE}📋 Next Steps:${NC}"
    echo -e "${CYAN}  1. Start backend: bash run_autobot.sh --dev${NC}"
    echo -e "${CYAN}  2. Backend will be available at: http://172.16.168.20:8001${NC}"
    echo -e "${CYAN}  3. Note: VM services need to be configured separately${NC}"
    echo ""
}

# Main execution
echo -e "${GREEN}🔧 AutoBot Setup - $SETUP_TYPE${NC}"
echo -e "${BLUE}Deployment Mode: $DEPLOYMENT_MODE${NC}"
echo ""

case "$SETUP_TYPE" in
    "initial"|"distributed")
        run_distributed_setup
        ;;
    "backend-only")
        run_backend_only_setup
        ;;
    "ssh-keys")
        setup_ssh_keys
        ;;
    "vm-services")
        install_vm_services
        ;;
    "agent")
        run_setup_script "scripts/setup/setup_agent.sh" "Setting up AutoBot agent"
        ;;
    "knowledge")
        run_setup_script "scripts/setup/knowledge/fresh_kb_setup.py" "Setting up knowledge base"
        ;;
    "desktop")
        run_setup_script "scripts/setup/install-vnc-headless.sh" "Setting up VNC desktop environment"
        ;;
    "repair")
        run_setup_script "scripts/setup/setup_repair.sh" "Running setup repair"
        ;;
    *)
        error "Unknown setup type: $SETUP_TYPE"
        print_usage
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}🎉 AutoBot $SETUP_TYPE setup completed!${NC}"