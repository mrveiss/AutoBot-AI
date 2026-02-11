#!/bin/bash

# Parse command line arguments
REPAIR_MODE=false
CHECK_ONLY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --repair|--check|--force-recreate|--update-deps|--fix-permissions|--verbose|--help)
            # Delegate to the new repair script
            exec ./setup_repair.sh "$@"
            ;;
        *)
            # Continue with normal setup
            break
            ;;
    esac
done

PATH="$(bash --norc -ec 'IFS=:; paths=($PATH);
for i in ${!paths[@]}; do
if [[ ${paths[i]} == "''${HOME}/.pyenv/shims''" ]]; then unset '\''paths[i]'\'';
fi; done;
echo "${paths[*]}"')"
export PATH="${HOME}/.pyenv/shims:${PATH}"
export PYENV_SHELL=bash

# CRITICAL FIX: Force tf-keras usage to fix Transformers compatibility with Keras 3
export TF_USE_LEGACY_KERAS=1
export KERAS_BACKEND=tensorflow
# Check if pyenv completion file exists before sourcing
if [ -f "${HOME}/.pyenv/completions/pyenv.bash" ]; then
    source "${HOME}/.pyenv/completions/pyenv.bash"
else
    echo "⚠️ Warning: pyenv completion file not found at ${HOME}/.pyenv/completions/pyenv.bash"
fi
command pyenv rehash 2>/dev/null
pyenv() {
  local command=${1:-}
  [ "$#" -gt 0 ] && shift
  case "$command" in
  activate|deactivate|rehash|shell)
    eval "$(pyenv "sh-$command" "$@")"
    ;;
  *)
    command pyenv "$command" "$@"
    ;;
  esac
}

# === AutoBot Setup Script ===
# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Go to project root (two levels up from scripts/setup/)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
echo "🔍 Detected project root: $PROJECT_ROOT"

# Change to project root directory
cd "$PROJECT_ROOT"

# Detect deployment environment and load appropriate configuration
if [ -f "./detect-environment.sh" ]; then
    echo "🔍 Detecting deployment environment..."
    source ./detect-environment.sh
else
    echo "⚠️  Environment detection script not found, using defaults"
fi

PYTHON_VERSION="3.10.13"
VENV_DIR="."
REQUIREMENTS_FILE="requirements.txt"
CONFIG_DIR="config"
CONFIG_TEMPLATE="${CONFIG_DIR}/config.yaml.template"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
VENV_HIGHER_DIR="venvs"
OPENVINO_VENV_NAME="openvino_env"
RUN_OPENVINO_SCRIPT="run_with_openvino.sh"
LOGS_DIR="logs"
DOCS_DIR="docs"
STATIC_DIR="frontend/static"
FRONTEND_DIR="autobot-slm-frontend"

echo "🔧 Starting AutoBot setup..."

# Ensure required folders exist (including new architecture directories)
mkdir -p "$CONFIG_DIR" "$LOGS_DIR" "$DOCS_DIR" "$STATIC_DIR"

# Create new architecture directories
echo "📁 Creating Docker architecture directories..."
mkdir -p docker/volumes/{prompts,knowledge_base,config,uploads,fluentd}
mkdir -p docker/volumes/config
mkdir -p logs/autobot-centralized
mkdir -p logs/autobot-all-logs
echo "✅ Docker architecture directories created."

# --- 1. Verify Python 3.10 via pyenv ---
echo "🔍 Checking for Python $PYTHON_VERSION with pyenv..."

if ! command -v pyenv &>/dev/null; then
    echo "❌ pyenv not found. Please install it manually:"
    echo "
# Install pyenv + build tools
sudo apt update && sudo apt install -y make build-essential libssl-dev zlib1g-dev \\
  libbz2-dev libreadline-dev libsqlite3-dev curl llvm libncursesw5-dev xz-utils tk-dev \\
  libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev git yq

# Install pyenv
curl https://pyenv.run | bash

# Add to shell
echo -e '\nexport PYENV_ROOT=\"\$HOME/.pyenv\"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH=\"\$PYENV_ROOT/bin:\$PATH\"' >> ~/.bashrc
echo 'eval \"\$(pyenv init -)\"' >> ~/.bashrc
exec \"\$SHELL\"

# Then install Python
pyenv install $PYTHON_VERSION
pyenv global $PYTHON_VERSION
"
    exit 1
fi

# Ensure Python 3.10 is installed
if ! pyenv versions | grep -q "$PYTHON_VERSION"; then
    echo "❌ Python $PYTHON_VERSION not installed. Installing build dependencies..."
    sudo apt update && sudo apt install -y make build-essential libssl-dev zlib1g-dev \\
  libbz2-dev libreadline-dev libsqlite3-dev curl llvm libncursesw5-dev xz-utils tk-dev \\
  libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev git redis-server pciutils yq || { echo "❌ Failed to install build dependencies and pciutils."; exit 1; }
    echo "Installing Python $PYTHON_VERSION..."
    sudo pyenv install "$PYTHON_VERSION" || { echo "❌ Failed to install Python $PYTHON_VERSION."; exit 1; }
    pyenv global "$PYTHON_VERSION"
fi

# --- 2. Install and Configure Docker in WSL2 ---
echo "🔍 Checking for Docker installation in WSL2..."
if ! command -v docker &>/dev/null; then
    echo "❌ Docker not found in WSL2. Installing Docker..."
    sudo apt update
    sudo apt install -y apt-transport-https ca-certificates curl software-properties-common || { echo "❌ Failed to install Docker prerequisites."; exit 1; }
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg || { echo "❌ Failed to add Docker GPG key."; exit 1; }
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null || { echo "❌ Failed to add Docker APT repository."; exit 1; }
    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io || { echo "❌ Failed to install Docker Engine."; exit 1; }
    echo "✅ Docker installed in WSL2."
