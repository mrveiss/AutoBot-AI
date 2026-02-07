# Installation Guide

Complete step-by-step installation instructions for AutoBot on Linux, Windows, and macOS.

## Prerequisites

### System Requirements
- **Operating System**: Linux (Ubuntu/Debian/Kali), Windows 10+ with WSL2, or macOS 12+
- **Python**: 3.10+ (3.11+ recommended for Intel NPU support)
- **Node.js**: 20.x LTS (for frontend development)
- **RAM**: 8GB minimum, 16GB+ recommended for local LLM inference
- **Storage**: 10GB free space minimum

### Hardware Requirements (Optional)
- **GPU**: NVIDIA GPU with 8GB+ VRAM for local LLM acceleration
  - NVIDIA drivers 470+ and CUDA 11.8+ toolkit
- **Intel NPU**: Intel Meteor Lake or newer for NPU acceleration
  - OpenVINO toolkit 2024.0+
- **AMD GPU**: AMD GPU with ROCm 5.4+ support

### Required Software
- **Git** - Version control (for cloning repository)
- **curl** - Command line tool for downloads
- **Python Build Tools** - For compiling dependencies

## Installation Methods

### Method 1: Single-Command Setup (Recommended)

This automated method handles all dependencies and configuration:

```bash
# Clone the repository
git clone https://github.com/your-repo/AutoBot-AI.git
cd AutoBot-AI

# Run automated setup (creates venv, installs dependencies, configures)
chmod +x setup_agent.sh
./setup_agent.sh
```

**The setup script will:**
- Detect your environment (Linux/WSL2/macOS)
- Install system packages (build tools, Redis, Tesseract OCR)
- Set up Python 3.10+ via pyenv if needed
- Create isolated virtual environment in `bin/`
- Install all Python dependencies from `requirements.txt`
- Install Node.js dependencies for frontend
- Create necessary directories (`data/`, `logs/`, `config/`)
- Copy configuration template to `config/config.yaml`
- Set up Git hooks and environment

### Method 2: Manual Installation

If automated setup fails or you prefer manual control:

#### Step 1: System Dependencies

**Ubuntu/Debian:**
```bash
# Update package list
sudo apt update

# Install system dependencies
sudo apt install -y build-essential curl git python3-dev python3-venv \
                    nodejs npm redis-server tesseract-ocr libffi-dev \
                    libjpeg-dev zlib1g-dev libssl-dev

# Start Redis service
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

**CentOS/RHEL/Fedora:**
```bash
# Install system dependencies
sudo dnf install -y gcc gcc-c++ make curl git python3-devel python3-pip \
                    nodejs npm redis tesseract openssl-devel libffi-devel \
                    libjpeg-turbo-devel zlib-devel

# Start Redis service
sudo systemctl enable redis
sudo systemctl start redis
```

**macOS:**
```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install python@3.11 node redis tesseract git curl
brew services start redis
```

**Windows (WSL2):**
```bash
# Update WSL2 Ubuntu
sudo apt update && sudo apt upgrade -y

# Install dependencies (same as Ubuntu above)
sudo apt install -y build-essential curl git python3-dev python3-venv \
                    nodejs npm redis-server tesseract-ocr libffi-dev \
                    libjpeg-dev zlib1g-dev libssl-dev
```

#### Step 2: Python Environment Setup

```bash
# Navigate to project directory
cd AutoBot-AI

# Create virtual environment using system Python 3.10+
python3 -m venv bin
source bin/activate  # Linux/macOS
# or: bin\Scripts\activate  # Windows

# Upgrade pip and install core tools
pip install --upgrade pip setuptools wheel

# Install Python dependencies
pip install -r requirements.txt
```

#### Step 3: Frontend Setup

```bash
# Navigate to frontend directory
cd autobot-vue

# Install Node.js dependencies
npm install

# Build frontend for production
npm run build

# Return to project root
cd ..
```

#### Step 4: Configuration Setup

```bash
# Create necessary directories
mkdir -p data/chats data/chromadb data/messages logs config

# Copy configuration template
cp config/config.yaml.template config/config.yaml

# Set proper permissions
chmod 755 data logs config
chmod 644 config/config.yaml
```

## LLM Provider Setup

Choose one or more LLM providers for AutoBot:

### Option A: Ollama (Local, Recommended)

**Installation:**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve &

# Pull recommended models
ollama pull tinyllama:latest    # Fast, low resource
ollama pull phi:2.7b           # Better quality
ollama pull llama2:7b          # High quality (requires 8GB+ RAM)
```

**Configuration:** Ollama runs on `http://localhost:11434` by default - no additional config needed.

### Option B: OpenAI API

**Setup:**
```bash
# Set API key as environment variable
export OPENAI_API_KEY="your-openai-api-key-here"  # pragma: allowlist secret

# Or add to your shell profile
echo 'export OPENAI_API_KEY="your-api-key"' >> ~/.bashrc  # pragma: allowlist secret
source ~/.bashrc
```

**Configuration:** Edit `config/config.yaml`:
```yaml
llm_config:
  default_llm: "openai_gpt35"
  openai:
    api_key: ""  # Uses environment variable
    models:
      - "gpt-3.5-turbo"
      - "gpt-4"
```

### Option C: Anthropic Claude

**Setup:**
```bash
# Set API key
export ANTHROPIC_API_KEY="your-anthropic-api-key-here"  # pragma: allowlist secret
echo 'export ANTHROPIC_API_KEY="your-api-key"' >> ~/.bashrc  # pragma: allowlist secret
```

