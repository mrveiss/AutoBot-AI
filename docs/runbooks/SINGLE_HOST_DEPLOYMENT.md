# Runbook: Single-Host AutoBot Deployment

**Issue #2961** | Last updated: 2026-04-08

---

## Overview

Single-host deployment runs all AutoBot services (backend API, frontend UI, AI stack, Redis, browser automation, etc.) on a single machine using loopback aliases (`127.0.0.x`). This mode is suitable for:

- **Development environments** — local testing and debugging
- **Lab / evaluation setups** — single-machine POC or demo
- **Small team prototyping** — all-in-one instance with full capabilities
- **WSL2 development** — complete AutoBot environment without VMs

This differs from **distributed deployment**, where each role (backend, frontend, database, AI, browser) runs on a dedicated VM.

---

## Architecture: Co-located Services

```
┌─────────────────────────────────────────────────────────┐
│                   Single Host Machine                    │
├─────────────────────────────────────────────────────────┤
│  Backend (127.0.0.3:8001)    [FastAPI, agents, chat]    │
│  Frontend (127.0.0.1:5173)   [Vue 3 dev or nginx]       │
│  Redis (127.0.0.7:6379)      [Cache & session store]    │
│  ChromaDB (127.0.0.7:8100)   [Vector DB for KB]         │
│  AI Stack (127.0.0.6:8080)   [vLLM / Ollama inference]  │
│  Browser (127.0.0.4:3000)    [Playwright + VNC]         │
│  NPU Worker (127.0.0.5:8081) [Hardware AI accel]        │
└─────────────────────────────────────────────────────────┘
```

Each service has a stable loopback IP so services can reach each other by IP
(e.g., backend calls Redis at `127.0.0.7:6379`) without network routing.

See [VM_ROLES.md](../architecture/VM_ROLES.md) for detailed role definitions.

---

## Prerequisites

### System Requirements

| Aspect | Minimum | Recommended |
|--------|---------|-------------|
| **CPU cores** | 4 | 8+ |
| **RAM** | 12 GB | 16–32 GB |
| **Storage** | 50 GB | 100+ GB SSD |
| **OS** | Ubuntu 22.04+ / WSL2 | Ubuntu 22.04 LTS / WSL2 |

### Software Requirements

```bash
# Check installed versions
python3 --version        # Must be 3.12+
node --version           # Must be 18+
npm --version            # Must be 9+
git --version            # Must be 2.40+
```

Install missing dependencies:

```bash
# Ubuntu 22.04
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
                   nodejs npm git build-essential libssl-dev
```

### Network / Hostname Setup

Single-host requires stable loopback aliases. This is configured automatically during provisioning, but your machine must support it:

- **Linux:** Native loopback aliases (automatic)
- **macOS:** Native loopback aliases (automatic)
- **WSL2:** Automatic via `setup-loopback-aliases` role

No manual `/etc/hosts` editing needed; Ansible handles all alias setup.

---

## Step 1: Clone Repository

```bash
cd ~/
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
git checkout Dev_new_gui  # Always use Dev_new_gui for latest optimizations
```

---

## Step 2: Create Environment File

Create `/etc/autobot/.env` with single-host configuration:

```bash
sudo mkdir -p /etc/autobot
sudo touch /etc/autobot/.env
sudo chmod 640 /etc/autobot/.env
```

Edit the file (use `sudo nano` or `sudo vim`):

```bash
# Single-host loopback addressing (Issue #2953, #768)
AUTOBOT_BACKEND_HOST=127.0.0.3
AUTOBOT_FRONTEND_HOST=127.0.0.1
AUTOBOT_REDIS_HOST=127.0.0.7
AUTOBOT_CHROMADB_HOST=127.0.0.7
AUTOBOT_AI_STACK_HOST=127.0.0.6
AUTOBOT_NPU_WORKER_HOST=127.0.0.5
AUTOBOT_BROWSER_SERVICE_HOST=127.0.0.4
AUTOBOT_OLLAMA_HOST=127.0.0.6
AUTOBOT_SLM_HOST=127.0.0.1

# Port assignments (standard)
AUTOBOT_BACKEND_PORT=8001
AUTOBOT_FRONTEND_PORT=5173
AUTOBOT_REDIS_PORT=6379
AUTOBOT_CHROMADB_PORT=8100
AUTOBOT_AI_STACK_PORT=8080
AUTOBOT_NPU_WORKER_PORT=8081
AUTOBOT_BROWSER_SERVICE_PORT=3000
AUTOBOT_OLLAMA_PORT=11434
AUTOBOT_SLM_PORT=8000

# LLM Model Settings
AUTOBOT_DEFAULT_LLM_MODEL=qwen3.5:9b
AUTOBOT_DEFAULT_EMBEDDING_MODEL=nomic-embed-text:latest
AUTOBOT_ROUTING_MODEL=llama3.2:1b
AUTOBOT_CLASSIFICATION_MODEL=gemma2:2b
AUTOBOT_LIGHT_PROCESSING_MODEL=phi3:mini
AUTOBOT_INSTRUCTION_MODEL=mistral:7b-instruct
AUTOBOT_SYSTEM_MODEL=dolphin-llama3:8b

# Optional: Timeouts (seconds)
AUTOBOT_HTTP_TIMEOUT=30
AUTOBOT_LLM_TIMEOUT=120
```