else
    echo "✅ Docker already installed in WSL2."
fi

# Add current user to docker group
if ! id -nG "$USER" | grep -qw "docker"; then
    echo "Adding user '$USER' to the 'docker' group..."
    sudo usermod -aG docker "$USER" || { echo "❌ Failed to add user to docker group."; exit 1; }
    echo "✅ User '$USER' added to 'docker' group. Please log out and log back in for changes to take effect."
    echo "You may need to run 'newgrp docker' or restart your terminal for changes to apply immediately."
    exit 1 # Exit to prompt user to re-login for group changes to apply
fi

# Check if we're using Docker Desktop (no need to start daemon)
if [[ "$AUTOBOT_ENVIRONMENT" == "wsl-docker-desktop" ]]; then
    echo "🐳 Using Docker Desktop - daemon already managed by Windows"
    # Set Docker API version for compatibility
    export DOCKER_API_VERSION=1.43
else
    # Start Docker daemon (if not running) for native Linux environments
    echo "🔄 Starting Docker daemon..."
    if ! pgrep dockerd >/dev/null; then
        # Ensure the Docker socket directory exists and has correct permissions
        sudo mkdir -p /var/run/docker || { echo "❌ Failed to create /var/run/docker."; exit 1; }
        sudo chmod 755 /var/run/docker || { echo "❌ Failed to set permissions on /var/run/docker."; exit 1; }

        # Start dockerd in the background
        sudo dockerd > /dev/null 2>&1 &
        DOCKERD_PID=$!
        echo "✅ Docker daemon started (PID: $DOCKERD_PID)."

        # Give dockerd some time to initialize
        echo "Waiting for Docker daemon to be ready..."
        sleep 5

        # Verify Docker daemon is responsive
        if ! docker info >/dev/null 2>&1; then
            echo "❌ Docker daemon is not responsive after startup. Please check Docker logs."
            exit 1
        else
            echo "✅ Docker daemon is responsive."
        fi
    else
        echo "✅ Docker daemon is already running."
    fi
fi

# --- 3. Deploy/Start Redis Stack Docker Container (using local Docker) ---
echo "🔍 Checking for existing Redis Stack Docker container..."
# Check for either 'redis-stack' or 'autobot-redis' containers
if docker ps -a --format '{{.Names}}' | grep -qE '^(redis-stack|autobot-redis)$'; then
    # Find which container exists
    REDIS_CONTAINER=$(docker ps -a --format '{{.Names}}' | grep -E '^(redis-stack|autobot-redis)$' | head -1)
    echo "✅ Redis container '$REDIS_CONTAINER' found."
    if docker inspect -f '{{.State.Running}}' "$REDIS_CONTAINER" | grep -q 'true'; then
        echo "✅ Redis container '$REDIS_CONTAINER' is already running."
    else
        echo "🔄 Redis container '$REDIS_CONTAINER' found but not running. Starting it..."
        docker start "$REDIS_CONTAINER" || { echo "❌ Failed to start Redis container."; exit 1; }
        echo "✅ Redis container '$REDIS_CONTAINER' started."
    fi
else
    echo "📦 No Redis container found. Using docker-compose to deploy..."
    docker-compose -f docker/compose/docker-compose.hybrid.yml up -d autobot-redis || {
        echo "❌ Failed to deploy Redis container via docker-compose."
        echo "   Trying direct docker run as fallback..."
        docker run -d --name redis-stack -p 6379:6379 redis/redis-stack-server:latest || {
            echo "❌ Failed to deploy Redis container.";
            exit 1;
        }
    }
    echo "✅ Redis container deployed and started."
fi

# Assume Redis Stack is ready if Docker command succeeded
echo "Assuming Redis Stack is ready and accessible via ${AUTOBOT_REDIS_HOST:-192.168.65.10}:${AUTOBOT_REDIS_PORT:-6379} from within WSL2."
echo "Please ensure the 'redis-stack' Docker container is running and healthy."

# --- 3.5. GUI Testing Setup ---
echo "🌐 GUI testing will use npm-installed Playwright (no additional system dependencies needed)"
echo "✅ GUI testing ready - Playwright will download browsers automatically when needed"

# --- 4. Deploy/Start Playwright Service Docker Container ---
echo "🔍 Checking for existing 'autobot-playwright' Docker container..."
if docker ps -a --format '{{.Names}}' | grep -q '^autobot-playwright$'; then
    echo "✅ 'autobot-playwright' container found."
    if docker inspect -f '{{.State.Running}}' autobot-playwright | grep -q 'true'; then
        echo "✅ 'autobot-playwright' container is already running."
    else
        echo "🔄 'autobot-playwright' container found but not running. Starting it..."
        docker start autobot-playwright || { echo "❌ Failed to start 'autobot-playwright' container."; exit 1; }
        echo "✅ 'autobot-playwright' container started."
    fi
