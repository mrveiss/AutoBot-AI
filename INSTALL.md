# AutoBot Installation Guide

## Overview

AutoBot is a self-hosted AI platform you own: a small core, the **Service Lifecycle
Manager (SLM)** management layer, and modules on top. Installing AutoBot means standing
up that stack on your own hardware. (Throughout this guide, **SLM** always means *Service
Lifecycle Manager* — AutoBot's management layer — never "small language model." For the
full picture, see [The AutoBot Platform Model](docs/architecture/PLATFORM_MODEL.md).)

Installation uses a two-phase deployment model:

1. **`install.sh`** — a shell script that deploys the **Service Lifecycle Manager (SLM)**
   and all dependencies onto a blank Ubuntu 22.04+ host. The SLM is the management layer
   that then deploys, operates, and scales the rest of the infrastructure.
2. **Setup Wizard** — a guided web UI that walks you through adding fleet nodes, testing
   connections, enrolling agents, assigning roles, and provisioning.

After both phases complete you have a fully operational AutoBot platform and fleet —
ready to run the core and install modules.

---

## Requirements

`install.sh` installs the **SLM node** -- the control plane. The **platform nodes** (backend,
frontend, Redis, ChromaDB, LLM) are provisioned afterwards by the Setup Wizard, onto the hosts
you add there, which may include this one.

**SLM node** -- what `install.sh` checks before it starts:

