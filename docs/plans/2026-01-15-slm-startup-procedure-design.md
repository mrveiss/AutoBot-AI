# SLM Startup Procedure Design

> **Status**: Draft
> **Created**: 2026-01-15
> **Issue**: #726

## Overview

This document defines the new simplified startup procedure for AutoBot where the Service Lifecycle Manager (SLM) on a dedicated admin machine becomes the single entry point for managing the entire fleet. All node deployments and service management happen through the SLM Admin GUI.

## Architecture

### Admin Machine (172.16.168.19)

The admin machine is a clean, dedicated management host running only SLM-related services.

```
┌─────────────────────────────────────────────────────────┐
│                 SLM Admin Machine                        │
│                   172.16.168.19                          │
│                                                          │
│  ┌─────────────────┐  ┌─────────────────┐               │
│  │  SLM Backend    │  │  SLM Admin UI   │               │
│  │  (FastAPI)      │  │  (Vue 3)        │               │
│  │  Port: 8000     │  │  Port: 5174     │               │
│  └─────────────────┘  └─────────────────┘               │
│                                                          │
│  ┌─────────────────┐  ┌─────────────────┐               │
│  │  Prometheus     │  │  Grafana        │               │
│  │  Port: 9090     │  │  Port: 3000     │               │
│  │  (localhost)    │  │  (localhost)    │               │
│  └─────────────────┘  └─────────────────┘               │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  /home/autobot/AutoBot/  (full codebase)        │    │
│  │  - Source of truth for all node deployments     │    │
│  │  - Ansible playbooks in ansible/                │    │
│  │  - SQLite state DB in data/slm.db               │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  Systemd services:                                       │
│  - slm-backend.service                                  │
│  - slm-admin-ui.service                                 │
│  - prometheus.service                                   │
│  - grafana-server.service                               │
└─────────────────────────────────────────────────────────┘
```

### Fleet Architecture

```
172.16.168.19 (Admin/Management)
├── SLM Backend + Admin UI
├── Grafana + Prometheus (default, portable)
├── Ansible controller
├── SQLite state DB
└── Full AutoBot codebase (distribution source)

172.16.168.20 (Main AutoBot) - deployed via SLM
├── AutoBot Backend (chat, agents, LLM, etc.)
└── VNC server

172.16.168.21 (Frontend) - deployed via SLM
└── AutoBot Vue frontend

172.16.168.22 (NPU Worker) - deployed via SLM
└── Hardware AI acceleration

172.16.168.23 (Redis) - deployed via SLM
└── Redis database

172.16.168.24 (AI Stack) - deployed via SLM
└── Ollama / AI processing

172.16.168.25 (Browser) - deployed via SLM
└── Playwright automation
```

### Runtime vs Management Separation

| Action | Admin Online | Admin Offline |
|--------|--------------|---------------|
| Normal service operation | Works | Works |
| Service auto-restart on crash | Works | Works (systemd) |
| VM reboot recovery | Works | Works (systemd) |
| New deployments | Works | Waits for admin |
| Rolling updates | Works | Waits for admin |
| Monitoring dashboards | Works | Degraded (no new data) |

## SLM Standalone Backend

The SLM backend runs independently with minimal dependencies, separate from the main AutoBot backend.

### Directory Structure

```
/home/autobot/AutoBot/
├── slm-server/                  # Standalone SLM backend
│   ├── main.py                  # FastAPI entry point
│   ├── config.py                # SLM configuration
│   ├── requirements.txt         # Minimal dependencies
│   ├── api/
│   │   ├── nodes.py             # Node management
│   │   ├── heartbeats.py        # Agent heartbeats
│   │   ├── deployments.py       # Ansible deployments
│   │   ├── stateful.py          # Backup/replication
│   │   └── websockets.py        # Real-time updates
│   ├── services/
│   │   ├── database.py          # SQLite operations
│   │   ├── reconciler.py        # Health monitoring
│   │   ├── deployment_manager.py
│   │   └── stateful_manager.py
│   └── models/                  # Pydantic models
│
├── slm-admin/                   # Vue Admin UI
├── ansible/                     # Deployment playbooks
├── backend/                     # Full AutoBot backend (for distribution)
├── autobot-user-frontend/                 # Full AutoBot frontend (for distribution)
└── data/
    └── slm.db                   # SQLite state database
```

### Dependencies

Minimal set (~10 packages):
- fastapi
- uvicorn
- sqlalchemy
- aiosqlite
- pydantic
- ansible-runner
- aiofiles
- python-jose (JWT)
- passlib (passwords)
- websockets