else
    echo "📦 'autobot-playwright' container not found. Deploying with docker-compose..."

    # Check if docker-compose is available
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        echo "❌ Neither docker-compose nor docker compose is available. Please install Docker Compose."
        exit 1
    fi

    # Deploy Playwright service using docker-compose
    if [ -f "docker/compose/docker-compose.playwright-vnc.yml" ]; then
        $COMPOSE_CMD -f docker/compose/docker-compose.playwright-vnc.yml up -d || {
            echo "❌ Failed to deploy 'autobot-playwright' container.";
            exit 1;
        }
    elif [ -f "docker-compose.playwright.yml" ]; then
        $COMPOSE_CMD -f docker-compose.playwright.yml up -d || {
            echo "❌ Failed to deploy 'autobot-playwright' container.";
            exit 1;
        }
    else
        echo "❌ No Playwright Docker Compose file found."
        exit 1
    fi
    echo "✅ 'autobot-playwright' container deployed and started."

    # Wait for service to be healthy
    echo "⏳ Waiting for Playwright service to be ready..."
    for i in {1..30}; do
        if curl -sf http://${AUTOBOT_PLAYWRIGHT_HOST:-192.168.65.80}:${AUTOBOT_PLAYWRIGHT_API_PORT:-3000}/health > /dev/null 2>&1; then
            echo "✅ Playwright service is healthy and ready."
            break
        fi
        echo "⏳ Waiting for Playwright service... (attempt $i/30)"
        sleep 2
    done

    if ! curl -sf http://${AUTOBOT_PLAYWRIGHT_HOST:-192.168.65.80}:${AUTOBOT_PLAYWRIGHT_API_PORT:-3000}/health > /dev/null 2>&1; then
        echo "⚠️ Playwright service health check failed, but continuing setup..."
    fi
fi

pyenv global "$PYTHON_VERSION"

# --- 2. Create AutoBot venv ---
VENV_PATH="venv"
echo "📦 Ensuring clean venv: $VENV_PATH..."
rm -rf "$VENV_PATH" # Remove existing venv to ensure a clean install

echo "📦 Creating venv: $VENV_PATH..."
eval "$(pyenv init -)"
export PATH="${HOME}/.pyenv/shims:$PATH"
echo "--- PYENV DEBUG INFO ---"
pyenv --version
pyenv versions
echo "--- END PYENV DEBUG INFO ---"
"${HOME}/.pyenv/versions/$PYTHON_VERSION/bin/python" -m venv "$VENV_PATH" || { echo "❌ Failed to create venv."; exit 1; }
echo "✅ Virtual environment $VENV_PATH created."

# --- 3. Setup Redis Database Separation Configuration ---
echo "🔧 Setting up Redis database separation configuration..."
cat > docker/volumes/config/redis-databases.yaml << 'EOF'
# Redis Database Separation Configuration
# AutoBot uses 11 isolated databases for different data types
databases:
  main: 0           # Main application data
  knowledge: 1      # Knowledge base and documents
  prompts: 2        # Prompt templates and management
  agents: 3         # Agent communication
  metrics: 4        # Performance metrics
  cache: 5          # General caching
  sessions: 6       # User sessions
  tasks: 7          # Task management
  logs: 8           # Log data
  temp: 9           # Temporary data
  backup: 10        # Backup data
EOF
echo "✅ Redis database separation configuration created."

# Create environment variables for Docker
echo "🔧 Setting up Docker environment configuration..."
cat > docker/env/redis.env << 'EOF'
# Redis Database Separation Environment Variables
REDIS_HOST=autobot-redis
REDIS_PORT=6379
REDIS_URL=redis://autobot-redis:6379

# Database assignments
REDIS_DB_MAIN=0
REDIS_DB_KNOWLEDGE=1
REDIS_DB_PROMPTS=2
REDIS_DB_AGENTS=3
REDIS_DB_METRICS=4
REDIS_DB_CACHE=5
REDIS_DB_SESSIONS=6
REDIS_DB_TASKS=7
REDIS_DB_LOGS=8
REDIS_DB_TEMP=9
REDIS_DB_BACKUP=10
EOF
echo "✅ Docker environment configuration created."

# --- 4. Activate and install main requirements ---
echo "--- Python Dependencies Installation for Multi-Agent Architecture ---"
source "$VENV_PATH/bin/activate"
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "⚠️ Warning: $REQUIREMENTS_FILE not found. Skipping pip install."
else
    echo "📦 Installing requirements in optimized groups for multi-agent architecture..."

    # Group 1: Core Framework Dependencies
    echo "⬇️ Installing Group 1: Core Framework Dependencies..."
    cat > requirements_group_1.txt << EOF
fastapi>=0.115.0
starlette>=0.47.2
uvicorn>=0.30.0
requests==2.31.0
pyyaml==6.0.1
pydantic>=2.8.0
websockets>=11.0.0
aiohttp>=3.9.0
beautifulsoup4>=4.12.0
redis>=5.0,<6.0
psutil>=5.9.0
click>=8.1.0
python-dotenv>=1.0.0
jsonschema>=4.20.0
validators>=0.22.0
cryptography>=45.0.0
EOF
    pip install -r requirements_group_1.txt || { echo "❌ Failed to install Group 1 requirements."; deactivate; exit 1; }
    echo "✅ Group 1 dependencies installed."

    # Group 2: AI/ML Framework Dependencies (Critical for Multi-Agent)
    echo "⬇️ Installing Group 2: AI/ML Framework Dependencies..."
    cat > requirements_group_2.txt << EOF
torch>=2.8.0
transformers>=4.53.0
sentence-transformers>=2.2.0
tiktoken>=0.5.0
numpy>=1.26.0
pillow>=10.0.0
EOF
    pip install -r requirements_group_2.txt || { echo "❌ Failed to install Group 2 requirements."; deactivate; exit 1; }
    echo "✅ Group 2 dependencies installed."

    # Group 3: LangChain Ecosystem
    echo "⬇️ Installing Group 3: LangChain Ecosystem..."
    cat > requirements_group_3.txt << EOF
