#!/bin/bash

PATH="$(bash --norc -ec 'IFS=:; paths=($PATH);
for i in ${!paths[@]}; do
if [[ ${paths[i]} == "''${HOME}/.pyenv/shims''" ]]; then unset '\''paths[i]'\'';
fi; done;
echo "${paths[*]}"')"
export PATH="${HOME}/.pyenv/shims:${PATH}"
export PYENV_SHELL=bash
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
# Get the directory where this script is located (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "🔍 Detected project root: $SCRIPT_DIR"

# Change to project root directory
cd "$SCRIPT_DIR"

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
FRONTEND_DIR="autobot-vue"

echo "🔧 Starting AutoBot setup..."

# Ensure required folders exist
mkdir -p "$CONFIG_DIR" "$LOGS_DIR" "$DOCS_DIR" "$STATIC_DIR"

# --- 1. Verify Python 3.10 via pyenv ---
echo "🔍 Checking for Python $PYTHON_VERSION with pyenv..."

if ! command -v pyenv &>/dev/null; then
    echo "❌ pyenv not found. Please install it manually:"
    echo "
# Install pyenv + build tools
sudo apt update && sudo apt install -y make build-essential libssl-dev zlib1g-dev \\
  libbz2-dev libreadline-dev libsqlite3-dev curl llvm libncursesw5-dev xz-utils tk-dev \\
  libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev git

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
  libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev git redis-server pciutils || { echo "❌ Failed to install build dependencies and pciutils."; exit 1; }
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

# Start Docker daemon (if not running)
echo "🔄 Starting Docker daemon in WSL2..."
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

# --- 3. Deploy/Start Redis Stack Docker Container (using local Docker) ---
echo "🔍 Checking for existing 'redis-stack' Docker container (local to WSL2)..."
if docker ps -a --format '{{.Names}}' | grep -q '^redis-stack$'; then
    echo "✅ 'redis-stack' container found."
    if docker inspect -f '{{.State.Running}}' redis-stack | grep -q 'true'; then
        echo "✅ 'redis-stack' container is already running."
    else
        echo "🔄 'redis-stack' container found but not running. Starting it..."
        docker start redis-stack || { echo "❌ Failed to start 'redis-stack' container."; exit 1; }
        echo "✅ 'redis-stack' container started."
    fi
else
    echo "📦 'redis-stack' container not found. Deploying a new one..."
    docker run -d --name redis-stack -p 6379:6379 redis/redis-stack-server:latest || { echo "❌ Failed to deploy 'redis-stack' container."; exit 1; }
    echo "✅ 'redis-stack' container deployed and started."
fi

# Assume Redis Stack is ready if Docker command succeeded
echo "Assuming Redis Stack is ready and accessible via localhost:6379 from within WSL2."
echo "Please ensure the 'redis-stack' Docker container is running and healthy."

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

# --- 3. Activate and install main requirements ---
echo "--- Python Dependencies Installation ---"
source "$VENV_PATH/bin/activate"
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "⚠️ Warning: $REQUIREMENTS_FILE not found. Skipping pip install."
else
    echo "📦 Installing requirements in groups to resolve dependency conflicts..."

    # Group 1: Core dependencies
    echo "⬇️ Installing Group 1: Core dependencies..."
    cat > requirements_group_1.txt << EOF
fastapi==0.115.9
uvicorn>=0.30.0
requests==2.31.0
pyyaml==6.0.1
redis>=5.0,<6.0
pyautogui==0.9.54
mouseinfo==0.1.3
pillow==9.4.0
numpy==1.26.4
markdownify==0.11.6
python-docx
psutil
EOF
    pip install -r requirements_group_1.txt || { echo "❌ Failed to install Group 1 requirements."; deactivate; exit 1; }
    echo "✅ Group 1 dependencies installed."

    # Group 2: LangChain and LangChain Community
    echo "⬇️ Installing Group 2: LangChain and LangChain Community..."
    cat > requirements_group_2.txt << EOF
langchain
langchain-community
EOF
    pip install -r requirements_group_2.txt || { echo "❌ Failed to install Group 2 requirements."; deactivate; exit 1; }
    echo "✅ Group 2 dependencies installed."

    # Group 3: LlamaIndex and its sub-packages
    echo "⬇️ Installing Group 3: LlamaIndex and related packages..."
    cat > requirements_group_3.txt << EOF
llama-index
llama-index-llms-ollama
llama-index-embeddings-ollama
llama-index-vector-stores-redis
transformers
EOF
    pip install -r requirements_group_3.txt || { echo "❌ Failed to install Group 3 requirements."; deactivate; exit 1; }
    echo "✅ Group 3 dependencies installed."

    # Clean up temporary files
    rm requirements_group_1.txt requirements_group_2.txt requirements_group_3.txt
    echo "✅ All Python dependencies installed."
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

# --- 4. Check and install Node.js and npm via nvm ---
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
echo "Access the Vue app at http://localhost:5173 (development)"
echo "The built files are served from the backend at http://localhost:8001"

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

python3 -c "
from src.config import global_config_manager
from src.orchestrator import Orchestrator  
from src.llm_interface import LLMInterface
from src.knowledge_base import KnowledgeBase
from src.worker_node import WorkerNode
from src.diagnostics import Diagnostics
print('✅ All modules imported successfully!')
print(f'✅ Config loaded - LLM model: {global_config_manager.get_nested(\"llm_config.ollama.model\")}')
print(f'✅ Config loaded - Redis host: {global_config_manager.get_nested(\"memory.redis.host\")}')
print(f'✅ Config loaded - Server port: {global_config_manager.get_nested(\"backend.server_port\")}')
print('✅ Configuration validation completed successfully!')
"

if [ $? -eq 0 ]; then
    echo "✅ Configuration validation passed!"
    echo "✅ Setup complete. You may now run ./run_agent.sh to launch AutoBot."
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
echo "--- END DIAGNOSTIC INFORMATION ---"
echo "Please provide this output to the developer for troubleshooting."