## Startup Flow

### Boot Sequence

```
1. Machine boots
         │
         ▼
2. systemd starts slm.target
         │
         ├──► prometheus.service (localhost:9090)
         ├──► grafana-server.service (localhost:3000)
         ├──► slm-backend.service (port 8000)
         └──► slm-admin-ui.service (port 5174)
         │
         ▼
3. Admin opens https://172.16.168.19/
         │
         ▼
4. Login with admin credentials
         │
         ▼
5. Fleet Overview shows all nodes as "offline"
         │
         ▼
6. Admin manually triggers deployments via GUI
         │
         ▼
7. SLM runs Ansible → nodes come online
         │
         ▼
8. Agents on nodes send heartbeats → status updates
```

### Startup Modes

**v1 (Minimal auto-start)**:
- SLM services start on boot
- All node deployments are manual via GUI

**Future (Smart auto-start)**:
- SLM checks last known state
- Automatically brings up nodes that were previously running

**Future (Full auto-start)**:
- SLM starts and deploys all nodes to configured roles

### Systemd Configuration

**slm.target** (wrapper):
```ini
[Unit]
Description=SLM Admin Services
After=network-online.target
Wants=network-online.target

[Install]
WantedBy=multi-user.target
```

**slm-backend.service**:
```ini
[Unit]
Description=SLM Backend
PartOf=slm.target
After=network.target

[Service]
Type=simple
User=autobot
WorkingDirectory=/home/autobot/AutoBot/slm-server
ExecStart=/home/autobot/AutoBot/slm-server/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=slm.target
```

**slm-admin-ui.service**:
```ini
[Unit]
Description=SLM Admin UI
PartOf=slm.target
After=slm-backend.service

[Service]
Type=simple
User=autobot
WorkingDirectory=/home/autobot/AutoBot/slm-admin
ExecStart=/usr/bin/node /home/autobot/AutoBot/slm-admin/server.js
Restart=always
RestartSec=5

[Install]
WantedBy=slm.target
```

## Access Management & Security

### Network Access

```
External Access (nginx HTTPS :443)
─────────────────────────────────────
https://172.16.168.19/         → SLM Admin UI
https://172.16.168.19/api/     → SLM Backend

Internal Only (localhost)
─────────────────────────────────────
127.0.0.1:9090  → Prometheus
127.0.0.1:3000  → Grafana (proxied via SLM after auth)
```

### Authentication Layers

1. **Network**: Admin machine accessible only from trusted sources
   - Dev machine (172.16.168.20)
   - Local network / VPN
   - Optional IP whitelist during install

2. **SSL/TLS**: All services behind nginx with HTTPS
   - Self-signed cert (initial setup)
   - Option: Let's Encrypt or custom CA

3. **Authentication**: Login required for all access
   - SLM Admin UI: username/password
   - API: JWT tokens for programmatic access
   - Grafana: own credentials (for standalone access)

4. **Role-based (future)**: admin / operator / viewer

### Nginx Configuration

```nginx
server {
    listen 443 ssl;
    server_name 172.16.168.19;

    ssl_certificate /etc/ssl/slm/cert.pem;
    ssl_certificate_key /etc/ssl/slm/key.pem;

    # SLM Admin UI
    location / {
        proxy_pass http://127.0.0.1:5174;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # SLM API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
    }

    # Grafana (proxied, requires SLM auth)
    location /grafana/ {
        auth_request /api/auth/verify;
        proxy_pass http://127.0.0.1:3000/;
    }

    # Prometheus (proxied, requires SLM auth)
    location /prometheus/ {
        auth_request /api/auth/verify;
        proxy_pass http://127.0.0.1:9090/;
    }
}
```

## Portable Monitoring Role

Grafana and Prometheus can run on the admin machine (default) or be moved to a separate monitoring host.

### Configuration Options

```
SLM GUI: Settings → Monitoring → Location

┌─────────────────────────────────────────────────────────┐
│  Monitoring Location                                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ○ Local (on this admin machine)                        │
│    - Grafana/Prometheus run here                        │
│    - Proxied through SLM, no separate login             │
│                                                          │
│  ○ Remote host                                          │
│    - Host: [172.16.168.XX]                              │
│    - Grafana credentials: [user/pass]                   │
│    - Deploy monitoring role via Ansible                 │
│                                                          │
│  [Apply Changes]                                         │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Scenarios

**Scenario A: All-in-one (default)**
```
172.16.168.19 (Admin)
├── SLM Backend + UI
├── Grafana (proxied through SLM)
└── Prometheus (proxied through SLM)
```

**Scenario B: Separate monitoring host**
```
172.16.168.19 (Admin)
├── SLM Backend + UI
└── Points to external monitoring