langchain
langchain-community
langchain-experimental
EOF
    pip install -r requirements_group_3.txt || { echo "❌ Failed to install Group 3 requirements."; deactivate; exit 1; }
    echo "✅ Group 3 dependencies installed."

    # Group 4: LlamaIndex Ecosystem
    echo "⬇️ Installing Group 4: LlamaIndex Ecosystem..."
    cat > requirements_group_4.txt << EOF
llama-index
llama-index-llms-ollama
llama-index-embeddings-ollama
llama-index-vector-stores-redis
llama-index-readers-file
EOF
    pip install -r requirements_group_4.txt || { echo "❌ Failed to install Group 4 requirements."; deactivate; exit 1; }
    echo "✅ Group 4 dependencies installed."

    # Group 5: Specialized Agent Dependencies
    echo "⬇️ Installing Group 5: Specialized Agent Dependencies..."
    cat > requirements_group_5.txt << EOF
chromadb>=0.4.0
httpx>=0.25.0
sh>=2.0.0
python-docx>=1.1.0
pypdf>=6.0.0
markdownify==0.11.6
nltk>=3.8.0
textstat>=0.7.3
EOF
    pip install -r requirements_group_5.txt || { echo "❌ Failed to install Group 5 requirements."; deactivate; exit 1; }
    echo "✅ Group 5 dependencies installed."

    # Group 6: GUI Automation & System Integration
    echo "⬇️ Installing Group 6: GUI Automation & System Integration..."
    cat > requirements_group_6.txt << EOF
pyautogui==0.9.54
mouseinfo==0.1.3
opencv-python>=4.8.0
pygetwindow>=0.0.9
EOF
    pip install -r requirements_group_6.txt || { echo "❌ Failed to install Group 6 requirements."; deactivate; exit 1; }
    echo "✅ Group 6 dependencies installed."

    # Group 7: Monitoring & Development Tools (including centralized logging)
    echo "⬇️ Installing Group 7: Monitoring & Development Tools..."
    cat > requirements_group_7.txt << EOF
rich>=13.7.0
tqdm>=4.66.0
structlog>=23.2.0
prometheus-client>=0.19.0
pre-commit>=3.6.0
detect-secrets>=1.4.0
flake8>=6.0.0
pytest>=7.4.0
EOF
    pip install -r requirements_group_7.txt || { echo "❌ Failed to install Group 7 requirements."; deactivate; exit 1; }
    echo "✅ Group 7 dependencies installed."

    # Group 8: Async Architecture Dependencies
    echo "⬇️ Installing Group 8: Async Architecture Dependencies..."
    cat > requirements_group_8.txt << EOF
redis>=5.0.0,<6.0
aioredis>=2.0.0
pydantic-settings>=2.0.0
tenacity>=8.0.0
docker>=7.0.0
pyyaml>=6.0.1
jsonschema>=4.20.0
ast-tools>=0.1.0
EOF
    pip install -r requirements_group_8.txt || { echo "❌ Failed to install Group 8 requirements."; deactivate; exit 1; }
    echo "✅ Group 8 dependencies installed."

    # Clean up temporary files
    rm requirements_group_*.txt
    echo "✅ All Multi-Agent Architecture dependencies installed."
fi

# Ensure GUI automation dependencies are installed (these are already in group 1, but keeping for redundancy/clarity)
echo "📦 Installing GUI automation dependencies (pyautogui, mouseinfo, pillow, numpy)..."
pip install pyautogui mouseinfo pillow numpy || { echo "⚠️ Failed to install GUI automation dependencies. Continuing without GUI support."; }
echo "✅ GUI automation dependencies installation attempted."

# Ensure Redis Python client is installed for application integration (already in group 1)
echo "📦 Installing Redis Python client (redis-py)..."
pip install redis || { echo "⚠️ Failed to install Redis client. Continuing without Redis support."; }
echo "✅ Redis Python client installation attempted."

# --- Install OpenVINO for NPU acceleration ---
echo "📦 Installing OpenVINO for NPU and GPU acceleration..."
pip install openvino openvino-dev[pytorch,tensorflow2] || {
    echo "⚠️ Failed to install OpenVINO. Trying with reduced dependencies...";
    pip install openvino || {
        echo "⚠️ Failed to install OpenVINO completely. Continuing without OpenVINO support.";
    }
}
echo "✅ OpenVINO installation attempted."

# Check for Intel NPU drivers on system
echo "🔍 Checking for Intel NPU driver support..."
# Ensure lspci is available
if ! command -v lspci &>/dev/null; then
    echo "⚠️ lspci command not found. Attempting to install pciutils..."
    sudo apt update && sudo apt install -y pciutils || { echo "❌ Failed to install pciutils. Cannot check for NPU hardware."; }
fi

if command -v lspci &>/dev/null && lspci | grep -i "neural\|npu\|ai" > /dev/null 2>&1; then
    echo "✅ Intel NPU hardware detected via lspci"

    # Check if Intel NPU driver is installed
    if ls /dev/intel_npu* > /dev/null 2>&1; then
        echo "✅ Intel NPU driver appears to be installed"
    else
        echo "⚠️ Intel NPU hardware detected but driver may not be installed"
        echo "   Install Intel NPU driver from: https://github.com/intel/intel-npu-acceleration-library"
    fi
else
    echo "ℹ️ No Intel NPU hardware detected via lspci"
fi

