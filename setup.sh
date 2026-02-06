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
    echo -e "${CYAN}TIP: For interactive setup, run: ./scripts/setup_wizard.sh${NC}"
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
    echo "  --development   Development mode - Vite dev servers, hot reload, debugging"
    echo "  --production    Production mode - nginx, systemd services, optimized builds"
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
    echo -e "${CYAN}Examples:${NC}"
    echo "  $0 initial                    # Complete distributed setup"
    echo "  $0 distributed --development  # Development mode setup"
    echo "  $0 backend-only --production  # Backend only production setup"
    echo "  $0 ssh-keys                   # Generate SSH keys for VMs"
    echo "  $0 knowledge                  # Setup knowledge base"
    echo ""
    exit 0
}

# Logging functions
log() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Check if we're running in the correct directory
check_autobot_directory() {
    if [ ! -f "config/config.yaml.template" ] || [ ! -d "backend" ] || [ ! -d "autobot-vue" ]; then
        error "Please run this script from the AutoBot root directory"
        error "Required files: config/config.yaml.template, backend/, autobot-vue/"
        exit 1
    fi
}

# Detect OS and distribution
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if grep -qi microsoft /proc/version 2>/dev/null; then
            OS="wsl"
            DISTRO=$(lsb_release -si 2>/dev/null || echo "Unknown")
        else
            OS="linux"
            DISTRO=$(lsb_release -si 2>/dev/null || echo "Unknown")
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        DISTRO="macOS"
    else
        OS="unknown"
        DISTRO="Unknown"
    fi

    log "Detected OS: $OS ($DISTRO)"
}

# Check system requirements
check_requirements() {
    log "Checking system requirements..."

    # Check Python
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is not installed. Please install Python 3.8 or later."
        exit 1
    fi

    # Check Node.js for frontend builds
    if ! command -v node &> /dev/null; then
        warn "Node.js not found. Frontend builds may not work."
        warn "Please install Node.js 16+ for frontend development."
    fi

    # Check available memory and disk space
    if command -v free &> /dev/null; then
        MEMORY_MB=$(free -m | awk 'NR==2{print $2}')
        if [ "$MEMORY_MB" -lt 4096 ]; then
            warn "System has less than 4GB RAM. Performance may be affected."
        fi
    fi

    success "System requirements check completed"
}

# Setup Python virtual environment and dependencies
setup_python_environment() {
    log "Setting up Python environment..."

    # Create virtual environment if it doesn't exist or if forced
    if [ ! -d "venv" ] || [ "$FORCE_SETUP" = true ]; then
        log "Creating Python virtual environment..."
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip

        # Install Python dependencies from config/requirements.txt
        if [ -f "config/requirements.txt" ]; then
            log "Installing AutoBot Python dependencies..."
            pip install -r config/requirements.txt
        elif [ -f "requirements.txt" ]; then
            log "Installing dependencies from requirements.txt..."
            pip install -r requirements.txt
        else
            log "Installing core AutoBot dependencies..."
            # Install critical dependencies if no requirements file found
            pip install fastapi>=0.115.0 uvicorn>=0.30.0 python-multipart>=0.0.9
            pip install aiohttp==3.12.15 aiofiles>=23.0.0 websockets>=11.0.0
            pip install redis>=5.0 chromadb>=0.4.0
            pip install transformers>=4.55.2 sentence-transformers>=2.2.0
            pip install llama-index llama-index-llms-ollama llama-index-embeddings-ollama
            pip install playwright>=1.40.0 selenium>=4.15.0
        fi

        # Install voice processing dependencies (optional)
        if [ -f "config/requirements-voice.txt" ]; then
            log "Installing voice processing dependencies..."
            # Install voice dependencies with fallback handling
            pip install speechrecognition==3.10.0 pydub==0.25.1 gtts==2.3.1 pyttsx3 || warn "Some voice dependencies failed to install - voice features may be limited"
        fi

        success "Python environment configured"
    else
        log "Python virtual environment already exists"
    fi

    # Setup Node.js dependencies for frontend (if present)
    if [ -d "autobot-vue" ] && command -v npm &> /dev/null; then
        log "Setting up Node.js dependencies for Vue frontend..."
        cd autobot-vue
        if [ ! -d "node_modules" ] || [ "$FORCE_SETUP" = true ]; then
            npm install
            success "Node.js dependencies installed"
        else
            log "Node.js dependencies already installed"
        fi
        cd ..
    fi
}