172.16.168.XX (Monitoring)
├── Grafana (port 3000, own credentials)
├── Prometheus (port 9090)
└── Deployed via SLM Ansible "monitoring" role
```

### Bidirectional Movement

- **Move to remote**: Deploy to target → verify → stop local → update config
- **Absorb to local**: Deploy here → verify → stop remote → update config

Both directions automated via Ansible using the same `monitoring` role.

### Database Settings

```python
# SLM settings table
monitoring_mode: "local" | "remote"
monitoring_host: "172.16.168.XX"
grafana_url: "https://..."
grafana_credentials: (encrypted)
prometheus_url: "http://..."
```

## Installer Script

### Usage

```bash
# Interactive mode (prompts for options)
./install-slm.sh

# Unattended mode (defaults, for automation)
./install-slm.sh --unattended

# Mixed (some options as flags)
./install-slm.sh --git-source=github --branch=main
```

### Interactive Prompts

```
╔══════════════════════════════════════════════════════════╗
║           SLM Admin Machine Installer                     ║
╚══════════════════════════════════════════════════════════╝

[1/6] Code source:
  1) Clone from GitHub (mrveiss/AutoBot-AI)
  2) Sync from dev machine (172.16.168.20)
  > 1

[2/6] Branch/version:
  > main

[3/6] SLM admin username:
  > admin

[4/6] SLM admin password:
  > ********

[5/6] Expose Grafana directly (separate login)?
  1) No - access through SLM only (recommended)
  2) Yes - direct access with own credentials
  > 1

[6/6] Expose Prometheus directly?
  1) No - access through SLM only (recommended)
  2) Yes - direct access
  > 1

Installing...
```

### Installation Steps

```
install-slm.sh
─────────────────────────────────────
1.  Check prerequisites (OS, sudo, SSH)
2.  Install system packages
    - python3, python3-venv, pip
    - nginx
    - ansible
3.  Install Prometheus + Grafana (apt)
4.  Clone/sync AutoBot repo to /home/autobot/AutoBot/
5.  Create Python venv for slm-server
6.  Install slm-server dependencies
7.  Build slm-admin Vue app (npm build)
8.  Generate self-signed SSL certificate
9.  Configure nginx reverse proxy
10. Create systemd unit files
11. Initialize SQLite database
12. Create admin user
13. Configure Grafana (if local)
14. Enable and start slm.target
15. Print access URL + credentials
─────────────────────────────────────
Done! Access SLM at https://172.16.168.19/
```

### Unattended Defaults

- Source: GitHub, branch: main
- Admin user: admin
- Admin password: auto-generated (printed at end)
- Grafana: local, proxied through SLM
- Prometheus: local, proxied through SLM

## Code Distribution

The admin machine holds the full AutoBot codebase and serves as the distribution source for all nodes.

### Code Sources

1. **Git clone from GitHub**: Clean deployments, version control
2. **Sync from dev machine**: Rapid iteration during development

Both methods supported, configurable during install and updatable via GUI.

### Ansible Distribution

When deploying a role to a node, Ansible:
1. Syncs required code from admin machine
2. Sets up Python/Node environment
3. Configures systemd services
4. Starts the service
5. Registers agent for heartbeats

## Implementation Phases

### Phase 1: Installer Script
- [ ] Create `scripts/install-slm.sh`
- [ ] System package installation
- [ ] Prometheus + Grafana setup
- [ ] SSL certificate generation
- [ ] Nginx configuration
- [ ] Systemd unit files

### Phase 2: SLM Standalone Backend
- [ ] Extract SLM code to `slm-server/`
- [ ] Minimal dependencies
- [ ] Authentication (JWT)
- [ ] Settings API for monitoring location

### Phase 3: Admin UI Enhancements
- [ ] Login page
- [ ] Settings page for monitoring location
- [ ] Grafana iframe integration
- [ ] Deploy/absorb monitoring controls

### Phase 4: Ansible Roles Update
- [ ] Add `monitoring` role (Grafana + Prometheus)
- [ ] Update existing roles for new architecture
- [ ] Code sync from admin machine

## Success Criteria

1. Single command installs complete SLM admin machine
2. Boot admin machine → services auto-start
3. Login to GUI → see fleet status
4. Deploy nodes via GUI → Ansible provisions them
5. Monitoring accessible through SLM (no separate login)
6. Can move monitoring to separate host and back
7. All settings changeable via GUI, deployed via Ansible
