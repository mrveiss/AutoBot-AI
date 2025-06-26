#!/bin/bash

PATH="$(bash --norc -ec 'IFS=:; paths=($PATH);
for i in ${!paths[@]}; do
if [[ ${paths[i]} == "''/home/kali/.pyenv/shims''" ]]; then unset '\''paths[i]'\'';
fi; done;
echo "${paths[*]}"')"
export PATH="/home/kali/.pyenv/shims:${PATH}"
export PYENV_SHELL=bash
source '/home/kali/.pyenv/completions/pyenv.bash'
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
  libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev git
    echo "Installing Python $PYTHON_VERSION..."
    sudo pyenv install "$PYTHON_VERSION" || { echo "❌ Failed to install Python $PYTHON_VERSION."; exit 1; }
    pyenv global "$PYTHON_VERSION"
fi

pyenv global "$PYTHON_VERSION"

# --- 2. Create AutoBot venv ---
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating venv: $VENV_DIR..."
    eval "$(pyenv init -)"
    export PATH="$HOME/.pyenv/shims:$PATH"
    echo "--- PYENV DEBUG INFO ---"
    pyenv --version
    pyenv versions
    echo "--- END PYENV DEBUG INFO ---"
    "$HOME/.pyenv/versions/$PYTHON_VERSION/bin/python" -m venv "$VENV_DIR" || { echo "❌ Failed to create venv."; exit 1; }
else
    echo "✅ Virtual environment $VENV_DIR already exists."
fi

# --- 3. Activate and install main requirements ---
source "$VENV_DIR/bin/activate"
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "⚠️ Warning: $REQUIREMENTS_FILE not found. Skipping pip install."
else
    echo "📦 Installing requirements into $VENV_DIR..."
    pip install --upgrade pip setuptools wheel
    pip install -r "$REQUIREMENTS_FILE" || { echo "❌ Failed to install requirements."; deactivate; exit 1; }
fi

# --- 4. Check and install npm if needed ---
if ! command -v npm &>/dev/null; then
    echo "📦 npm not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y npm || { echo "❌ Failed to install npm."; exit 1; }
fi

# --- 5. Set up frontend ---
echo "🎨 Setting up frontend..."
# Navigate to frontend directory
cd $FRONTEND_DIR

# Clean existing build and old GUI remnants
echo "🧹 Cleaning previous build and old GUI remnants..."
rm -rf dist node_modules
rm -rf ../../old_static/*
rm -rf ../../frontend/templates/*

# Install dependencies
echo "📦 Installing dependencies..."
npm install

# Build frontend
echo "🏗️ Building frontend..."
npm run build

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
DIST_PATH=\"$(pwd)/$FRONTEND_DIR/dist\"
STATIC_PATH="/home/kali/Desktop/AutoBot/$STATIC_DIR"
if [ -d "$DIST_PATH" ] && [ "$(ls -A $DIST_PATH)" ]; then
    # Copy build files to static directory with force overwrite
    echo "📋 Copying build files to static directory..."
    cp -rf "$DIST_PATH/." "$STATIC_PATH/" || { echo "❌ Failed to copy build files to static directory."; exit 1; }
else
    echo "❌ Error: Build output directory $DIST_PATH does not exist or is empty."
    exit 1
fi

echo "✅ Frontend setup complete!"
echo "Access the app at http://localhost:8000"

# --- 6. Copy default config if needed ---
if [ ! -f "$CONFIG_FILE" ]; then
    echo "📄 Copying $CONFIG_TEMPLATE to $CONFIG_FILE..."
    cp "$CONFIG_TEMPLATE" "$CONFIG_FILE" || { echo "❌ Failed to copy config file."; exit 1; }
fi

echo "✅ Setup complete. You may now run ./run_agent.sh to launch AutoBot."

echo "--- DIAGNOSTIC INFORMATION ---"
echo "Running pyenv versions:"
pyenv versions
echo "Running pyenv doctor:"
pyenv doctor
echo "--- END DIAGNOSTIC INFORMATION ---"
echo "Please provide this output to the developer for troubleshooting."