# Test OpenVINO installation
echo "🧪 Testing OpenVINO installation..."
python3 -c "
try:
    from openvino.runtime import Core
    core = Core()
    devices = core.available_devices
    print(f'✅ OpenVINO installed successfully. Available devices: {devices}')

    # Check for NPU specifically
    npu_devices = [d for d in devices if 'NPU' in d]
    if npu_devices:
        print(f'🚀 NPU devices available: {npu_devices}')
    else:
        print('ℹ️ No NPU devices detected by OpenVINO')

except ImportError as e:
    print(f'❌ OpenVINO import failed: {e}')
except Exception as e:
    print(f'⚠️ OpenVINO test failed: {e}')
" || echo "⚠️ OpenVINO test script failed"

# --- Voice Interface Setup (Optional) ---
echo "🎤 Setting up voice interface (optional)..."

# Ask user if they want voice interface support
echo "Do you want to install voice interface support? (y/N)"
echo "Note: Requires system audio libraries and may fail in some environments."
read -r -n 1 voice_choice
echo

if [[ $voice_choice =~ ^[Yy]$ ]]; then
    echo "📦 Installing system audio dependencies..."

    # Install system dependencies based on OS
    if command -v apt-get &>/dev/null; then
        # Ubuntu/Debian (including centralized logging dependencies)
        sudo apt-get update && sudo apt-get install -y \
            portaudio19-dev python3-pyaudio \
            espeak espeak-data libespeak1 libespeak-dev \
            flac \
            jq \
            yq \
            curl \
            netcat-openbsd || {
            echo "⚠️ Failed to install some system audio dependencies"
        }
    elif command -v brew &>/dev/null; then
        # macOS
        brew install portaudio espeak yq || {
            echo "⚠️ Failed to install some system audio dependencies"
        }
    else
        echo "⚠️ Unknown system - please install audio libraries manually"
        echo "   See docs/VOICE_INTERFACE_SETUP.md for details"
    fi

    echo "📦 Installing Python voice interface dependencies..."
    pip install -r requirements-voice.txt || {
        echo "⚠️ Failed to install voice interface dependencies"
        echo "   Voice interface will be disabled"
        echo "   See docs/VOICE_INTERFACE_SETUP.md for troubleshooting"
    }

    # Test voice interface
    echo "🧪 Testing voice interface..."
    python3 -c "
try:
    import speech_recognition as sr
    import pyaudio
    import gtts
    print('✅ Voice interface dependencies installed successfully')

    # Test microphone access
    r = sr.Recognizer()
    mic_list = sr.Microphone.list_microphone_names()
    print(f'📱 Found {len(mic_list)} microphone(s)')

except ImportError as e:
    print(f'⚠️ Voice interface import failed: {e}')
except Exception as e:
    print(f'⚠️ Voice interface test failed: {e}')
" || echo "⚠️ Voice interface test failed"

    echo "✅ Voice interface setup completed (check results above)"
else
    echo "⏭️ Skipping voice interface setup"
    echo "   You can install it later with: pip install -r requirements-voice.txt"
fi

# --- 4. Install Required Ollama Models for Multi-Agent Architecture ---
echo "🤖 Installing required Ollama models for multi-agent architecture..."

# Check if Ollama is installed
if ! command -v ollama &>/dev/null; then
    echo "❌ Ollama not found. Please install Ollama first:"
    echo "curl -fsSL https://ollama.com/install.sh | sh"
    echo "Then run this setup script again."
    exit 1
fi

# Function to install model with retry logic
install_ollama_model() {
    local model=$1
    local description=$2
    echo "📥 Installing $description ($model)..."

    # Check if model is already installed
    if ollama list | grep -q "$model"; then
        echo "✅ $description ($model) already installed."
        return 0
    fi

    # Install with timeout and retry
    local max_attempts=3
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        echo "⏳ Attempt $attempt/$max_attempts: Installing $model..."

        if timeout 600s ollama pull "$model"; then
            echo "✅ Successfully installed $description ($model)"
            return 0
        else
            echo "❌ Failed to install $model (attempt $attempt/$max_attempts)"
            if [ $attempt -eq $max_attempts ]; then
                echo "💡 You can manually install this model later with: ollama pull $model"
                return 1
            fi
            attempt=$((attempt + 1))
            echo "⏳ Waiting 10 seconds before retry..."
            sleep 10
        fi
    done
}

# Install required uncensored models for multi-agent architecture
echo "🎯 Installing uncensored models for unrestricted multi-agent capabilities..."

# Primary uncensored models for the architecture
# Try known uncensored models that actually exist
install_ollama_model "dolphin-llama3:8b" "Uncensored Chat & System Commands Agent (Dolphin Llama3 8B)"
install_ollama_model "wizard-vicuna-uncensored:13b" "Uncensored Orchestrator Agent (Wizard Vicuna 13B)"
# Fallback to standard models if uncensored not available
install_ollama_model "llama3.2:1b" "Fallback Chat Agent (Llama 3.2 1B)"
install_ollama_model "llama3.2:3b" "Fallback Orchestrator Agent (Llama 3.2 3B)"

# Embedding model for knowledge base (no uncensored variant needed)
install_ollama_model "nomic-embed-text:latest" "Knowledge Base Embeddings"

# Fallback: Try general uncensored model if specific sizes not available
if ! ollama list | grep -q "artifish/llama3.2-uncensored:1b"; then
    echo "⚠️ Specific 1B uncensored model not available, trying general uncensored..."
    install_ollama_model "artifish/llama3.2-uncensored:latest" "General Uncensored Model (will use for 1B tasks)"
fi

