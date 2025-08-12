#!/bin/bash
# AutoBot Hybrid Setup Script
# Sets up local development + containerized AI stack

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
PYTHON_VERSION="3.10.13"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

show_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                   AutoBot Hybrid Setup                      ║"
    echo "║              Local + Container Architecture                  ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_dependencies() {
    log_step "Checking system dependencies..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 not found. Please install Python 3.10.13"
        exit 1
    fi
    
    # Check pyenv
    if ! command -v pyenv &> /dev/null; then
        log_warning "pyenv not found. Using system Python."
    else
        # Install Python version if needed
        if ! pyenv versions | grep -q "$PYTHON_VERSION"; then
            log_info "Installing Python $PYTHON_VERSION via pyenv..."
            pyenv install "$PYTHON_VERSION"
        fi
        pyenv local "$PYTHON_VERSION"
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Please install Docker."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose not found. Please install Docker Compose."
        exit 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
    
    # Check Ollama
    if ! command -v ollama &> /dev/null; then
        log_warning "Ollama not found. Will install..."
        install_ollama
    fi
    
    log_success "All dependencies checked"
}

install_ollama() {
    log_step "Installing Ollama..."
    
    if command -v curl &> /dev/null; then
        curl -fsSL https://ollama.ai/install.sh | sh
    else
        log_error "curl not found. Please install Ollama manually: https://ollama.ai"
        exit 1
    fi
    
    # Start Ollama service
    if command -v systemctl &> /dev/null; then
        sudo systemctl enable ollama
        sudo systemctl start ollama
    else
        log_warning "Please start Ollama manually: ollama serve"
    fi
    
    log_success "Ollama installed"
}

setup_python_environment() {
    log_step "Setting up Python environment..."
    
    cd "$PROJECT_ROOT"
    
    # Create virtual environment
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        log_info "Created virtual environment"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install core requirements (minimal for local orchestrator)
    cat > requirements-local.txt << EOF
# Core AutoBot Local Dependencies (minimal for orchestrator)
fastapi>=0.115.0
uvicorn[standard]>=0.35.0
python-dotenv>=1.1.0
redis>=5.2.0
psutil>=5.9.0
requests>=2.32.0
aiohttp>=3.12.0
pyyaml>=6.0.0
structlog>=24.0.0

# For agent interface only (no heavy AI deps)
pydantic>=2.11.0
aiosqlite>=0.21.0

# Basic utilities
click>=8.2.0
rich>=14.0.0

# Testing
pytest>=8.3.0
pytest-asyncio>=0.25.0
EOF

    pip install -r requirements-local.txt
    
    log_success "Python environment setup complete"
}

setup_configuration() {
    log_step "Setting up configuration..."
    
    # Create config directory
    mkdir -p config logs data
    
    # Copy deployment configuration if it doesn't exist
    if [ ! -f "config/deployment.yaml" ]; then
        log_info "Deployment configuration already exists"
    else
        log_success "Using existing deployment configuration"
    fi
    
    # Create environment file
    cat > .env << EOF
# AutoBot Hybrid Environment Configuration
AUTOBOT_MODE=hybrid
AUTOBOT_DEBUG=true
AUTOBOT_LOG_LEVEL=INFO

# Local services
AUTOBOT_BACKEND_HOST=0.0.0.0
AUTOBOT_BACKEND_PORT=8001
REDIS_HOST=localhost
REDIS_PORT=6379

# Container services
AI_STACK_URL=http://localhost:8080
CONTAINER_ENABLED=true

# LLM Configuration
OLLAMA_HOST=http://localhost:11434
VLLM_ENABLED=true
OPENAI_ENABLED=false

# Privacy settings
DISABLE_EXTERNAL_APIS=true
LOCAL_ONLY=true
EOF

    log_success "Configuration setup complete"
}

install_ollama_models() {
    log_step "Installing Ollama models..."
    
    # Check if Ollama is running
    if ! curl -s http://localhost:11434/api/version &> /dev/null; then
        log_warning "Ollama not running, starting..."
        ollama serve &
        sleep 5
    fi
    
    # Install uncensored models
    models=(
        "dolphin-llama3:8b"
        "llama3.2:1b"
        "llama3.2:3b"
        "nomic-embed-text:latest"
    )
    
    for model in "${models[@]}"; do
        log_info "Installing model: $model"
        ollama pull "$model" || log_warning "Failed to install $model"
    done
    
    log_success "Ollama models installation complete"
}

build_ai_container() {
    log_step "Building AI stack container..."
    
    # Fix Docker build context path
    if [ ! -f "docker/ai-stack/requirements-ai.txt" ]; then
        log_error "AI stack requirements file not found"
        exit 1
    fi
    
    # Build AI stack container
    docker build -f docker/ai-stack/Dockerfile -t autobot-ai-stack:latest .
    
    log_success "AI stack container built"
}

build_npu_worker() {
    log_step "Building NPU worker container..."
    
    # Check if NPU worker files exist
    if [ ! -f "docker/npu-worker/requirements-npu.txt" ]; then
        log_error "NPU worker requirements file not found"
        exit 1
    fi
    
    # Build NPU worker container
    docker build -f docker/npu-worker/Dockerfile -t autobot-npu-worker:latest .
    
    log_success "NPU worker container built"
}