**Configuration:** Edit `config/config.yaml`:
```yaml
llm_config:
  default_llm: "anthropic_claude"
  anthropic:
    api_key: ""  # Uses environment variable
    models:
      - "claude-3-sonnet-20240229"
      - "claude-3-haiku-20240307"
```

## GPU Acceleration Setup (Optional)

### NVIDIA GPU Setup

**Install CUDA:**
```bash
# Download and install CUDA 11.8 (or latest compatible)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/cuda-ubuntu2004.pin
sudo mv cuda-ubuntu2004.pin /etc/apt/preferences.d/cuda-repository-pin-600
wget https://developer.download.nvidia.com/compute/cuda/11.8.0/local_installers/cuda-repo-ubuntu2004-11-8-local_11.8.0-520.61.05-1_amd64.deb
sudo dpkg -i cuda-repo-ubuntu2004-11-8-local_11.8.0-520.61.05-1_amd64.deb
sudo cp /var/cuda-repo-ubuntu2004-11-8-local/cuda-*-keyring.gpg /usr/share/keyrings/
sudo apt-get update
sudo apt-get -y install cuda
```

**Install PyTorch with CUDA:**
```bash
# Activate virtual environment
source bin/activate

# Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### AMD GPU Setup (ROCm)

**Install ROCm:**
```bash
# Add ROCm repository
wget -q -O - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
echo "deb [arch=amd64] https://repo.radeon.com/rocm/apt/debian/ ubuntu main" | sudo tee /etc/apt/sources.list.d/rocm.list
sudo apt update
sudo apt install rocm-dkms rocm-dev rocm-libs
```

**Install PyTorch with ROCm:**
```bash
source bin/activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.4.2
```

### Intel NPU Setup (OpenVINO)

**Install OpenVINO:**
```bash
# Download and install OpenVINO toolkit
wget https://storage.openvinotoolkit.org/repositories/openvino/packages/2024.0/linux/l_openvino_toolkit_ubuntu20_2024.0.0.14509.34caeefd078_x86_64.tgz
tar -xzf l_openvino_toolkit_ubuntu20_2024.0.0.14509.34caeefd078_x86_64.tgz
sudo mv l_openvino_toolkit_ubuntu20_2024.0.0.14509.34caeefd078 /opt/intel/openvino_2024
echo 'source /opt/intel/openvino_2024/setupvars.sh' >> ~/.bashrc
```

## Verification and First Run

### Verify Installation

**Check dependencies:**
```bash
# Verify Python environment
source bin/activate
python --version  # Should be 3.10+
pip list | grep -E "(fastapi|ollama|redis|chromadb)"

# Verify Node.js build
cd autobot-vue && npm run build && cd ..

# Verify Redis connection
redis-cli ping  # Should return "PONG"

# Test GPU (if installed)
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

**Configuration validation:**
```bash
# Validate configuration file
python -c "from src.config import validate_config; print(validate_config())"
```

### First Launch

```bash
# Launch AutoBot (all services)
./run_agent.sh
```

**Expected output:**
```
Starting AutoBot services...
✓ Backend server starting on http://localhost:8001
✓ Frontend development server on http://localhost:5173
✓ Redis connection established
✓ LLM provider connected
✓ Knowledge base initialized
✓ All systems operational
```

### Access Interface

Open your web browser and navigate to:
- **Main Interface**: http://localhost:5173
- **API Documentation**: http://localhost:8001/docs
- **Health Check**: http://localhost:8001/api/health

## Post-Installation Configuration

### Basic Configuration

Edit `config/config.yaml` for your environment:

```yaml
# Basic settings that may need adjustment
backend:
  server_port: 8001  # Change if port conflict

llm_config:
  default_llm: "ollama_tinyllama"  # Choose your preferred model

memory:
  redis:
    enabled: true  # Set false if Redis unavailable
  chromadb:
    enabled: true
    path: "data/chromadb"

logging:
  log_level: "info"  # debug, info, warning, error
```

### Security Setup

```bash
# Set secure file permissions
chmod 600 config/config.yaml  # Restrict config file access
chmod 700 data/               # Restrict data directory

# Generate secure secret keys (optional)
python -c "import secrets; print(f'SECRET_KEY={secrets.token_hex(32)}')" >> .env
```

## Troubleshooting Installation

### Common Issues

**Issue: Permission denied during setup**
```bash
# Fix script permissions
chmod +x setup_agent.sh run_agent.sh

# Run with sudo if needed
sudo ./setup_agent.sh
```

**Issue: Python version not found**
```bash
# Install pyenv for Python version management
curl https://pyenv.run | bash
exec $SHELL  # Restart shell
pyenv install 3.10.13
pyenv global 3.10.13
```

**Issue: Redis connection failed**
```bash
# Install and start Redis
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Test connection
redis-cli ping
```

**Issue: Node.js/npm not found**
```bash
# Install Node.js 20.x LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**Issue: GPU not detected**
```bash
# Check GPU status
nvidia-smi  # For NVIDIA
rocm-smi    # For AMD

# Verify drivers
lsmod | grep nvidia  # Should show nvidia modules
```

### Getting Help

If installation fails:

1. **Check logs**: `tail -f logs/setup.log`
2. **Verify prerequisites**: Ensure all system requirements are met
3. **Manual installation**: Follow Method 2 step-by-step
4. **GitHub Issues**: Report installation problems with system details
5. **Community Support**: Check discussions for similar issues

### Next Steps

After successful installation:
1. **[Quick Start Guide](02-quickstart.md)** - Learn basic usage
2. **[Configuration Guide](../configuration.md)** - Detailed configuration options
3. **[Troubleshooting Guide](04-troubleshooting.md)** - Common runtime issues

---

**Installation complete!** AutoBot is now ready for use. 🚀