# Generate SSH keys for VM connectivity
generate_ssh_keys() {
    log "Generating SSH keys for VM connectivity..."

    SSH_KEY_PATH="$HOME/.ssh/autobot_key"

    if [ ! -f "$SSH_KEY_PATH" ] || [ "$FORCE_SETUP" = true ]; then
        log "Creating SSH key pair..."
        ssh-keygen -t rsa -b 4096 -f "$SSH_KEY_PATH" -N "" -C "autobot-vm-access"
        chmod 600 "$SSH_KEY_PATH"
        chmod 644 "$SSH_KEY_PATH.pub"
        success "SSH keys generated: $SSH_KEY_PATH"

        # Display public key for VM setup
        echo -e "\n${YELLOW}Public key for VM setup:${NC}"
        cat "$SSH_KEY_PATH.pub"
        echo ""
        echo -e "${CYAN}Copy this public key to ~/.ssh/authorized_keys on all VMs${NC}"
    else
        log "SSH keys already exist"
        success "Using existing SSH keys: $SSH_KEY_PATH"
    fi
}

# Setup configuration files
setup_configuration() {
    log "Setting up configuration files..."

    # Create config.yaml from template if it doesn't exist
    if [ ! -f "config/config.yaml" ]; then
        log "Creating config.yaml from template..."
        cp config/config.yaml.template config/config.yaml

        # Enable voice interface by default
        if command -v sed &> /dev/null; then
            sed -i 's/enabled: false/enabled: true/' config/config.yaml || warn "Could not enable voice interface in config"
        fi

        success "Configuration file created"
    else
        log "Configuration file already exists"
    fi

    # Create required directories
    log "Creating required directories..."
    mkdir -p data/chats data/knowledge data/outputs logs temp reports analysis models
    mkdir -p logs/ai-ml analysis/ai-ml data/outputs/ai-ml data/outputs/multimodal

    # Setup .env file for environment variables
    if [ ! -f ".env" ]; then
        log "Creating .env file..."
        cat > .env << EOF
# AutoBot Environment Configuration
NODE_ENV=development
BACKEND_URL=http://172.16.168.20:8001
FRONTEND_URL=http://172.16.168.21:5173
REDIS_URL=redis://172.16.168.23:6379
NPU_WORKER_URL=http://172.16.168.22:8081
AI_STACK_URL=http://172.16.168.24:8080
BROWSER_VM_URL=http://172.16.168.25:3000

# Security
SECRET_KEY=your-secret-key-here

# Voice Interface
VOICE_ENABLED=true

# User Management Mode (Issue #576)
# Available: single_user (default), single_company, multi_company, provider
# - single_user: No auth, personal use
# - single_company: Auth enabled, teams, PostgreSQL required
# - multi_company: Multi-tenant, PostgreSQL required
# - provider: SaaS with billing, PostgreSQL required
AUTOBOT_USER_MODE=single_user
EOF
        success ".env file created"
    else
        log ".env file already exists"
    fi
}

# Setup NPU Worker (VM2)
setup_npu_worker() {
    log "Setting up NPU Worker environment..."

    # Create NPU-specific requirements and install
    if command -v pip &> /dev/null; then
        log "Installing NPU dependencies..."
        # Activate virtual environment if it exists
        [ -f "venv/bin/activate" ] && source venv/bin/activate

        pip install --upgrade pip

        # Install NPU-specific dependencies
        pip install torch>=2.0.0 transformers>=4.55.2 sentence-transformers>=2.2.0
        pip install openvino>=2023.0.0 openvino-dev
        pip install fastapi uvicorn aiohttp requests pyyaml
        pip install psutil numpy opencv-python pillow

        success "NPU Worker dependencies installed"
    else
        warn "pip not available, skipping NPU dependency installation"
    fi

    # Setup NPU model directory
    mkdir -p models/npu models/onnx models/openvino

    log "NPU Worker setup completed"
}

# Setup AI Stack (VM4)
setup_ai_stack() {
    log "Setting up AI Stack environment..."

    if command -v pip &> /dev/null; then
        log "Installing AI/ML dependencies..."
        [ -f "venv/bin/activate" ] && source venv/bin/activate

        pip install --upgrade pip

        # Install AI/ML dependencies from AutoBot requirements
        pip install fastapi>=0.115.0 uvicorn>=0.30.0 aiohttp==3.12.15
        pip install openai>=1.0.0 anthropic>=0.7.0 tiktoken>=0.5.0
        pip install transformers>=4.55.2 sentence-transformers>=2.2.0
        pip install torch>=2.0.0 torchvision>=0.15.0 torchaudio>=2.0.0
        pip install chromadb>=0.4.0 redis>=5.0
        pip install llama-index llama-index-llms-ollama llama-index-embeddings-ollama
        pip install langchain langchain-community langchain-experimental

        success "AI Stack dependencies installed"
    else
        warn "pip not available, skipping AI dependency installation"
    fi

    # Setup AI model directories
    mkdir -p models/llm models/embeddings models/vision

    log "AI Stack setup completed"
}

