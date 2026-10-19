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
| `--uninstall` | Remove AutoBot: shows what it will remove, then asks you to type `UNINSTALL`. See [Uninstalling](#uninstalling) |
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
| `NETWORK_SUBNET=<cidr>` / `NETWORK_GATEWAY=<ip>` | Use this network instead of detecting it. The subnet is the source the firewall rules allow, so if it cannot be detected the installer stops and asks for these instead of guessing |

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

| What you start | Containers | Memory limits (sum) | Measured use | Host RAM |
|----------------|------------|---------------------|--------------|----------|
| SLM web GUI only (`--profile slm`) | SLM, its GUI, Redis, PostgreSQL | ~3.1 GB | ~215 MiB idle just after start (CI); ~414 MiB with the SLM restarting (an external test) | 1 GB+ free to run; building the images needs more (not measured) |
| Full stack | backend, worker, celery-beat, SLM, frontend, Redis, PostgreSQL, ChromaDB | ~9 GB | not measured | 16 GB recommended |

### First: per-host secrets and network range

```bash
bash docker/generate-secrets.sh
```

This writes the gitignored `docker/.env.secrets`: unique signing secrets and passwords,
and `AUTOBOT_DOCKER_MGMT_PREFIX`, a private `/24` for the stack's management network that
overlaps none of this host's routes or existing Docker networks. Compose refuses to start
without it; there is no built-in default range, because a fixed one can collide with your
LAN and cut the host off the network. To choose the range yourself, set
`AUTOBOT_DOCKER_MGMT_PREFIX=<first three octets>` (e.g. `10.77.3`) before running the
script. Keep the file: every command below passes it.

It also holds `AUTOBOT_ADMIN_PASSWORD`, the password of the main app's first admin
account (user `admin`). The backend creates that account on its first start. To read it:

```bash
grep '^AUTOBOT_ADMIN_PASSWORD=' docker/.env.secrets
```

Log in to the main app at **http://localhost** with `admin` and that password, then change
it. A stack started without the line has no main-app account; add the line with
`bash docker/generate-secrets.sh` (it keeps every value already in the file) and restart the
backend.

### SLM web GUI first (smallest start)

Start only the Service Lifecycle Manager and its web GUI, then add the rest of the fleet
from the GUI's Setup Wizard:

```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
bash docker/generate-secrets.sh
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets --profile slm up -d --build autobot-slm-gui
```

The SLM GUI is then at **http://localhost/slm/**. It binds port 80, like the full stack's
frontend — run one or the other, not both.

### Full stack

```bash
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets up -d --build
```

This starts the core services: backend, SLM, frontend, Redis, PostgreSQL, and
ChromaDB.

### Profiles

Optional services are activated with `--profile`:

```bash
# Add a local Ollama LLM server (only for running models on this host)
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets --profile ollama up -d --build

# Add Prometheus + Grafana monitoring
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets --profile monitoring up -d --build
```

Which AI providers to use is your choice: local, hybrid or cloud (#15494). Cloud and
hybrid providers need no local model. Only on the fully local path, with the `ollama`
profile, does Ollama start empty: pull the models `docker/.env.docker` names, or the
ones you set there instead:

```bash
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets exec autobot-ollama ollama pull qwen3.5:9b
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets exec autobot-ollama ollama pull nomic-embed-text:latest
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
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets up -d
```

Edit source files on the host and changes are reflected inside the containers
automatically.

### Environment

Every command above passes `--env-file docker/.env.docker`. That is the only Docker env file
(#18555). To change a value, edit a copy of it and pass the copy with `--env-file` instead.
`.env.example` is the reference for native installs, not for Docker.

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

## Uninstalling

```bash
sudo /opt/autobot/code_source/install.sh --uninstall                       # shows the plan, then asks
sudo bash /opt/autobot/code_source/scripts/uninstall.sh --dry-run          # only shows what would go
sudo bash /opt/autobot/code_source/scripts/uninstall.sh --purge-data       # also your AutoBot data
```

The uninstaller first prints its plan, then asks you to type `UNINSTALL`. `--yes` skips the
question for scripted use. Without a terminal and without `--yes`, it refuses instead of
proceeding.

By default it removes AutoBot's services and units, its code, configs, nginx sites, sudoers
files and the apt sources it added. **Your data stays** unless you add a flag:

| Flag | Also removes |
|---|---|
| `--purge-data` | AutoBot's databases; the whole `/opt/autobot` tree, including anything else in it (by default only AutoBot's own code there goes; its `backups`, `db-backups`, `snapshots`, `data`, `models`, `plugins`, `.env`, `config`, certificates, any folder AutoBot does not know as its code, and the data inside its code folders -- the backends' `data` and `.env`, the ChromaDB store -- stay); `/etc/autobot` (secrets and credentials); its state and backups elsewhere; and the accounts the installer created, with their homes. PostgreSQL itself only if every cluster was inspected and holds nothing but AutoBot's databases and roles, and its directories only if empty afterwards |
| `--purge-shared` | grafana, prometheus, node-exporter, redis-stack and python3-psycopg2, with their data. Nothing records who installed them, so they stay by default |

It never removes:
- **An account it did not create.** The installer records the `autobot` account only if it
  created it, in `/etc/autobot/install-record`. On a machine where `autobot` already existed,
  for example your own login, the account and its home stay. An install made before this record
  existed has no record, so no account, recorded package or recorded apt source is removed there.
- **More than it asked apt for.** If purging a package would also remove something else, the
  purge is skipped and the plan names it. No `apt autoremove` is run.
- **nginx, the base packages** the installer needs (git, curl, openssh-server, ...), `ollama`,
  the `docker` and `intel-openvino` sources, and `deadsnakes` unless the installer recorded
  adding it. Nor the service accounts the roles create (prometheus, node_exporter, ...).

A partial install that never got as far as cloning the code has no uninstaller copy on the
machine; `install.sh --uninstall` says so instead of guessing.

The log is written to `/var/tmp/autobot-uninstall-<timestamp>.log`, which survives the uninstall.

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