**Note:** Do NOT modify IPs after provisioning without re-running the role setup.

**Updated (MVA-2418):** The `AUTOBOT_BACKEND_HOST` variable is now automatically configured by the Ansible backend role in `/etc/autobot/autobot-backend.env`. If using Ansible for deployment, this variable no longer needs manual configuration in the global `.env` file — it will be set from the `backend_host` Ansible variable (defaults to `127.0.0.1`, or `0.0.0.0` on WSL2).

---

## Step 3: Create Ansible Inventory for Single-Host

Create `autobot-slm-backend/ansible/inventory/localhost.yml`:

```yaml
---
# Single-host co-located deployment
# All roles run on localhost with loopback aliases (127.0.0.x)
# Issue #2961: Single-host deployment runbook

all:
  hosts:
    localhost:
      ansible_connection: local
      ansible_user: "{{ ansible_user_id }}"
      ansible_become: yes
      ansible_become_method: sudo

  children:
    # Single-host: all groups map to localhost
    slm:
      hosts:
        localhost:

    backend:
      hosts:
        localhost:

    frontend:
      hosts:
        localhost:

    database:
      hosts:
        localhost:

    aiml:
      hosts:
        localhost:

    browser:
      hosts:
        localhost:

    npu_workers:
      hosts:
        localhost:
```

---

## Step 4: Set Up Loopback Aliases

Single-host deployment requires loopback aliases so services can address each other by stable IPs.
Set these up before provisioning:

```bash
# Add loopback aliases (one-time setup)
sudo ip addr add 127.0.0.3/8 dev lo  # backend
sudo ip addr add 127.0.0.4/8 dev lo  # browser
sudo ip addr add 127.0.0.5/8 dev lo  # npu-worker
sudo ip addr add 127.0.0.6/8 dev lo  # ai-stack
sudo ip addr add 127.0.0.7/8 dev lo  # redis
```

**Optional: Make loopback aliases persistent across reboots**

Edit `/etc/rc.local` (create if missing):

```bash
#!/bin/bash
ip addr add 127.0.0.3/8 dev lo 2>/dev/null
ip addr add 127.0.0.4/8 dev lo 2>/dev/null
ip addr add 127.0.0.5/8 dev lo 2>/dev/null
ip addr add 127.0.0.6/8 dev lo 2>/dev/null
ip addr add 127.0.0.7/8 dev lo 2>/dev/null
exit 0
```

Then make it executable:
```bash
sudo chmod +x /etc/rc.local
```

Verify aliases are created:

```bash
ip addr show lo | grep "127.0.0"
```

Expected output:
```
inet 127.0.0.3/8 scope host lo   # backend
inet 127.0.0.4/8 scope host lo   # browser
inet 127.0.0.5/8 scope host lo   # npu
inet 127.0.0.6/8 scope host lo   # ai-stack
inet 127.0.0.7/8 scope host lo   # redis
```

See [IP_ADDRESSING_SCHEME.md](../api/IP_ADDRESSING_SCHEME.md) for networking details.

---

## Step 5: Run Role Provisioning

```bash
cd autobot-slm-backend/ansible

# Provision all roles for single-host
ansible-playbook \
  -i inventory/localhost.yml \
  -e "ansible_python_interpreter=/usr/bin/python3.12" \
  playbooks/provision-fleet-roles.yml
```

This runs 6 provisioning phases:
1. **Phase 1: System dependencies** (apt/npm packages, Python 3.12)
2. **Phase 2: Service setup** (create systemd units, directories, logging)
3. **Phase 3: Code sync** (rsync application code from working directory)
4. **Phase 4: Secrets** (generate TLS certs, Redis auth, API tokens)
5. **Phase 5: Configuration** (render Ansible templates to live locations)
6. **Phase 6: Service start** (enable and start all systemd units)

**Expected duration:** 5–10 minutes on first run.

---

## Step 6: Verify Installation

### 6.1: Check Service Status

```bash
# All services should be active (running)
sudo systemctl status autobot-backend
sudo systemctl status autobot-frontend
sudo systemctl status autobot-redis
sudo systemctl status autobot-chromadb
sudo systemctl status autobot-ai-stack
sudo systemctl status autobot-browser
# NPU worker only on systems with NPU hardware
# sudo systemctl status autobot-npu-worker
```

### 6.2: Verify Network Connectivity

```bash
# Test backend API
curl -k https://127.0.0.3:8001/health
# Expected: 200 OK + JSON health status

# Test frontend
curl -k https://127.0.0.1/
# Expected: 200 OK + HTML index

# Test Redis
redis-cli -h 127.0.0.7 ping
# Expected: PONG

# Test ChromaDB
curl http://127.0.0.7:8100/api/v1/heartbeat
# Expected: 200 OK
```