# Setup Browser VM (VM5)
setup_browser_vm() {
    log "Setting up Browser VM environment..."

    if command -v pip &> /dev/null; then
        log "Installing browser automation dependencies..."
        [ -f "venv/bin/activate" ] && source venv/bin/activate

        pip install --upgrade pip

        # Install browser automation dependencies
        pip install playwright>=1.40.0 selenium>=4.15.0
        pip install fastapi>=0.115.0 uvicorn>=0.30.0
        pip install httpx>=0.25.0 requests>=2.32.4
        pip install beautifulsoup4>=4.12.0 newspaper3k>=0.2.8

        # Install Playwright browsers
        if command -v playwright &> /dev/null; then
            log "Installing Playwright browsers..."
            playwright install --with-deps
        fi

        success "Browser VM dependencies installed"
    else
        warn "pip not available, skipping browser dependency installation"
    fi

    log "Browser VM setup completed"
}

# Setup VNC Desktop environment
setup_desktop() {
    log "Setting up VNC desktop environment..."

    if [ "$OS" = "linux" ] || [ "$OS" = "wsl" ]; then
        # Create VNC startup script
        cat > scripts/start_vnc.sh << 'EOF'
#!/bin/bash
# Start VNC server for AutoBot desktop access

# Kill any existing VNC servers
vncserver -kill :1 2>/dev/null || true

# Start new VNC server
vncserver :1 -geometry 1920x1080 -depth 24

echo "VNC server started on :1 (port 5901)"
echo "Connect using VNC viewer to: localhost:5901"
EOF
        chmod +x scripts/start_vnc.sh

        success "VNC desktop setup completed"
    else
        log "VNC desktop setup skipped (not applicable for this OS)"
    fi
}

# Setup knowledge base
setup_knowledge_base() {
    log "Setting up knowledge base..."

    # Create knowledge base directories
    mkdir -p data/knowledge_base/documents data/knowledge_base/embeddings
    mkdir -p data/chromadb

    # Initialize knowledge base if Python is available
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate

        if [ -f "scripts/populate_kb_chromadb.py" ]; then
            log "Initializing knowledge base with sample data..."
            python scripts/populate_kb_chromadb.py || warn "Knowledge base initialization failed"
        fi
    fi

    success "Knowledge base setup completed"
}

# Repair existing installation
repair_installation() {
    log "Repairing AutoBot installation..."

    # Re-run key setup steps with force
    FORCE_SETUP=true

    setup_python_environment
    setup_configuration

    # Reinstall requirements
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate

        if [ -f "config/requirements.txt" ]; then
            pip install -r config/requirements.txt --force-reinstall
        fi

        if [ -f "config/requirements-voice.txt" ]; then
            pip install speechrecognition==3.10.0 pydub==0.25.1 gtts==2.3.1 pyttsx3 --force-reinstall || warn "Voice dependencies repair incomplete"
        fi
    fi

    success "Installation repair completed"
}

# Main setup orchestration
main() {
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}        AutoBot Distributed Setup        ${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""

    # Parse command line arguments
    SETUP_TYPE="initial"
    FORCE_SETUP=false
    SKIP_DEPS=false
    DEVELOPMENT_MODE=false
    PRODUCTION_MODE=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            initial|distributed|backend-only|agent|ssh-keys|vm-services|knowledge|desktop|repair)
                SETUP_TYPE="$1"
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
            --development)
                DEVELOPMENT_MODE=true
                shift
                ;;
            --production)
                PRODUCTION_MODE=true
                shift
                ;;
            --help|-h)
                print_usage
                ;;
            *)
                error "Unknown option: $1"
                print_usage
                ;;
        esac
    done

    # Initial checks
    check_autobot_directory
    detect_os
    check_requirements

    # Execute setup based on type
    case $SETUP_TYPE in
        initial|distributed)
            log "Starting complete distributed setup..."
            setup_python_environment
            generate_ssh_keys
            setup_configuration
            setup_knowledge_base
            success "Complete distributed setup finished"
            ;;
        backend-only)
            log "Starting backend-only setup..."
            setup_python_environment
            setup_configuration
            success "Backend-only setup finished"
            ;;
        agent)
            log "Starting agent environment setup..."
            setup_python_environment
            setup_configuration
            success "Agent setup finished"
            ;;
        ssh-keys)
            generate_ssh_keys
            ;;
        vm-services)
            log "Setting up VM-specific services..."
            setup_npu_worker
            setup_ai_stack
            setup_browser_vm
            success "VM services setup finished"
            ;;
        knowledge)
            setup_knowledge_base
            ;;
        desktop)
            setup_desktop
            ;;
        repair)
            repair_installation
            ;;
        *)
            error "Unknown setup type: $SETUP_TYPE"
            print_usage
            ;;
    esac

    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}           Setup Complete!               ${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "1. Configure your LLM API keys in config/config.yaml"
    echo "2. Start AutoBot with: bash run_autobot.sh --dev"
    echo "3. Access the web interface at: http://172.16.168.21:5173"
    echo "4. Access the desktop via VNC at: http://127.0.0.1:6080/vnc.html"
    echo ""
    echo -e "${YELLOW}For voice features:${NC}"
    echo "- Microphone access may require additional system setup"
    echo "- Voice interface is enabled by default in config"
    echo "- Test voice features in the web interface settings"
    echo ""
}

# Run main function
main "$@"
