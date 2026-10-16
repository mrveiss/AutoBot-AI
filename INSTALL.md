# AutoBot Installation Guide

## Overview

AutoBot is a self-hosted AI platform you own: a small core, the **Service Lifecycle
Manager (SLM)** management layer, and modules on top. Installing AutoBot means standing
up that stack on your own hardware. (Throughout this guide, **SLM** always means *Service
Lifecycle Manager* — AutoBot's management layer — never "small language model." For the
full picture, see [The AutoBot Platform Model](docs/architecture/PLATFORM_MODEL.md).)

Installation uses a two-phase deployment model:

1. **`install.sh`** — a shell script that deploys the **Service Lifecycle Manager (SLM)**
   and all dependencies onto a blank Debian/Ubuntu host. The SLM is the management layer
   that then deploys, operates, and scales the rest of the infrastructure.
2. **Setup Wizard** — a guided web UI that walks you through adding fleet nodes, testing
   connections, enrolling agents, assigning roles, and provisioning.

After both phases complete you have a fully operational AutoBot platform and fleet —
ready to run the core and install modules.

---

## Requirements

| Requirement | Minimum |
|-------------|---------|
| OS | Debian 11+ / Ubuntu 22.04+ |
| Init system | **systemd running as PID 1** — the installer manages every service as a systemd unit |
| RAM | 1.5 GB (the installer refuses to run below this; SLM control plane only) |
| Disk | 5 GB free (the installer refuses to run below this); 20 GB recommended |
| Access | Root (or sudo) |
| Network | Internet access for package downloads |