### 6.3: Access Web UI

Open browser to:
```
http://localhost:5173      # Development frontend (auto-reload)
https://localhost          # Production frontend (nginx)
http://localhost:8001/docs # API documentation
```

### 6.4: Check Logs

```bash
# Backend service logs
sudo journalctl -u autobot-backend -f

# All AutoBot service logs
sudo tail -f /var/log/autobot/*.log
```

---

## Step 7: Configure SSH / Remote Access (Optional)

For remote access to the single-host machine:

```bash
# Test SSH access
ssh -i ~/.ssh/id_ed25519 -l $USER localhost

# For services behind HTTPS with self-signed certs, use:
curl -k --cacert /etc/autobot/ca.crt https://127.0.0.3:8443/health
```

---

## Step 8: Post-Deployment Configuration

### Set Up Knowledge Base (Optional)

```bash
# Create initial KB database
curl -X POST https://127.0.0.3:8001/api/knowledge/init \
  -H "Authorization: Bearer $(cat /etc/autobot/api-token.txt)" \
  -H "Content-Type: application/json" \
  -d '{"mode": "single-host"}'
```

### Configure User Credentials

See `docs/guides/USER_SETUP.md` for creating first admin user and API credentials.

### Enable VNC Remote Desktop (Optional)

Single-host includes VNC for remote desktop access:

```bash
# VNC is available at https://127.0.0.3:6080 (via noVNC proxy)
# Or connect with VNC client to 127.0.0.3:5900
```

---

## Troubleshooting

| Issue | Symptoms | Fix |
|-------|----------|-----|
| **Services don't start** | `systemctl status autobot-*` shows failed | Check logs: `sudo journalctl -u autobot-backend` |
| **Loopback aliases missing** | `ip addr` doesn't show 127.0.0.x | Re-run Step 4: `setup-loopback-aliases.yml` |
| **Backend can't reach Redis** | Backend logs show "Connection refused 127.0.0.7:6379" | Check Redis: `redis-cli -h 127.0.0.7 ping` |
| **Frontend shows CORS errors** | Browser console errors accessing `/api/*` | Verify backend is running: `curl https://127.0.0.3:8001/health` |
| **Permission denied on .env file** | Provisioning fails reading `/etc/autobot/.env` | Check permissions: `sudo chmod 640 /etc/autobot/.env` |
| **Port conflicts** | Systemd service fails to bind port | Check if another process is using the port: `sudo ss -tlnp \| grep 8001` |
| **Ansible permission errors** | Playbook fails with "permission denied" | Run with `-K` flag for password prompt or add sudo NOPASSWD rule |

### Debug Tips

```bash
# See all running AutoBot services
ps aux | grep autobot

# Check disk usage
df -h /opt/autobot

# Monitor service startup
sudo journalctl -u autobot-backend -f --since "5 min ago"

# Reload a single service without stopping others
sudo systemctl restart autobot-backend

# Check if loopback aliases are persistent across reboot
sudo reboot
ip addr show lo  # Verify aliases still exist
```

---

## Updating Code

After pulling new code from the repository:

```bash
cd autobot-slm-backend/ansible

# Re-sync code and restart services
ansible-playbook \
  -i inventory/localhost.yml \
  -e "ansible_python_interpreter=/usr/bin/python3.12" \
  playbooks/provision-fleet-roles.yml \
  --tags "code,services"
```

---

## Scaling to Distributed (Multi-VM) Later

To migrate from single-host to distributed deployment:

1. Create separate VMs for each role
2. Update `/etc/autobot/.env` with real IPs (e.g., `AUTOBOT_BACKEND_HOST=172.16.168.10`)
3. Create `inventory/fleet.yml` with host groups
4. Run provisioning against new inventory:
   ```bash
   ansible-playbook \
     -i inventory/fleet.yml \
     playbooks/provision-fleet-roles.yml
   ```
5. Services automatically detect new IPs and reconfigure

See [DEPLOY_NEW_NODE.md](DEPLOY_NEW_NODE.md) for distributed setup details.

---

## Related Documentation

- [VM_ROLES.md](../architecture/VM_ROLES.md) — role definitions and architecture
- [comprehensive_deployment_guide.md](../deployment/comprehensive_deployment_guide.md) — full deployment options
- [DEPLOY_NEW_NODE.md](DEPLOY_NEW_NODE.md) — multi-VM (distributed) deployment
- [CODE_UPDATE.md](CODE_UPDATE.md) — updating code without reprovisioning
- [EMERGENCY_RECOVERY.md](EMERGENCY_RECOVERY.md) — recovery procedures

---

## Support

For issues or questions:

1. **Check logs first:** `sudo journalctl -u autobot-* -f`
2. **Review docs:** [docs/troubleshooting/](../troubleshooting/)
3. **File issue:** [GitHub Issues](https://github.com/mrveiss/AutoBot-AI/issues) with logs attached
