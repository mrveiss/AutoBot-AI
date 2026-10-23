# Installation Guide

Complete installation instructions for AutoBot. Two deployment methods: bare-metal (systemd) or Docker.

## Prerequisites

### System Requirements

Requirements (OS, systemd, RAM, disk) live in one place: [INSTALL.md - Requirements](../../INSTALL.md#requirements).

The installer sets up the runtime itself: Python 3.14 and Node.js 20.

A GPU is optional and only speeds up local model inference; see [GPU Acceleration](#gpu-acceleration-optional).

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
| `--branch=BRANCH` | Git branch to install (default: `main`) |
| `--admin-pass-file=PATH` | Read the SLM admin password from the first line of PATH (auto-generated if not set). The file must be non-empty and mode `600` or tighter (`chmod 600 PATH`); the installer refuses a group- or world-readable file or an empty first line |

**The installer will:**
1. Verify root access, systemd, disk space and memory (minimums in INSTALL.md), and internet
2. Install system packages (Python 3.14, Node.js 20, nginx, Ansible, build tools, libpq)
3. Create the `autobot` system user with passwordless sudo
4. Clone the repository and distribute code to service directories
5. Run Ansible deployment for the SLM stack (PostgreSQL, backend, nginx)
6. Verify all services are running and healthy
7. Display admin credentials and save them to `/root/autobot-credentials.txt`

Takes 10-20 minutes depending on internet speed. Logs: `/var/log/autobot/`.

**Post-install access:**

| Service | URL |
|---------|-----|
| SLM Admin | `https://<server>/slm/` |
| Service Logs | `journalctl -u autobot-slm-backend -f` |

### Method 2: Docker (Single Node)

Run the stack on one machine with Docker Compose. No system users or packages are installed on the host.

The full, current procedure (per-host secrets, the SLM-only start, TLS, profiles, the first admin login) is in [INSTALL.md - Docker Deployment](../../INSTALL.md#docker-deployment). The short form:

```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
bash docker/generate-secrets.sh   # once per host; writes docker/.env.secrets
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets up -d --build
```

| Service | URL |
|---------|-----|
| Frontend (user UI) | http://localhost |
| SLM Admin | http://localhost/slm/ |
| Backend API (via the frontend proxy) | http://localhost/api |
| RedisInsight | http://localhost:8001 (host-local only) |
| Ollama | http://localhost:11434 (only with `--profile ollama`) |
| Grafana | http://localhost:3000 (only with `--profile monitoring`) |

The backend publishes no host port of its own: reach it through `http://localhost/api`. Host port 8001 is RedisInsight, not the backend.

Log in at http://localhost with user `admin`; the password is `AUTOBOT_ADMIN_PASSWORD` in `docker/.env.secrets` (see INSTALL.md).

## LLM Provider Setup

Providers (local Ollama, OpenAI, Anthropic and others) are configured in the running system, not by hand-editing YAML:

- **SLM Admin > Settings > LLM Configuration** (tabs: Providers, Server Settings, Models) sets the active provider, endpoint, model and API key.
- **SLM Admin > Settings > LLM Fallbacks** sets the fallback order between providers.
- To run models on this host with Docker, start the `ollama` profile and pull the models named in `docker/.env.docker`; see [INSTALL.md - Profiles](../../INSTALL.md#profiles).
- How AutoBot picks a model per request: [Model Selection Guide](../user/guides/model-selection.md). Fallback behaviour: [LLM Model Fallback](../developer/llm-fallback.md).

Cloud providers need no local model.

## GPU Acceleration (Optional)

GPU drivers and toolkits (NVIDIA CUDA, AMD ROCm, Intel OpenVINO) are host software. Install them from the vendor's current instructions for your distribution and release; this guide does not pin a version.

Check that the driver sees the GPU:

```bash
nvidia-smi   # NVIDIA
rocm-smi     # AMD
```

For GPU problems see [Troubleshooting](04-troubleshooting.md).

## Verification

### Bare-Metal Install

The installer verifies services itself. To confirm afterwards:

```bash
systemctl status autobot-slm-backend --no-pager
systemctl status postgresql --no-pager
systemctl status nginx --no-pager

# SLM backend health, through nginx
curl -sk https://127.0.0.1/slm/api/health | jq

# Recent logs
journalctl -u autobot-slm-backend -n 20 --no-pager
```

Open `https://<server>/slm/` and accept the self-signed certificate warning. The admin password is printed at the end of the install and saved to `/root/autobot-credentials.txt`. The first login starts the Setup Wizard.

### Docker Install

```bash
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets ps
curl -s http://localhost/api/health | jq   # backend, via the frontend proxy
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets logs -f --tail=50
```

If you started only the SLM GUI (`--profile slm`), use `curl -s http://localhost/slm/api/health` instead.

## Troubleshooting Installation

### Common Issues

**Issue: Permission denied running install.sh**
```bash
# The installer requires root
chmod +x install.sh
sudo ./install.sh
```

**Issue: systemd not running (WSL2)**
```bash
# Enable systemd in WSL2
sudo tee /etc/wsl.conf <<'EOF'
[boot]
systemd=true
EOF
# Then restart WSL from PowerShell: wsl --shutdown
```

**Issue: Python 3.14 not found**
```bash
# Install Python 3.14 via deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.14 python3.14-venv python3.14-dev
```

**Issue: Node.js/npm not found**
```bash
# Install Node.js 20.x LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**Issue: Ansible deployment failed**
```bash
# Check the install log for details
tail -100 /var/log/autobot/install-*.log

# Then see INSTALL.md, "Installer fails at Ansible Deployment"
```

**Issue: GPU not detected**
```bash
nvidia-smi  # NVIDIA
rocm-smi    # AMD
```

### Getting Help

If installation fails:

1. **Check logs**: `tail -100 /var/log/autobot/install-*.log`
2. **Verify prerequisites**: Ensure all system requirements are met
3. **Try Docker**: Use Method 2 as an alternative to bare-metal
4. **GitHub Issues**: Report installation problems with system details at https://github.com/mrveiss/AutoBot-AI/issues

### Next Steps

After successful installation:
1. **[Quick Start Guide](02-quickstart.md)** - Your first conversation
2. **[Configuration Guide](03-configuration.md)** - Where settings live
3. **[User Guides](../user/README.md)** - Complete user documentation