if ! ollama list | grep -q "artifish/llama3.2-uncensored:3b"; then
    echo "⚠️ Specific 3B uncensored model not available, trying general uncensored..."
    if ! ollama list | grep -q "artifish/llama3.2-uncensored:latest"; then
        install_ollama_model "artifish/llama3.2-uncensored:latest" "General Uncensored Model (will use for 3B tasks)"
    fi
fi

# Install standard models as ultimate fallback only
echo "🔄 Installing standard models as ultimate fallback..."
install_ollama_model "llama3.2:1b-instruct-q4_K_M" "Standard 1B Fallback"
install_ollama_model "llama3.2:3b-instruct-q4_K_M" "Standard 3B Fallback"

# Verify model installation
echo "🔍 Verifying installed models..."
ollama list

# Test model functionality with uncensored models first
echo "🧪 Testing uncensored model functionality..."
echo "Testing 1B uncensored model for chat agent..."
echo "Hello, test!" | ollama run artifish/llama3.2-uncensored:1b >/dev/null 2>&1 || \
echo "Hello, test!" | ollama run artifish/llama3.2-uncensored:latest >/dev/null 2>&1 || \
echo "Hello, test!" | ollama run llama3.2:1b-instruct-q4_K_M >/dev/null 2>&1 || \
echo "⚠️ Warning: 1B model test failed"

echo "Testing 3B uncensored model for orchestrator..."
echo "Plan a simple task" | ollama run artifish/llama3.2-uncensored:3b >/dev/null 2>&1 || \
echo "Plan a simple task" | ollama run artifish/llama3.2-uncensored:latest >/dev/null 2>&1 || \
echo "Plan a simple task" | ollama run llama3.2:3b-instruct-q4_K_M >/dev/null 2>&1 || \
echo "⚠️ Warning: 3B model test failed"

echo "✅ Ollama model installation and verification completed!"

# --- 5. Check and install Node.js and npm via nvm ---
echo "🔍 Checking for nvm (Node Version Manager)..."
if ! command -v nvm &>/dev/null; then
    echo "📦 nvm not found. Installing nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash || { echo "❌ Failed to install nvm."; exit 1; }
    # Source nvm to make it available in the current shell
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
else
    echo "✅ nvm already installed."
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
fi

NODE_VERSION="20" # Target Node.js 20.x LTS
echo "📦 Installing Node.js $NODE_VERSION and compatible npm via nvm..."
nvm install "$NODE_VERSION" || { echo "❌ Failed to install Node.js $NODE_VERSION."; exit 1; }
nvm use "$NODE_VERSION" || { echo "❌ Failed to use Node.js $NODE_VERSION."; exit 1; }
nvm alias default "$NODE_VERSION" # Set as default for future shells

# Ensure nvm's shims are in PATH for subsequent commands
export PATH="$NVM_DIR/versions/node/v${NODE_VERSION}/bin:$PATH"

echo "Node.js version: $(node -v)"
echo "npm version: $(npm -v)"

# --- 5. Set up frontend ---
echo "🎨 Setting up frontend..."
# Navigate to frontend directory
cd $FRONTEND_DIR

# Store the absolute path of the frontend directory
FRONTEND_ABS_PATH="$(pwd)"

