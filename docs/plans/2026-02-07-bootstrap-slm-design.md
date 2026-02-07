# SLM Bootstrap Script Design

**Issue:** #789
**Date:** 2026-02-07
**Status:** Approved

## Overview

**Script:** `infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh`

**Purpose:** Deploy complete SLM stack (backend + frontend) to a target node from the dev machine.

**Usage:**

```bash
./infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh [OPTIONS]

Options:
  -h, --host HOST       Target host (default: 172.16.168.19)
  -u, --user USER       SSH user with sudo (required)
  -k, --key PATH        SSH key path (tries ~/.ssh/id_rsa first)
  -p, --password        Prompt for SSH password (fallback if no key)
  --admin-password      Prompt for SLM admin password (default: generate random)
  --fresh               Force fresh install, ignore existing deployment
  --no-cleanup          Don't cleanup on failure
```

**Example:**

```bash
# With SSH key
./infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh -u root -h 172.16.168.19

# With password prompt
./infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh -u root -h 172.16.168.19 -p

# Custom admin password
./infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh -u root -h 172.16.168.19 --admin-password
```

## Target Architecture

```
nginx (:443 HTTPS, :80 redirect)
  ├── / → static files (/opt/autobot/autobot-slm-frontend/dist/)
  └── /api/* → proxy to uvicorn (:8000)
```

All-in-one deployment on SLM node (172.16.168.19).

## Directory Structure on Target

```
/opt/autobot/
├── autobot-slm-backend/
│   ├── .env                    # Generated config
│   ├── venv/                   # Python virtual environment
│   ├── start.sh                # Manual start script
│   ├── stop.sh                 # Manual stop script
│   ├── status.sh               # Check status script
│   └── ... (backend code)
├── autobot-slm-frontend/
│   ├── dist/                   # Built frontend assets
│   ├── start.sh                # nginx start
│   ├── stop.sh                 # nginx stop
│   ├── status.sh               # Check status
│   └── ... (frontend source)
├── autobot-shared/             # Shared utilities
├── nginx/
│   └── certs/
│       ├── slm.crt             # Self-signed TLS cert
│       └── slm.key             # Private key
├── certs/                      # Core AutoBot certs (separate from nginx)
│   ├── ca/
│   ├── services/
│   └── ssh/
└── logs/                       # Runtime logs
```

## User Model

- **Connect as:** Any user with sudo access (provided via -u flag)
- **Service user:** `autobot` (created, no login shell, owns /opt/autobot/)
- **Reserve user:** `autobot_admin` (created with sudo, password displayed once for backup)

The `autobot_admin` user is normally disabled and only enabled during key/cert rotation to prevent lockout.

## Execution Phases

### Phase 1: Pre-flight Checks (local)

- Verify script run from git repo root
- Check required directories exist:
  - `autobot-slm-backend/`
  - `autobot-slm-frontend/`
  - `autobot-shared/`
- Test SSH connectivity to target host
- Verify sudo access on target

### Phase 2: System Preparation (remote)

- Update package lists
- Install base packages:
  - `python3`, `python3-venv`, `python3-pip`
  - `nodejs`, `npm`
  - `nginx`
  - `rsync`, `curl`
- Create `/opt/autobot/` directory structure
- Create `autobot` service user (no login shell, owns /opt/autobot/)
- Create `autobot_admin` reserve user:
  - Add to sudo group
  - Generate random password
  - Display password once (user must save)
  - Lock account (unlock only when needed)

### Phase 3: Code Deployment (local to remote)

- Backup existing `/opt/autobot/` to `/opt/autobot.bak.TIMESTAMP/` if exists
- Rsync `autobot-slm-backend/` to `/opt/autobot/autobot-slm-backend/`
- Rsync `autobot-slm-frontend/` to `/opt/autobot/autobot-slm-frontend/`
- Rsync `autobot-shared/` to `/opt/autobot/autobot-shared/`
- Set ownership: `chown -R autobot:autobot /opt/autobot/`

### Phase 4: Backend Setup (remote)

- Create Python venv: `/opt/autobot/autobot-slm-backend/venv/`
- Install requirements: `pip install -r requirements.txt`
- Generate `.env` config:
  - `REDIS_HOST=172.16.168.23`
  - `REDIS_PORT=6379`
  - `SECRET_KEY=<generated>`
  - `DATABASE_URL=sqlite:///data/slm.db`
- Run database migrations
- Create SLM admin user:
  - Username: `admin`
  - Password: random or prompted (based on --admin-password flag)
- Install helper scripts (start.sh, stop.sh, status.sh)

### Phase 5: Frontend and Nginx Setup (remote)

- Run `npm install` in frontend directory
- Build production assets: `npm run build`
- Generate self-signed TLS certificate:
  - `/opt/autobot/nginx/certs/slm.crt`
  - `/opt/autobot/nginx/certs/slm.key`
  - Valid for 365 days
  - CN = hostname or IP
- Configure nginx:
  - Port 443: HTTPS with self-signed cert
  - Port 80: Redirect to HTTPS
  - Serve frontend static files from `/opt/autobot/autobot-slm-frontend/dist/`
  - Reverse proxy `/api/*` to `http://127.0.0.1:8000`
- Enable nginx site configuration
- Install helper scripts (start.sh, stop.sh, status.sh)

### Phase 6: Service Installation (remote)

