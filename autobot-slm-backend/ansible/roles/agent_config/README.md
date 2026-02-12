# Agent Configuration Role

Ansible role for configuring AutoBot agents with Python environment, AI/ML frameworks, and automation tools.

## Features

- Python virtual environment with configurable version
- System package dependencies
- OpenVINO for NPU/GPU acceleration
- Ollama for local LLM inference
- Node.js and npm
- Playwright browser automation
- Systemd service management
- Comprehensive configuration templating

## Requirements

- Ubuntu 22.04 or later
- Ansible 2.9+
- Sudo privileges on target hosts

## Role Variables

### Core Settings

```yaml
service_user: autobot          # Service account
service_group: autobot         # Service group
project_root: /opt/autobot     # Installation directory
python_version: "3.10.13"      # Python version to install
agent_role: general            # Agent role (general, ai_stack, browser, etc.)
agent_port: 8090               # Agent API port
```

### Component Toggles

```yaml
install_openvino: true         # Install OpenVINO runtime
install_ollama: true           # Install Ollama
install_nodejs: true           # Install Node.js
install_playwright: true       # Install Playwright
create_systemd_service: true   # Create systemd service
```

### AI/ML Configuration

```yaml
openvino_version: "2023.3"
ollama_models:
  - "llama2"
  - "codellama"
  - "mistral"

playwright_browsers_list:
  - chromium
  - firefox
```

### Environment Variables

```yaml
env_vars:
  TF_USE_LEGACY_KERAS: "1"
  KERAS_BACKEND: "tensorflow"
  TRANSFORMERS_CACHE: "/opt/autobot/models/transformers"
  HF_HOME: "/opt/autobot/models/huggingface"
```

## Dependencies

None. This role is self-contained.

## Example Playbook

```yaml
- hosts: ai_stack
  become: yes
  roles:
    - role: agent_config
      vars:
        agent_role: ai_processing
        agent_port: 8091
        ollama_models:
          - "llama2:70b"
          - "codellama:34b"
```

## Tags

- `system_packages` - System dependencies
- `python` - Python environment setup
- `openvino` - OpenVINO installation
- `ollama` - Ollama setup and models
- `nodejs` - Node.js installation
- `playwright` - Playwright installation
- `config` - Configuration deployment
- `service` - Systemd service
- `verify` - Verification tasks

## Usage Examples

```bash
# Full deployment
ansible-playbook deploy-agent-config.yml

# Deploy to specific host
ansible-playbook deploy-agent-config.yml --limit ai_stack

# Install only Python components
ansible-playbook deploy-agent-config.yml --tags python

# Skip Ollama model downloads
ansible-playbook deploy-agent-config.yml --skip-tags ollama

# Update configuration only
ansible-playbook deploy-agent-config.yml --tags config
```

## Directory Structure

```
agent_config/
├── defaults/
│   └── main.yml              # Default variables
├── handlers/
│   └── main.yml              # Service restart handlers
├── tasks/
│   ├── main.yml              # Main task orchestration
│   ├── system_packages.yml   # System dependencies
│   ├── python_env.yml        # Python environment
│   ├── python_deps.yml       # Python packages
│   ├── openvino.yml          # OpenVINO setup
│   ├── ollama.yml            # Ollama installation
│   ├── nodejs.yml            # Node.js setup
│   ├── playwright.yml        # Playwright installation
│   ├── config.yml            # Configuration
│   ├── service.yml           # Systemd service
│   └── verify.yml            # Verification
└── templates/
    ├── agent_config.yml.j2   # Agent configuration
    ├── agent.env.j2          # Environment variables
    ├── logging.yml.j2        # Logging config
    └── autobot-agent.service.j2  # Systemd unit
```

## Verification

After deployment, verify the installation:

```bash
# Check service status
systemctl status autobot-agent

# View logs
journalctl -u autobot-agent -f

# Test Python environment
sudo -u autobot /opt/autobot/venv/bin/python --version

# Verify OpenVINO
sudo -u autobot /opt/autobot/venv/bin/python -c 'import openvino; print(openvino.__version__)'

# Check Ollama models
ollama list

# Test agent endpoint
curl http://localhost:8090/health
```

## Troubleshooting

### Python version mismatch

If Python installation fails, ensure pyenv is properly configured:
```bash
sudo -u autobot pyenv versions
sudo -u autobot pyenv install 3.10.13
```

### OpenVINO GPU access denied

Add the service user to the render group:
```bash
sudo usermod -a -G render autobot
```

### Ollama models not downloading

Check disk space and network connectivity:
```bash
df -h /opt/autobot
curl -I https://ollama.ai/
```

### Service won't start

Check logs for details:
```bash
journalctl -u autobot-agent -n 50 --no-pager
```

## License

Copyright (c) 2025 mrveiss. All rights reserved.