| Requirement | Minimum |
|-------------|---------|
| OS | Ubuntu 22.04+ (the installer gets Python 3.14 and Ansible from Ubuntu PPAs; on Debian and other systems, use [Docker](#docker-deployment)) |
| Init system | **systemd running as PID 1** — the installer manages every service as a systemd unit |
| RAM | 1.5 GB (the installer refuses to run below this; SLM control plane only) |
| Disk | 5 GB free (the installer refuses to run below this); 20 GB recommended |
| Access | Root (or sudo) |
| Network | Internet access for package downloads |

**Supported hosts:** an Ubuntu 22.04+ VM or bare-metal machine booted with systemd, or
WSL2 with systemd enabled (`[boot] systemd=true` in `/etc/wsl.conf`). **Not supported by
`install.sh`:** containers and other hosts where systemd is not PID 1 — use the
[Docker deployment](#docker-deployment) there instead.

**Platform nodes:** no minimum is enforced. Provisioning reaches them over SSH, and the
backend unit sizes its own memory limits from the host's memory. A local LLM is the main
consumer: plan memory for the models you pull, or use a cloud provider instead (see
[Choose your AI provider](docs/user-guide/03-configuration.md#choose-your-ai-provider)).

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

The `main` one-liner runs the newest installer, unpinned and unverified. For a production host,
install a release instead and verify it first.

### Verified, pinned install (recommended)

Each release publishes three files next to its notes (#18666):
- `install.sh`, pinned to that release: it installs exactly that tag;
- `install.sh.sha256`, its checksum;
- `install.sh.sig`, a cosign signature made with the key in this repository's `cosign.pub`.

Releases made before this change do not carry them. Verify, then run:

```bash
TAG=v0.0.0   # the release you want, from https://github.com/mrveiss/AutoBot-AI/releases
BASE="https://github.com/mrveiss/AutoBot-AI/releases/download/${TAG}"
curl -fsSLO "${BASE}/install.sh"
curl -fsSLO "${BASE}/install.sh.sha256"
curl -fsSLO "${BASE}/install.sh.sig"
curl -fsSL -o cosign.pub "https://raw.githubusercontent.com/mrveiss/AutoBot-AI/${TAG}/cosign.pub"
sha256sum -c install.sh.sha256 \
  && cosign verify-blob --key cosign.pub --signature install.sh.sig install.sh \
  && sudo bash install.sh
```

The `&&` chain is the point: if a download is missing, the checksum differs or the signature does
not verify, `install.sh` never runs.

A signature only proves the script matches the key, so the key is the thing to check. Fetching
`cosign.pub` from the same tag, as above, proves nothing by itself: whoever can replace a tag can
replace its key, signature and release notes together. The first time, compare `sha256sum cosign.pub`
with a fingerprint from a channel a release cannot rewrite:

- `cosign.pub` on the `main` branch, viewed in the repository's web interface at a commit you pin
  (its history shows when the key last changed), and
- the fingerprint the owner publishes alongside the key (#19126).

Then keep that `cosign.pub` and verify later releases against your copy. The SHA256 printed in each
signed release's notes is a comparison aid only, never the proof.

Until the signing key is set up, a release carries `install.sh` and `install.sh.sha256` but no
`install.sh.sig`; its release job says so in a warning. For such a release, verify the checksum and
drop the `cosign` step from the chain: `sha256sum -c install.sh.sha256 && sudo bash install.sh`. A checksum downloaded from
the same release proves the file arrived intact, not who made it: authenticity needs the signing key
(#19126).

Pinned but unverified, as a one-liner next to the `main` one:

```bash
curl -fsSL "https://github.com/mrveiss/AutoBot-AI/releases/download/${TAG}/install.sh" | sudo bash
```

**Offline or air-gapped installs are out of scope for now.** Phase 3 clones the repository from
GitHub, and the roles install packages from your distribution's and vendors' mirrors.

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
| `--admin-pass-file=PATH` | Read the SLM admin password from the first line of PATH (auto-generated if not set). The file must be non-empty and mode `600` or tighter (`chmod 600 PATH`), or the installer refuses it. `--admin-pass=` is refused: a command-line argument is readable by every local user (#19236). |
| `--ip=IP` | Override the auto-detected IP address (multi-interface hosts) |
| `--rotate-secrets` | On reinstall, replace the existing SLM admin password. By default a reinstall keeps the password set in the wizard and ignores `--admin-pass=` |
| `--help`, `-h` | Show help |

Environment variables skip the matching interactive prompt:

| Variable | Effect |
|----------|--------|
| `AUTOBOT_INSTALL_BRANCH=<branch>` | Same as `--branch=` |
| `AUTOBOT_SLM_ADMIN_PASSWORD=<pass>` | The admin password itself, not a file path (unlike `--admin-pass-file=`, which names a file) |
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

Every credential compose needs comes from this file; none has a built-in default. If one is
missing, `docker compose` stops with an error that names it (#17793).

**Upgrading a stack that already has data.** An existing Postgres volume keeps the database
password it was created with and ignores a new one. So if `docker/.env.secrets` has no
`AUTOBOT_DB_PASSWORD` line, `generate-secrets.sh` refuses to create one while the Postgres
volume exists. Add the password the stack already uses (a stack started from the old tracked
default used `autobot`), then rerun the script to add any other missing line:

```bash
echo 'AUTOBOT_DB_PASSWORD=<the password this stack already uses>' >> docker/.env.secrets
bash docker/generate-secrets.sh
```

### SLM web GUI first (smallest start)

Start only the Service Lifecycle Manager and its web GUI, then add the rest of the fleet
from the GUI's Setup Wizard:

```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
bash docker/generate-secrets.sh
docker compose --env-file docker/.env.docker --env-file docker/.env.secrets --profile slm up -d --build autobot-slm-gui
```

The SLM GUI is then at **http://localhost/slm/**. It binds ports 80 and 443, like the full
stack's frontend — run one or the other, not both.

To serve it over HTTPS, put a certificate in `docker/certs/` (`autobot.crt` and `autobot.key`;
`bash docker/certs/generate-self-signed.sh` makes a self-signed pair for testing) and select
the TLS config. Port 80 then redirects to HTTPS:

```bash
AUTOBOT_DOCKER_SLM_NGINX_CONF=./docker/nginx/nginx-slm-ssl.conf \
  docker compose --env-file docker/.env.docker --env-file docker/.env.secrets --profile slm up -d autobot-slm-gui
```

The GUI is then at **https://localhost/slm/**. If host port 443 is already in use, publish
HTTPS on another port with `AUTOBOT_DOCKER_SLM_HTTPS_PORT=<port>` (the GUI is then at
`https://localhost:<port>/slm/`). The full stack's frontend switches to TLS the same way, with
`AUTOBOT_DOCKER_NGINX_CONF=./docker/nginx/nginx-ssl.conf`.

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

Which AI providers to use is your choice: local, hybrid or cloud (#15494). Out of the box,
every LLM tier points at `autobot-ollama` (`docker-compose.yml`, the `AUTOBOT_OLLAMA_*` and
`AUTOBOT_LLM_*` endpoints), which only runs with `--profile ollama`. Without that profile, either
point `AUTOBOT_OLLAMA_HOST` at an Ollama server you run, or use Anthropic:
`ANTHROPIC_API_KEY` is the one provider key compose passes to the backend. Then select the
provider in **SLM Admin > Settings > LLM**. With the `ollama` profile, Ollama starts empty:
pull the models `docker/.env.docker` names, or the ones you set there instead:

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
`.env.example` is the reference for native installs, not for Docker. Native-install development
tooling reads `.env.base` (the shared keys) and then one overlay -- `.env.localhost`, `.env.native-vm`
or `.env.network` -- in that order (#18555).

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
**Settings > General > Launch Wizard**.

### Resetting the Wizard

To start the wizard over from the first step, use **Settings > General > Reset Wizard** in the
SLM web UI.

Over the API, log in to the SLM first. The response's `access_token` is the bearer token
(an account with MFA enabled gets an MFA challenge instead; use the UI for that one). These
commands send the admin password and a token, so run them **on the SLM server itself**: the
installer's certificate is self-signed, and `-k` (skip certificate checks) is only safe over
loopback. From another machine, install a certificate from a CA you trust, drop `-k`, and use
the server's name instead of `127.0.0.1`. `--fail` makes a rejected login or reset exit non-zero
instead of looking successful:

```bash
TOKEN=$(curl -sSk --fail -X POST https://127.0.0.1/slm/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username": "admin", "password": "<password>"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -sSk --fail -X POST https://127.0.0.1/slm/api/setup/reset -H "Authorization: Bearer ${TOKEN}"
```

### After the wizard

- **First login to the main app**, and where the chat UI is: [README: First login](README.md#first-login).
- **First steps:** [Quick Start](docs/user-guide/02-quickstart.md) · **settings and the AI provider:** [Configuration](docs/user-guide/03-configuration.md) · **problems:** [Troubleshooting](docs/user-guide/04-troubleshooting.md).
- **Upgrades, backups and recovery:** [README: Running AutoBot](README.md#running-autobot).

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
| `prometheus`, `grafana-server`, `node_exporter` | Monitoring, installed by phase 4 (`alertmanager` only when `monitoring_install_alertmanager` is set) |

Check service status:

```bash
sudo systemctl status autobot-slm-backend
sudo systemctl status nginx
sudo systemctl status postgresql
sudo systemctl status prometheus grafana-server node_exporter
```

### The `autobot` account's root access

The installer creates the `autobot` service account and gives it **unrestricted passwordless
root**: it writes `autobot ALL=(ALL) NOPASSWD:ALL` to `/etc/sudoers.d/autobot`.

Why it is that broad today:
- the SLM deploys and updates hosts with Ansible using `become`, and that runs arbitrary
  module code as root through `sudo /bin/sh -c ...`, which a sudoers command list cannot
  usefully restrict;
- the builtin updater and the agent's privileged tasks run commands as root through `sudo -n`.

Treat the `autobot` account as root-equivalent: anyone who can act as it can act as root on
this host. Narrowing the grant without breaking deploys is designed in #19245.

To audit it:

```bash
sudo cat /etc/sudoers.d/autobot   # exactly the one line above, mode 0440
sudo -l -U autobot                # what the account may run
```

To remove it, run `sudo rm /etc/sudoers.d/autobot`. Fleet deploys, the builtin updater and
privileged agent tasks then stop working on this host until it is restored. The uninstaller
removes it along with the account it created (see below).

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

# Test the SLM backend's health through nginx (/slm/api/ is the SLM; /api/ is the main
# backend, which exists only once the wizard has provisioned it)
curl -sk https://localhost/slm/api/health
```

### Setup wizard does not appear

The wizard only redirects on first run (before `setup_wizard_completed` is set
to `true` in the database). To force it, reset it as described in
[Resetting the Wizard](#resetting-the-wizard), then refresh the browser.

### Docker: containers cannot reach each other

Symptom: a service restarts in a loop, and its log says it `cannot reach PostgreSQL at
autobot-postgres:5432` (or Redis, or another service), naming the host and port it tried and
whether the attempt **timed out**, was **refused**, or the name **did not resolve**.

- **Timed out:** nothing answered in time. A timeout alone does not say why; possible causes
  include packets being dropped, a target host or container that is down or overloaded, or
  routing that leads nowhere. One common cause is a host firewall whose forwarding policy drops
  container-to-container traffic. Check `sudo iptables -S FORWARD` (a `-P FORWARD DROP` with no
  Docker accept rules points there), and if so allow traffic on the Docker bridges, or restore
  Docker's own chains with `sudo systemctl restart docker`.
- **Refused:** the target container is not listening yet, or not running. Check
  `docker compose --env-file docker/.env.docker --env-file docker/.env.secrets ps` and that
  container's logs.
- **Did not resolve:** Docker's DNS could not find the name. Possible causes include the two
  containers not sharing a network, the target service not being started (or a different
  service name), or a host DNS problem. Check that the name matches a service in the compose
  files, and start the whole stack with the same compose files and env files, so every service
  joins the networks it declares.

### Re-running the installer

Use the `--reinstall` flag to bypass the "already installed" check:

```bash
sudo ./install.sh --reinstall
```

This does **not** destroy data — it re-runs all phases and overwrites code and
configuration while preserving the database.