- Install systemd unit: `autobot-slm-backend.service`
  - User: autobot
  - WorkingDirectory: /opt/autobot/autobot-slm-backend
  - ExecStart: venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
- Reload systemd daemon
- Enable and start `autobot-slm-backend.service`
- Enable and start nginx
- Wait for services to be ready
- Verify health endpoints respond:
  - `curl -k https://localhost/api/health`

### Phase 7: Summary (local)

Display:

- SLM URL: `https://172.16.168.19`
- Admin username: `admin`
- Admin password: `<generated or provided>`
- `autobot_admin` password: `<SAVE THIS - displayed once>`
- Next steps for adding nodes

## Error Handling

- Each phase checks previous phase success before proceeding
- On failure:
  - Display clear error message with suggested fix
  - Exit with non-zero code
  - Optionally cleanup partial deployment (unless --no-cleanup)
- Log all operations to `bootstrap-slm-YYYYMMDD-HHMMSS.log` (local)

## Idempotency

Safe to re-run:

- Skip package install if already present
- Skip user creation if `autobot`/`autobot_admin` exist
- Rsync with `--delete` ensures clean sync
- Backup existing deployment before overwrite
- Preserve existing secrets in `.env` if found
- Skip cert generation if valid certs exist

Re-run behavior:

- Normal re-run: backs up, re-syncs code, restarts services
- With `--fresh`: ignores existing, full fresh install

## Dependencies

**Redis:** Assumes Redis available at 172.16.168.23:6379. SLM should gracefully handle Redis unavailability (future enhancement).

## Files to Create

### Main script

- `infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh`

### Systemd templates

- `infrastructure/autobot-slm-backend/templates/autobot-slm-backend.service`

### Nginx template

- `infrastructure/autobot-slm-frontend/templates/autobot-slm.conf`

### Helper script templates

- `infrastructure/autobot-slm-backend/templates/backend-start.sh`
- `infrastructure/autobot-slm-backend/templates/backend-stop.sh`
- `infrastructure/autobot-slm-backend/templates/backend-status.sh`
- `infrastructure/autobot-slm-frontend/templates/frontend-start.sh`
- `infrastructure/autobot-slm-frontend/templates/frontend-stop.sh`
- `infrastructure/autobot-slm-frontend/templates/frontend-status.sh`

## Success Criteria

- [ ] Fresh machine with SSH leads to fully deployed SLM via single command
- [ ] HTTPS working with self-signed cert
- [ ] HTTP redirects to HTTPS
- [ ] SLM web GUI accessible and login works
- [ ] Backend API responding at /api/health
- [ ] Services survive reboot (systemd enabled)
- [ ] Re-run is safe and updates deployment
- [ ] `autobot_admin` password displayed and user can save it

---

## Phase B: Per-Role Templates (Completed)

**Status:** Complete (2026-02-07)

Extended the per-role infrastructure pattern to all AutoBot components. Each component now has its own templates directory with start/stop/status scripts and service definitions.

### Components Created

| Component              | VM   | Port           | Service Type            | Files   |
| ---------------------- | ---- | -------------- | ----------------------- | ------- |
| autobot-user-backend   | .20  | 8001           | systemd + uvicorn       | 4 files |
| autobot-user-frontend  | .21  | 443            | nginx                   | 4 files |
| autobot-npu-worker     | .22  | 8081           | systemd + uvicorn       | 4 files |
| autobot-db-stack       | .23  | 6379/5432/8000 | native systemd          | 6 files |
| autobot-ai-stack       | .24  | 8080           | systemd + uvicorn       | 4 files |
| autobot-browser-worker | .25  | 3000           | systemd + uvicorn       | 4 files |
| autobot-ollama         | .20  | 11434          | systemd (optional role) | 4 files |

### Directory Structure

```text
infrastructure/
├── autobot-user-backend/templates/
│   ├── autobot-user-backend.service
│   ├── backend-start.sh
│   ├── backend-stop.sh
│   └── backend-status.sh
├── autobot-user-frontend/templates/
│   ├── autobot-user.conf (nginx)
│   ├── frontend-start.sh
│   ├── frontend-stop.sh
│   └── frontend-status.sh
├── autobot-npu-worker/templates/
│   ├── autobot-npu-worker.service
│   ├── npu-start.sh
│   ├── npu-stop.sh
│   └── npu-status.sh
├── autobot-db-stack/templates/
│   ├── autobot-redis.service
│   ├── autobot-chromadb.service
│   ├── redis.conf
│   ├── db-start.sh
│   ├── db-stop.sh
│   └── db-status.sh
├── autobot-ai-stack/templates/
│   ├── autobot-ai-stack.service
│   ├── ai-start.sh
│   ├── ai-stop.sh
│   └── ai-status.sh
├── autobot-browser-worker/templates/
│   ├── autobot-browser-worker.service
│   ├── browser-start.sh
│   ├── browser-stop.sh
│   └── browser-status.sh
└── autobot-ollama/templates/
    ├── autobot-ollama.service
    ├── ollama-start.sh
    ├── ollama-stop.sh
    └── ollama-status.sh
```

### Notes

- **autobot-ollama** is an optional role assignable to .20 (has GPU access)
- **autobot-db-stack** uses native systemd services: Redis Stack, PostgreSQL (apt), ChromaDB (Python)
- **autobot-npu-worker** runs natively with uvicorn (requires Intel NPU drivers and video group access)
- All templates follow consistent naming: `{component}-start.sh`, `{component}-stop.sh`, `{component}-status.sh`
