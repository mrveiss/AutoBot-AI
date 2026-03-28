# Installation Guide

Complete installation instructions for AutoBot. Two deployment methods: bare-metal (systemd) or Docker.

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Debian/Ubuntu or WSL2 | Ubuntu 22.04 LTS |
| RAM | 16 GB | 32 GB+ |
| CPU | 8 cores | 16+ cores |
| Storage | 50 GB | 200 GB+ (model + knowledge base storage) |
| GPU | — | NVIDIA (CUDA) or Intel NPU for accelerated inference |
| Python | 3.12 | 3.12 (installed automatically by installer) |
| Node.js | 18 | 20 (installed automatically by installer) |

### Required Permissions (Bare-Metal Install)

- **Root access (`sudo`)** — the installer must run as root
- **systemd** — required for service management (PostgreSQL, nginx, SLM backend)
- **Internet access** — outbound HTTPS to github.com and package repositories (deb.nodesource.com, PPA)

> **WSL2 users:** systemd must be enabled before running the installer. Add the following to `/etc/wsl.conf` and restart WSL:
> ```ini
> [boot]
> systemd=true
> ```

### What the Installer Creates

| Resource | Purpose |
|----------|---------|
| `autobot` system user | Runs all services (with passwordless sudo) |
| `/opt/autobot/` | Application base directory |
| `/var/log/autobot/` | Installation and service logs |
| `/etc/autobot/` | Secrets and configuration |
| SSH key pair | Fleet management (`/home/autobot/.ssh/autobot_key`) |
| Self-signed TLS cert | HTTPS for nginx |

## Installation Methods

### Method 1: Bare-Metal Install (Recommended)

Installs all services directly on the host using systemd:

```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
sudo ./install.sh              # Interactive install
sudo ./install.sh --unattended # Unattended (CI/automation)
```

**Options:**

| Flag | Description |
|------|-------------|
| `--unattended` | No prompts, use all defaults |
| `--reinstall` | Force reinstall over existing installation |
| `--branch=BRANCH` | Git branch to install (default: `Dev_new_gui`) |
| `--admin-pass=PASS` | SLM admin password (auto-generated if not set) |

**The installer will:**
1. Verify root access, systemd, disk space (5 GB+), memory (2 GB+), and internet
2. Install system packages (Python 3.12, Node.js 20, nginx, Ansible, build tools, libpq)
3. Create the `autobot` system user with passwordless sudo
4. Clone the repository and distribute code to service directories
5. Run Ansible deployment for the SLM stack (PostgreSQL, backend, nginx)
6. Verify all services are running and healthy
7. Display admin credentials and save them to `/root/autobot-credentials.txt`

Takes 10-20 minutes depending on internet speed. Logs: `/var/log/autobot/`.

**Post-install access:**

| Service | URL |
|---------|-----|
| SLM Admin | `https://<server-ip>/` |
| Service Logs | `journalctl -u autobot-slm-backend -f` |

### Method 2: Docker (Single Node)

Run the entire stack on one machine with Docker Compose. No system users or packages installed on the host — Docker handles all isolation.

**Requirements:** Docker Engine 24+ and Docker Compose v2.

```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI

# Core services (backend, SLM, frontend, Redis, PostgreSQL, ChromaDB)
docker compose --env-file docker/.env.docker up -d --build

# Include local Ollama LLM
docker compose --env-file docker/.env.docker --profile ollama up -d --build

# Include Prometheus + Grafana monitoring
docker compose --env-file docker/.env.docker --profile monitoring up -d --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost |
| SLM Admin | http://localhost/slm |
| Backend API | http://localhost/api |
| RedisInsight | http://localhost:8001 |
| Ollama | http://localhost:11434 (if `--profile ollama`) |
| Grafana | http://localhost:3000 (if `--profile monitoring`) |

**Dev mode** with hot reload:
```bash
cp docker-compose.override.example.yml docker-compose.override.yml
docker compose up -d
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
# Install Python 3.12 via deadsnakes PPA (Issue #1898)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
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
