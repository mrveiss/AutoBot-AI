# autobot-backend Infrastructure

> Role: `autobot-backend` | Node: Backend (.20 / 172.16.168.20) | Ansible role: `backend`

---

## Overview

Core AutoBot FastAPI backend. Handles AI agent orchestration, chat sessions, RAG pipeline, tool execution, user authentication, and all primary API endpoints.

Runs alongside `autobot-ollama` on the backend node (different ports, different users).

---

## Ports

| Port | Protocol | Public | Purpose |
|------|----------|--------|---------|
| 8443 | HTTPS | No (fleet-internal) | Primary API + WebSocket |
| 5555 | HTTP | No (loopback only) | Celery Flower monitoring UI |

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `autobot-backend` | systemd | 2 (after redis + postgres on .23) |
| `autobot-celery` | systemd | 3 |

---

## Health Check

```bash
# From another VM (WSL2 loopback limitation — cannot curl 172.16.168.20 from .20 itself)
ssh autobot@172.16.168.19 'curl -sk https://172.16.168.20:8443/api/health | jq'
```

Expected: `{"status": "healthy", ...}`

Startup takes ~6 minutes (loads GPUSemanticChunker, RAG optimizer, ChromaDB).

---

## Secrets

| Secret | File | Description |
|--------|------|-------------|
| `tls_cert` | `/etc/autobot/autobot-backend/tls.crt` | Self-signed cert (signed by SLM CA) |
| `tls_key` | `/etc/autobot/autobot-backend/tls.key` | Private key (mode 640) |
| `jwt_secret` | `.env` | JWT signing key |
| `redis_password` | `.env` | Shared from autobot-database |
| `service_auth_token` | `/etc/autobot/autobot-backend.env` | Inter-service auth token |

Environment file: `/etc/autobot/autobot-backend.env` (mode 640, `root:autobot-backend`)

---

## Deployment

```bash
# Full deployment (from autobot-slm-backend/ansible/)
ansible-playbook playbooks/deploy-full.yml --tags backend --limit backend_node

# Service restart only
ansible-playbook playbooks/slm-service-control.yml \
  -e "service=autobot-backend action=restart"

# Manual sync (dev)
# rsync directly — the sync-to-vm.sh script targets the autobot-backend/ dir
rsync -avz --exclude=venv/ --exclude=data/ --exclude=logs/ --exclude=__pycache__/ \
  autobot-backend/ autobot@172.16.168.20:/opt/autobot/autobot-backend/
```

---

## Logs

```bash
# Backend logs (NOT journald)
ssh autobot@172.16.168.20 'tail -f /var/log/autobot/backend.log'

# Celery logs
ssh autobot@172.16.168.20 'journalctl -u autobot-celery -f'
```

---

## Known Gotchas

- **WSL2 loopback**: Cannot health-check 172.16.168.20 from the backend node itself. Use .19 as a relay.
- **6-minute startup**: The backend loads large ML models at init. nginx returns 504 during this window.
- **Restart cost**: Each restart causes a 6-minute outage. Avoid unless essential.
- **Python env**: Uses conda env at `/home/autobot/miniconda3/envs/autobot-backend` (Python 3.12).
- **Log location**: `StandardOutput=append:/var/log/autobot/backend.log` — not journald.

---

## Ansible Role

Role: `backend` in `autobot-slm-backend/ansible/roles/backend/`

Key tasks:
- Deploy Python venv
- Install requirements.txt
- Render systemd unit from `templates/autobot-backend.service.j2`
- Render `.env` from `templates/.env.j2`
- Start + enable service
