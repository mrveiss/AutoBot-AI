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
  libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev git redis-server
    echo "Installing Python $PYTHON_VERSION..."
    sudo pyenv install "$PYTHON_VERSION" || { echo "❌ Failed to install Python $PYTHON_VERSION."; exit 1; }
    pyenv global "$PYTHON_VERSION"
fi

# Ensure Redis server is installed and started
echo "🔍 Checking for Redis server installation..."
if ! command -v redis-server &>/dev/null; then
    echo "❌ Redis server not installed. Installing Redis server..."
    sudo apt update && sudo apt install -y redis-server || { echo "❌ Failed to install Redis server."; exit 1; }
fi

echo "🔄 Starting Redis server if not already running..."
sudo systemctl start redis 2>/dev/null || redis-server --daemonize yes 2>/dev/null || { echo "⚠️ Failed to start Redis server. Continuing without Redis."; }

pyenv global "$PYTHON_VERSION"

# --- 2. Create AutoBot venv ---
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating venv: $VENV_DIR..."
    eval "$(pyenv init -)"
    export PATH="${HOME}/.pyenv/shims:$PATH"
    echo "--- PYENV DEBUG INFO ---"
    pyenv --version
    pyenv versions
    echo "--- END PYENV DEBUG INFO ---"
    "${HOME}/.pyenv/versions/$PYTHON_VERSION/bin/python" -m venv "$VENV_DIR" || { echo "❌ Failed to create venv."; exit 1; }
else
    echo "✅ Virtual environment $VENV_DIR already exists."
fi

# --- 3. Activate and install main requirements ---
echo "--- Python Dependencies Installation ---"
source "$VENV_DIR/bin/activate"
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
numpy==1.24.2
markdownify==0.11.6
EOF
    pip install -r requirements_group_1.txt || { echo "❌ Failed to install Group 1 requirements."; deactivate; exit 1; }
    echo "✅ Group 1 dependencies installed."

    # Group 2: LangChain
    echo "⬇️ Installing Group 2: LangChain..."
    cat > requirements_group_2.txt << EOF
langchain
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
if lspci | grep -i "neural\|npu\|ai" > /dev/null 2>&1; then
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
cd ../..
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
echo "Access the app at http://localhost:8000"

# --- 6. Copy default config if needed ---
if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "$CONFIG_TEMPLATE" ]; then
        echo "📄 Copying $CONFIG_TEMPLATE to $CONFIG_FILE..."
        cp "$CONFIG_TEMPLATE" "$CONFIG_FILE" || { echo "❌ Failed to copy config file."; exit 1; }
    else
        echo "⚠️ Warning: Config template $CONFIG_TEMPLATE not found. Creating a basic config file..."
        cat > "$CONFIG_FILE" << 'EOF'
# Basic AutoBot Configuration
server:
  host: "0.0.0.0"
  port: 8000

logging:
  level: "INFO"
  file: "logs/autobot.log"

models:
  default: "tinyllama"
EOF
        echo "✅ Basic config file created at $CONFIG_FILE."
    fi
fi

echo "✅ Setup complete. You may now run ./run_agent.sh to launch AutoBot."

echo "--- DIAGNOSTIC INFORMATION ---"
echo "Running pyenv versions:"
pyenv versions
echo "Running pyenv doctor:"
pyenv doctor
echo "--- END DIAGNOSTIC INFORMATION ---"
echo "Please provide this output to the developer for troubleshooting."