# Clean existing build and old GUI remnants with timeout protection
echo "🧹 Cleaning previous build and old GUI remnants..."
timeout 30s rm -rf dist node_modules 2>/dev/null || {
    echo "⚠️ Warning: Cleanup timed out or failed. Continuing..."
}
timeout 10s rm -rf ../../old_static/* 2>/dev/null || true
timeout 10s rm -rf ../../frontend/templates/* 2>/dev/null || true

# Kill any lingering npm processes
echo "🔍 Cleaning up any lingering npm processes..."
pkill -f "npm" 2>/dev/null || true
sleep 1

# Install dependencies with timeout
echo "📦 Installing dependencies..."
timeout 300s npm install || {
    echo "❌ npm install timed out. Trying with --force flag..."
    timeout 300s npm install --force || {
        echo "❌ Failed to install dependencies even with --force. Please check your internet connection and npm registry."
        exit 1
    }
}

# Install XTerm.js dependencies for terminal functionality
echo "📦 Installing XTerm.js dependencies..."
timeout 300s npm install @xterm/xterm @xterm/addon-fit @xterm/addon-web-links || {
    echo "❌ Failed to install XTerm.js dependencies. Trying with --force..."
    timeout 300s npm install --force @xterm/xterm @xterm/addon-fit @xterm/addon-web-links || {
        echo "⚠️ Warning: Failed to install XTerm.js dependencies. Terminal functionality may be limited."
        # Don't exit here, continue setup
    }
}

# Install Playwright browsers for GUI testing
echo "🌐 Installing Playwright browsers for GUI testing..."
npx playwright install --with-deps || {
    echo "⚠️ Failed to install Playwright browsers with system dependencies."
    echo "   Trying without system dependencies..."
    npx playwright install || {
        echo "⚠️ Failed to install Playwright browsers. GUI testing will be limited."
        echo "   You can manually install later with: npx playwright install"
    }
}
echo "✅ Playwright browser installation completed."

# Build frontend with timeout
echo "🏗️ Building frontend..."
timeout 180s npm run build || {
    echo "❌ Frontend build timed out or failed. Please check for build errors."
    exit 1
}

# Debug: Check current directory and dist contents
echo "🔍 Debugging: Current working directory is:"
pwd
echo "🔍 Debugging: Contents of dist are:"
ls -la dist || echo "Directory dist not found."

# Ensure static directory exists within frontend folder
cd ..
mkdir -p $STATIC_DIR

# Clean static directory before copying new files
echo "🧹 Cleaning static directory..."
rm -rf $STATIC_DIR/*

# Check if dist directory exists and contains files
echo "🔍 Checking for build output..."
DIST_PATH="$FRONTEND_ABS_PATH/dist"
STATIC_PATH="$(realpath ./$STATIC_DIR)"
if [ -d "$DIST_PATH" ]; then
    shopt -s nullglob
    files=("$DIST_PATH"/*)
    if [ ${#files[@]} -gt 0 ]; then
        # Copy build files to static directory with force overwrite
        echo "📋 Copying build files to static directory..."
        cp -rf "$DIST_PATH/." "$STATIC_PATH/" || { echo "❌ Failed to copy build files to static directory."; exit 1; }
    else
        echo "❌ Error: Build output directory $DIST_PATH exists but is empty."
        exit 1
    fi
else
    echo "❌ Error: Build output directory $DIST_PATH does not exist."
    exit 1
fi

echo "✅ Frontend setup complete!"
echo "Access the Vue app at http://${AUTOBOT_FRONTEND_HOST:-127.0.0.1}:${AUTOBOT_FRONTEND_PORT:-5173} (development)"
echo "The built files are served from the backend at http://${AUTOBOT_BACKEND_HOST:-127.0.0.1}:${AUTOBOT_BACKEND_PORT:-8001}"

# --- 6. Copy default config if needed ---
# Use the project root directory detected at script start
echo "🔍 Using project root directory: $SCRIPT_DIR"

# Verify we're in the correct directory by checking for key files
if [ ! -f "main.py" ] || [ ! -d "src" ] || [ ! -f "run_agent.sh" ]; then
    echo "❌ Error: Script must be run from the AutoBot project directory"
    echo "Expected files: main.py, src/, run_agent.sh"
    echo "Current directory: $(pwd)"
    echo "Please cd to the AutoBot directory and run the script again"
    exit 1
fi

echo "✅ Confirmed running from AutoBot project directory"

if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "$CONFIG_TEMPLATE" ]; then
        echo "📄 Copying $CONFIG_TEMPLATE to $CONFIG_FILE..."
        cp "$CONFIG_TEMPLATE" "$CONFIG_FILE" || { echo "❌ Failed to copy config file."; exit 1; }
    else
        echo "⚠️ Warning: Config template $CONFIG_TEMPLATE not found. Creating a basic config file..."
        mkdir -p "$CONFIG_DIR"
        cat > "$CONFIG_FILE" << 'EOF'
# Basic AutoBot Configuration
server:
  host: "0.0.0.0"
  port: 8001

logging:
  level: "INFO"
  file: "logs/autobot.log"

models:
  default: "tinyllama"
EOF
        echo "✅ Basic config file created at $CONFIG_FILE."
    fi
fi

# Update config file with correct message display defaults
echo "🔧 Updating config file with correct message display defaults..."
update_message_display_defaults() {
    if [ -f "$CONFIG_FILE" ]; then
        # Use sed to update the message_display section with correct defaults
        sed -i.bak '
            /^message_display:$/,/^[a-zA-Z]/ {
                s/^  show_debug: true$/  show_debug: false/
                s/^  show_json: true$/  show_json: false/
                s/^  show_utility: true$/  show_utility: false/
            }
        ' "$CONFIG_FILE"

        echo "✅ Updated message display defaults in $CONFIG_FILE"
        echo "   - show_debug: false (was potentially true)"
        echo "   - show_json: false (was potentially true)"
        echo "   - show_utility: false (was potentially true)"
        echo "   - Backup saved as: ${CONFIG_FILE}.bak"
    else
        echo "⚠️ Config file not found at $CONFIG_FILE"
    fi
}

# Run the config update
update_message_display_defaults

# --- 7. Validate Configuration and Module Imports ---
echo "🔍 Validating configuration and module imports..."

# Ensure we're back in the root directory and activate virtual environment
cd "$SCRIPT_DIR"
echo "🔍 Current working directory: $(pwd)"
echo "🔍 Looking for virtual environment at: $SCRIPT_DIR/$VENV_PATH"

# Check if virtual environment directory exists
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment directory not found at $VENV_PATH"
    echo "🔍 Contents of current directory:"
    ls -la
    exit 1
fi

# Ensure the activate script is executable
chmod +x "$VENV_PATH/bin/activate"

# Activate the virtual environment
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
    echo "✅ Virtual environment activated successfully."
else
    echo "❌ Virtual environment activation script not found at $VENV_PATH/bin/activate"
    echo "🔍 Contents of venv/bin directory:"
    ls -la "$VENV_PATH/bin/" || echo "Directory does not exist"
    exit 1
fi

# Add current directory to PYTHONPATH for module discovery
export PYTHONPATH=$(pwd)

# Function to initialize system knowledge and Redis database separation
initialize_system_knowledge() {
    echo "🔄 Initializing system knowledge and Redis database separation..."

    python3 -c "
import asyncio
import sys
from src.knowledge_base import KnowledgeBase
from src.agents.system_knowledge_manager import SystemKnowledgeManager

async def init_knowledge():
    try:
        kb = KnowledgeBase()
        await kb.ainit()

        manager = SystemKnowledgeManager(kb)
        await manager.initialize_system_knowledge()

        print('✅ System knowledge initialized successfully!')
        return True
    except Exception as e:
        print(f'❌ Failed to initialize system knowledge: {e}')
        import traceback
        traceback.print_exc()
        return False

# Run the async function
result = asyncio.run(init_knowledge())
sys.exit(0 if result else 1)
"

    if [ $? -eq 0 ]; then
        echo "✅ System knowledge initialization completed!"
    else
        echo "❌ System knowledge initialization failed!"
        echo "⚠️ AutoBot will still work, but without pre-loaded system knowledge."
        echo "You can retry initialization later by running the agent."
    fi
}

# Function to test Redis database separation
test_redis_separation() {
    echo "🧪 Testing Redis database separation..."

    python3 -c "
try:
    from src.utils.redis_database_manager import redis_db_manager

    # Test database separation
    if redis_db_manager.validate_database_separation():
        print('✅ Redis database separation validated')

        # Test different database connections
        main_client = redis_db_manager.get_connection('main')
        knowledge_client = redis_db_manager.get_connection('knowledge')
        prompts_client = redis_db_manager.get_connection('prompts')

        # Test isolation
        main_client.set('test_key', 'main_value')
        knowledge_client.set('test_key', 'knowledge_value')
        prompts_client.set('test_key', 'prompts_value')

        main_val = main_client.get('test_key')
        knowledge_val = knowledge_client.get('test_key')
        prompts_val = prompts_client.get('test_key')

        if main_val == 'main_value' and knowledge_val == 'knowledge_value' and prompts_val == 'prompts_value':
            print('✅ Database isolation working correctly')

            # Cleanup test data
            main_client.delete('test_key')
            knowledge_client.delete('test_key')
            prompts_client.delete('test_key')
        else:
            print('❌ Database isolation test failed')
    else:
        print('❌ Redis database separation validation failed')

except ImportError as e:
    print(f'⚠️ Redis database manager not available: {e}')
except Exception as e:
    print(f'❌ Redis separation test failed: {e}')
" || echo "⚠️ Redis separation test failed (may be expected if Redis not running)"
}

# Initialize system knowledge and test Redis separation
initialize_system_knowledge
test_redis_separation

python3 -c "
# Test core modules
from src.config import global_config_manager
from src.orchestrator import Orchestrator
from src.llm_interface import LLMInterface
from src.knowledge_base import KnowledgeBase
from src.worker_node import WorkerNode
from src.diagnostics import Diagnostics
print('✅ Core modules imported successfully!')

# Test multi-agent architecture modules
from src.agents import (
    get_chat_agent, get_enhanced_system_commands_agent, get_rag_agent,
    get_agent_orchestrator, AgentType
)
print('✅ Multi-agent architecture modules imported successfully!')

# Test StandardizedAgent base class
from src.agents.standardized_agent import StandardizedAgent
print('✅ StandardizedAgent base class imported successfully!')

# Test Redis database manager
from src.utils.redis_database_manager import redis_db_manager
print('✅ Redis database manager imported successfully!')

# Test codebase analytics
from src.agents.npu_code_search_agent import NPUCodeSearchAgent
print('✅ NPU Code Search Agent imported successfully!')

# Test task-specific model configuration
chat_model = global_config_manager.get_task_specific_model('chat')
orchestrator_model = global_config_manager.get_task_specific_model('orchestrator')
rag_model = global_config_manager.get_task_specific_model('rag')
print(f'✅ Agent model configuration - Chat: {chat_model}')
print(f'✅ Agent model configuration - Orchestrator: {orchestrator_model}')
print(f'✅ Agent model configuration - RAG: {rag_model}')

# Test legacy configuration
print(f'✅ Config loaded - Redis host: {global_config_manager.get_nested(\"memory.redis.host\")}')
print(f'✅ Config loaded - Server port: {global_config_manager.get_nested(\"backend.server_port\")}')

print('✅ Multi-Agent Architecture configuration validation completed successfully!')
"

if [ $? -eq 0 ]; then
    echo "✅ Configuration validation passed!"
    echo "✅ Setup complete. You may now run ./run_agent.sh to launch AutoBot."
echo ""
echo "🚀 New Architecture Features Available:"
echo "   ./run_agent.sh --centralized-logs    # All logs in one place"
echo "   ./run_agent.sh --redis-separation    # Isolated Redis databases"
echo "   ./run_agent.sh --all-containers      # Full Docker setup"
echo "   ./run_agent.sh --help               # Show all options"
echo ""
echo "📊 Analytics Features:"
echo "   Frontend: http://${AUTOBOT_FRONTEND_HOST:-127.0.0.1}:${AUTOBOT_FRONTEND_PORT:-5173} → Analytics tab"
echo "   API: /api/code_search/analytics/ endpoints"
echo "   NPU acceleration: Available when hardware supports"
echo ""
echo "🐳 Docker Architecture:"
echo "   Centralized volumes in: docker/volumes/"
echo "   Logging output: logs/autobot-centralized/"
echo "   Redis databases: 11 isolated databases (0-10)"
else
    echo "❌ Configuration validation failed!"
    echo "Please check the error messages above and fix any issues."
    exit 1
fi

echo "--- DIAGNOSTIC INFORMATION ---"
echo "Running pyenv versions:"
pyenv versions
echo "Running pyenv doctor:"
pyenv doctor
echo ""
echo "Redis configuration:"
ls -la docker/volumes/config/redis-databases.yaml 2>/dev/null || echo "Redis config not found"
echo ""
echo "Docker volumes:"
ls -la docker/volumes/ 2>/dev/null || echo "Docker volumes not found"
echo ""
echo "Centralized logging:"
ls -la logs/ 2>/dev/null || echo "Log directories not found"
echo "--- END DIAGNOSTIC INFORMATION ---"
echo "Please provide this output to the developer for troubleshooting."
