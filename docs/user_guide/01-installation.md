# Installation Guide

## Prerequisites

Before installing AutoBot, ensure you have the following prerequisites:

### System Requirements
- **Operating System**: Linux (Kali preferred) or Windows with WSL2
- **Python**: 3.10.x (managed via pyenv)
- **Hardware**: Minimum 4GB RAM, 8GB+ recommended for local LLM inference
- **GPU (Optional)**: NVIDIA GPU with CUDA drivers or AMD GPU with ROCm for accelerated inference

### Required Software
1. **Git** - For repository cloning
2. **pyenv** - Python version management
3. **Redis** (optional) - For enhanced memory and task queue functionality
4. **Hardware Drivers** (if using GPU acceleration):
   - NVIDIA: Latest CUDA drivers
   - AMD: ROCm drivers

## Installation Methods

### Method 1: Single-Command Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI

# Run the setup script
./setup_agent.sh
```

This script will:
- Detect your environment (WSL2/Linux)
- Install required system packages
- Set up Python virtual environment
- Install all dependencies
- Create necessary directories
- Set up configuration files

### Method 2: Manual Installation

If the automated setup fails, follow these manual steps:

#### 1. Environment Setup
```bash
# Install pyenv if not present
curl https://pyenv.run | bash

# Install Python 3.10
pyenv install 3.10.13
pyenv global 3.10.13
```

#### 2. Project Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/WSL
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

#### 3. Configuration
```bash
# Copy configuration template
cp config/config.yaml.template config/config.yaml

# Edit configuration as needed
nano config/config.yaml
```

## Post-Installation

### Verification
Run the verification script to ensure everything is installed correctly:
```bash
python -c "import src.config; print('Installation successful!')"
```

### First Run
Launch AutoBot with:
```bash
./run_agent.sh
```

The web interface will be available at `http://localhost:8001`

## Troubleshooting

### Common Issues

**Issue**: `pyenv command not found`
**Solution**: Restart your shell or run `source ~/.bashrc`

**Issue**: GPU not detected
**Solution**: Verify driver installation and CUDA/ROCm setup

**Issue**: Redis connection failed
**Solution**: Install Redis server or disable Redis in configuration

### Getting Help
- Check the logs in `logs/` directory
- Review `docs/troubleshooting.md`
- Submit issues on GitHub