**Supported hosts:** a Debian/Ubuntu VM or bare-metal machine booted with systemd, or
WSL2 with systemd enabled (`[boot] systemd=true` in `/etc/wsl.conf`). **Not supported by
`install.sh`:** containers and other hosts where systemd is not PID 1 — use the
[Docker deployment](#docker-deployment) there instead.

---

## Quick Start

```bash
# One-liner (downloads and runs the installer):
curl -fsSL https://raw.githubusercontent.com/mrveiss/AutoBot-AI/main/install.sh | sudo bash

# Or clone first, then run:
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
sudo ./install.sh
```

The installer takes 10-20 minutes depending on network speed and hardware.

---

## Installer Phases

The install script runs seven phases automatically:

| Phase | Description |
|-------|-------------|
| 1/7 Pre-flight | Checks root, systemd, OS, disk, memory, internet, existing installs |
| 2/7 System Setup | Installs system packages, creates `autobot` user, sets up directories |
| 3/7 Code Deployment | Clones the repository to `/opt/autobot/code_source`, creates a Python venv |
| 4/7 Ansible Deployment | Runs `deploy-slm-manager.yml` locally (PostgreSQL, SLM backend, nginx, monitoring) |
| 5/7 Service Verification | Waits for the SLM backend to become healthy (up to 2 minutes) |
| 6/7 Register Local Node | Registers this host with the SLM as its first node and assigns the code source |
| 7/7 Finalize | Writes the install marker, prints access URL and credentials |

**Which code is installed:** phase 3 clones `main` from GitHub (or the branch given with
`--branch=`), even when you run `./install.sh` from a local clone — the installer warns when
that happens. Only pushed branches can be installed. The installed commit is printed and
logged.

### Installer Options

| Option | Effect |
|--------|--------|
| *(none)* | Standard interactive install |
| `--unattended` | Run without prompts, use all defaults (CI/automation) |
| `--reinstall` | Force a reinstall over an existing installation |
| `--uninstall` | Completely remove AutoBot and its dependencies (asks for confirmation) |
| `--yes`, `-y` | Skip confirmation prompts (use with `--uninstall`) |
| `--validate` | Verify installation integrity (required service directories present) |
| `--branch=BRANCH` | Git branch to install (default: `main`) |
| `--admin-pass=PASS` | SLM admin password (auto-generated if not set) |
| `--ip=IP` | Override the auto-detected IP address (multi-interface hosts) |
| `--rotate-secrets` | On reinstall, replace the existing SLM admin password. By default a reinstall keeps the password set in the wizard and ignores `--admin-pass=` |
| `--help`, `-h` | Show help |

Environment variables skip the matching interactive prompt:

| Variable | Effect |
|----------|--------|
| `AUTOBOT_INSTALL_BRANCH=<branch>` | Same as `--branch=` |
| `AUTOBOT_SLM_ADMIN_PASSWORD=<pass>` | Same as `--admin-pass=` |
| `AUTOBOT_INSTALL_INTERFACE=<iface>` | Pick the network interface by name instead of the menu |
| `OVERRIDE_IP=<ip>` | Skip IP detection and use this address |

### Log Files

All output is logged to `/var/log/autobot/install-<timestamp>.log`.

---

## Docker Deployment

For single-node or development setups, Docker Compose runs the stack without the
installer, Ansible or systemd.

**Requirements:** Docker Engine 24.0+ with the Compose v2 plugin (`docker compose`, not
the legacy `docker-compose` v1). Memory depends on what you start — the figures below are
the containers' configured memory limits (ceilings, not measured use), and building the
images needs headroom on top:

| What you start | Containers | Memory limits (sum) | Host RAM |
|----------------|------------|---------------------|----------|
| SLM web GUI only (`--profile slm`) | SLM, its GUI, Redis, PostgreSQL | ~3.1 GB | 4 GB+ free |
| Full stack | backend, worker, celery-beat, SLM, frontend, Redis, PostgreSQL, ChromaDB | ~9 GB | 16 GB recommended |

### SLM web GUI first (smallest start)

Start only the Service Lifecycle Manager and its web GUI, then add the rest of the fleet
from the GUI's Setup Wizard:

```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
docker compose --profile slm up -d --build autobot-slm-gui
```

The SLM GUI is then at **http://localhost/slm/**. It binds port 80, like the full stack's
frontend — run one or the other, not both.

### Full stack

```bash
docker compose up -d --build
```

This starts the core services: backend, SLM, frontend, Redis, PostgreSQL, and
ChromaDB.

### Profiles

Optional services are activated with `--profile`:

```bash
# Add a local Ollama LLM server
docker compose --profile ollama up -d --build

# Add Prometheus + Grafana monitoring
docker compose --profile monitoring up -d --build
```

### Exposed Services

| Service | URL |
|---------|-----|
| Frontend (user UI) | http://localhost |
| SLM Admin | http://localhost/slm/ |
| Backend API | http://localhost/api |
| RedisInsight | http://localhost:8001 |
| Ollama | http://localhost:11434 (profile: `ollama`) |
| Grafana | http://localhost:3000 (profile: `monitoring`) |

### Dev Mode (Hot Reload)

Copy the override template to enable live-reload for frontend and backend code:

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
docker compose up -d
```

Edit source files on the host and changes are reflected inside the containers
automatically.

### Environment

Docker Compose reads `.env.docker` by default. Copy `.env.example` to
`.env.docker` and adjust values as needed before starting.

---

## Setup Wizard

After the installer finishes, open the SLM web UI in your browser:

```
https://<server-ip>/slm/
```

Log in with the admin credentials printed at the end of the install. On first
login the setup wizard launches automatically and guides you through:

| Step | Action |
|------|--------|
| Welcome | Overview of the setup process |
| Add Nodes | Enter hostname/IP and SSH credentials for each fleet node |
| Test Connections | Verify SSH connectivity to every node |
| Enroll Agents | Install the AutoBot agent on each node |
| Assign Roles | Choose which role(s) each node performs |
| Provision Fleet | Run Ansible provisioning across the fleet |
| Verify Health | Confirm all nodes and required roles are healthy |
| Complete | Setup finished — redirects to Fleet Overview |

You can skip the wizard at any time and return to it later from
**Settings > General > Re-run Setup Wizard**.

### Resetting the Wizard

To run the wizard again:

```bash
# Via API
curl -sk -X POST https://localhost/api/setup/reset \
  -H "Authorization: Bearer <token>"

# Or from the Settings page in the UI
```

---

## Post-Install Structure

After a successful install the following paths are created:

```
/opt/autobot/
├── code_source/          # Git clone of AutoBot-AI
├── autobot-slm-backend/  # SLM backend (FastAPI + Ansible)
├── autobot-slm-frontend/ # SLM frontend (Vue 3, built)
├── venv/                 # Python virtual environment
└── .autobot-installed    # Install marker (prevents re-install)

/etc/autobot/
└── slm-secrets.env       # Generated admin credentials + secrets

/var/log/autobot/
└── install-*.log         # Installer logs
```

### Services

| Service | Description |
|---------|-------------|
| `autobot-slm-backend` | FastAPI backend (systemd) |
| `nginx` | Reverse proxy + static frontend |
| `postgresql` | Database |

Check service status:

```bash
sudo systemctl status autobot-slm-backend
sudo systemctl status nginx
sudo systemctl status postgresql
```

---

## Troubleshooting

### Installer fails at "Ansible Deployment"

Check the Ansible log:

```bash
tail -100 /var/log/autobot/install-*.log
```

Common causes:
- Missing internet access (package downloads fail)
- Port 5432 already in use (existing PostgreSQL)
- Insufficient disk space

### Cannot access the web UI

```bash
# Verify backend is running
sudo systemctl status autobot-slm-backend

# Check nginx
sudo nginx -t
sudo systemctl status nginx

# Test backend health directly
curl -sk https://localhost/api/health
```

### Setup wizard does not appear

The wizard only redirects on first run (before `setup_wizard_completed` is set
to `true` in the database). To force it:

```bash
curl -sk -X POST https://localhost/api/setup/reset \
  -H "Authorization: Bearer <token>"
```

Then refresh the browser.

### Re-running the installer

Use the `--reinstall` flag to bypass the "already installed" check:

```bash
sudo ./install.sh --reinstall
```

This does **not** destroy data — it re-runs all phases and overwrites code and
configuration while preserving the database.