start_hybrid_services() {
    log_step "Starting hybrid services..."
    
    # Stop any existing standalone Redis containers first
    log_info "Stopping any existing standalone Redis containers..."
    docker stop redis-stack autobot-redis 2>/dev/null || true
    docker rm redis-stack autobot-redis 2>/dev/null || true
    
    # Start Redis and AI stack containers using Docker Compose
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    # Check for NPU hardware
    NPU_AVAILABLE=false
    if command -v lspci &>/dev/null && lspci | grep -i "neural\\|npu\\|ai" > /dev/null 2>&1; then
        NPU_AVAILABLE=true
        log_info "NPU hardware detected - enabling NPU worker"
    else
        log_info "No NPU hardware detected - running without NPU worker"
    fi
    
    log_info "Starting AutoBot services with Docker Compose..."
    if [ "$NPU_AVAILABLE" = true ]; then
        $COMPOSE_CMD -f docker-compose.hybrid.yml --profile npu up -d
    else
        $COMPOSE_CMD -f docker-compose.hybrid.yml up -d
    fi
    
    # Wait for services to start
    log_info "Waiting for services to start..."
    sleep 20
    
    # Check service health
    log_info "Checking service health..."
    
    # Check Redis health
    if docker exec autobot-redis redis-cli ping &> /dev/null; then
        log_success "Redis container is healthy"
    else
        log_warning "Redis container may not be ready yet"
    fi
    
    # Check AI stack health (with retry)
    for i in {1..6}; do
        if curl -s -f http://localhost:8080/health &> /dev/null; then
            log_success "AI stack container is healthy"
            break
        else
            if [ $i -eq 6 ]; then
                log_warning "AI stack container may not be ready yet (attempt $i/6)"
            else
                log_info "Waiting for AI stack container... (attempt $i/6)"
                sleep 10
            fi
        fi
    done
    
    # Show container status
    log_info "Container status:"
    docker ps --filter "name=autobot-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

run_tests() {
    log_step "Running setup validation tests..."
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Test base agent interface
    if python test_base_agents.py; then
        log_success "Base agent interface test passed"
    else
        log_warning "Base agent interface test failed"
    fi
    
    # Test container connectivity
    if curl -s -f http://localhost:8080/agents &> /dev/null; then
        log_success "Container connectivity test passed"
    else
        log_warning "Container connectivity test failed"
    fi
}

show_status() {
    log_step "Setup Summary"
    echo
    echo "🏗️  Architecture: Hybrid (Local Orchestrator + AI Containers)"
    echo "🐍 Python Environment: $(python --version 2>&1 || echo 'Not activated')"
    echo "🐳 Docker Containers:"
    
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(autobot-redis|autobot-ai-stack)"; then
        echo
    else
        echo "   No AutoBot containers running"
    fi
    
    echo "📊 Services Status:"
    # Check Redis
    if docker exec autobot-redis redis-cli ping &> /dev/null; then
        echo "   ✅ Redis: Running (autobot-redis)"
    else
        echo "   ❌ Redis: Not running"
    fi
    
    # Check Ollama
    if curl -s http://localhost:11434/api/version &> /dev/null; then
        echo "   ✅ Ollama: Running (local)"
    else
        echo "   ❌ Ollama: Not running"
    fi
    
    # Check AI Stack
    if curl -s -f http://localhost:8080/health &> /dev/null; then
        echo "   ✅ AI Stack Container: Running (autobot-ai-stack)"
    else
        echo "   ❌ AI Stack Container: Not running"
    fi
    
    # Check NPU Worker
    if curl -s -f http://localhost:8081/health &> /dev/null; then
        echo "   ✅ NPU Worker: Running (autobot-npu-worker)"
    else
        echo "   ❌ NPU Worker: Not running (NPU hardware may not be available)"
    fi
    
    echo
    echo "🌐 Network Configuration:"
    echo "   • AutoBot network: autobot-network"
    echo "   • Redis: autobot-redis:6379 (internal)"
    echo "   • AI Stack: localhost:8080 (external)"
    echo "   • NPU Worker: localhost:8081 (external)"
    echo "   • Ollama: host.docker.internal:11434 (from containers)"
    
    echo
    echo "📋 Next Steps:"
    echo "   1. Start AutoBot: ./run_agent.sh"
    echo "   2. Check containers: docker ps --filter 'name=autobot-'"
    echo "   3. View logs: docker-compose -f docker-compose.hybrid.yml logs"
    echo "   4. Test agents: python test_hybrid_agents.py"
    echo
}

show_help() {
    echo "AutoBot Hybrid Setup Script"
    echo
    echo "Usage: $0 [options]"
    echo
    echo "Options:"
    echo "  --local-only    Setup only local environment (no containers)"
    echo "  --containers-only    Setup only containers (no local Python)"
    echo "  --skip-models   Skip Ollama model installation"
    echo "  --skip-tests    Skip validation tests"
    echo "  --help          Show this help message"
    echo
    echo "Default: Full hybrid setup (local + containers)"
}

# Parse command line arguments
LOCAL_ONLY=false
CONTAINERS_ONLY=false
SKIP_MODELS=false
SKIP_TESTS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --local-only)
            LOCAL_ONLY=true
            shift
            ;;
        --containers-only)
            CONTAINERS_ONLY=true
            shift
            ;;
        --skip-models)
            SKIP_MODELS=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main setup process
main() {
    show_banner
    
    check_dependencies
    
    if [ "$CONTAINERS_ONLY" = false ]; then
        setup_python_environment
        setup_configuration
        
        if [ "$SKIP_MODELS" = false ]; then
            install_ollama_models
        fi
    fi
    
    if [ "$LOCAL_ONLY" = false ]; then
        build_ai_container
        build_npu_worker
        start_hybrid_services
    fi
    
    if [ "$SKIP_TESTS" = false ]; then
        run_tests
    fi
    
    show_status
    
    log_success "AutoBot hybrid setup complete!"
}

# Run main function
main "$@"