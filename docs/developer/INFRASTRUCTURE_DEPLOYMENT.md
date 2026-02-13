# Infrastructure & Deployment Guide

**Status**: MANDATORY - Local-only development with immediate sync

This guide provides detailed instructions for AutoBot's distributed VM infrastructure and deployment workflows.

> **MANDATORY RULE**: NEVER edit code directly on remote VMs - Edit locally, sync immediately

---

## SSH Authentication

### SSH Key Setup

**Key Location**: `~/.ssh/autobot_key` (4096-bit RSA)

**Configured for all 5 VMs**:

- `frontend` (172.16.168.21)
- `npu-worker` (172.16.168.22)
- `redis` (172.16.168.23)
- `ai-stack` (172.16.168.24)
- `browser` (172.16.168.25)

### Verify SSH Access

```bash
# Test connection to all VMs
for vm in frontend npu-worker redis ai-stack browser; do
    echo "Testing $vm..."
    ssh -i ~/.ssh/autobot_key autobot@172.16.168.{21..25} "hostname" 2>/dev/null
done

# Test specific VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "echo 'Frontend VM connected'"
```

### SSH Configuration

Add to `~/.ssh/config` for easier access:

```ssh-config
# AutoBot VMs
Host autobot-frontend
    HostName 172.16.168.21
    User autobot
    IdentityFile ~/.ssh/autobot_key
    StrictHostKeyChecking no

Host autobot-npu
    HostName 172.16.168.22
    User autobot
    IdentityFile ~/.ssh/autobot_key
    StrictHostKeyChecking no

Host autobot-redis
    HostName 172.16.168.23
    User autobot
    IdentityFile ~/.ssh/autobot_key
    StrictHostKeyChecking no

Host autobot-ai
    HostName 172.16.168.24
    User autobot
    IdentityFile ~/.ssh/autobot_key
    StrictHostKeyChecking no

Host autobot-browser
    HostName 172.16.168.25
    User autobot
    IdentityFile ~/.ssh/autobot_key
    StrictHostKeyChecking no
```

**Usage**:

```bash
# Now you can use short names
ssh autobot-frontend
ssh autobot-redis
```

---

## File Synchronization

### Sync Script

**Script Location**: `./infrastructure/shared/scripts/sync-to-vm.sh`

**Basic Usage**:

```bash
# Syntax
./infrastructure/shared/scripts/sync-to-vm.sh <vm-name> <local-path> <remote-path>

# Example: Sync frontend component to Frontend VM
./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-slm-frontend/src/components/Chat.vue /home/autobot/autobot-slm-frontend/src/components/Chat.vue

# Example: Sync entire directory
./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-slm-frontend/src/components/ /home/autobot/autobot-slm-frontend/src/components/
```

### Sync to All VMs

```bash
# Sync to ALL VMs at once
./infrastructure/shared/scripts/sync-to-vm.sh all scripts/setup.sh /home/autobot/scripts/

# Sync directory to all VMs
./infrastructure/shared/scripts/sync-to-vm.sh all autobot-user-backend/utils/ /home/autobot/autobot-user-backend/utils/
```

### Common Sync Patterns

**Sync frontend changes**:

```bash
# Single component
./infrastructure/shared/scripts/sync-to-vm.sh frontend \
    autobot-slm-frontend/src/components/ChatMessages.vue \
    /home/autobot/autobot-slm-frontend/src/components/ChatMessages.vue

# Entire components directory
./infrastructure/shared/scripts/sync-to-vm.sh frontend \
    autobot-slm-frontend/src/components/ \
    /home/autobot/autobot-slm-frontend/src/components/

# Full frontend rebuild
./infrastructure/shared/scripts/sync-to-vm.sh frontend \
    autobot-slm-frontend/ \
    /home/autobot/autobot-slm-frontend/
```

**Sync backend changes**:

```bash
# Single API file
./infrastructure/shared/scripts/sync-to-vm.sh all \
    autobot-user-autobot-user-backend/api/chat.py \
    /home/autobot/autobot-user-autobot-user-backend/api/chat.py

# Entire backend directory
./infrastructure/shared/scripts/sync-to-vm.sh all \
    autobot-user-backend/ \
    /home/autobot/autobot-user-backend/
```

**Sync configuration**:

```bash
# Environment file (be careful with secrets!)
./infrastructure/shared/scripts/sync-to-vm.sh all \
    .env.example \
    /home/autobot/.env.example

# Config file
./infrastructure/shared/scripts/sync-to-vm.sh all \
    infrastructure/shared/config/config.yaml \
    /home/autobot/config/config.yaml
```

### Sync Shortcuts

**Use the convenience script**:

```bash
# Frontend sync (uses sync-to-vm.sh internally)
./sync-frontend.sh

# Equivalent to:
./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-slm-frontend/ /home/autobot/autobot-slm-frontend/
```

---

## MANDATORY: Local-Only Development

### The Rule

**NEVER edit code directly on remote VMs (172.16.168.21-25) - ZERO TOLERANCE**

### Required Workflow

1. **Edit locally** in `/home/kali/Desktop/AutoBot/`
2. **Sync immediately** using sync scripts
3. **Never skip sync** - remote machines must stay synchronized

### Why This Is Critical

| Problem | Impact |
|---------|--------|
| **No version control on VMs** | Changes completely untracked |
| **No backup system** | Remote edits never saved or recorded |
| **VMs are ephemeral** | Can be reinstalled anytime leading to PERMANENT WORK LOSS |
| **No recovery mechanism** | Cannot track or recover remote changes |

### What This Means

**CORRECT workflow**:

```bash
# Step 1: Edit locally
vim /home/kali/Desktop/AutoBot/autobot-user-autobot-user-backend/api/chat.py

# Step 2: Sync immediately
./infrastructure/shared/scripts/sync-to-vm.sh all autobot-user-autobot-user-backend/api/chat.py /home/autobot/autobot-user-autobot-user-backend/api/chat.py

# Step 3: Commit changes (version control)
git add autobot-user-autobot-user-backend/api/chat.py
git commit -m "Update chat API"
```

**FORBIDDEN workflow**:

```bash
# NEVER DO THIS - Direct editing on VM
ssh autobot@172.16.168.21
vim /home/autobot/autobot-user-autobot-user-backend/api/chat.py  # PERMANENT WORK LOSS RISK!
```

### Enforcement

- **Pre-commit checks**: Verify no unsynced changes exist
- **Code review**: Check for evidence of direct VM edits
- **Periodic VM reinstalls**: Prove resilience (all work is local)

---

## Network Configuration

### Service Binding Rules

**CORRECT - Bind to all interfaces**:

```python
# Backend service
app.run(host="0.0.0.0", port=8001)  # Accessible from network

# Frontend development server
vite --host 0.0.0.0 --port 5173  # Accessible from network
```

**FORBIDDEN - Localhost binding**:

```python
# NOT accessible from remote VMs
app.run(host="localhost", port=8001)
app.run(host="127.0.0.1", port=8001)

# NOT accessible from remote VMs
vite --host localhost --port 5173
```

### Service Access Patterns

**Backend on Main Machine** (172.16.168.20):

```python
# Binds to all interfaces
uvicorn main:app --host 0.0.0.0 --port 8001

# Accessed from frontend VM:
# http://172.16.168.20:8001/api/chat
```

**Frontend on VM1** (172.16.168.21):

```bash
# Binds to all interfaces
npm run dev -- --host 0.0.0.0 --port 5173

# Accessed from browser:
# http://172.16.168.21:5173
```

**Redis on VM3** (172.16.168.23):

```bash
# Configure Redis to bind to all interfaces
# In /etc/redis/redis.conf:
bind 0.0.0.0

# Accessed from any VM:
# redis-cli -h 172.16.168.23 -p 6379
```

### Inter-VM Communication

**Use actual IPs** for communication between VMs:

```python
# CORRECT - Use NetworkConstants
from autobot_shared.network_constants import NetworkConstants

backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}/api/chat"
# Result: http://172.16.168.20:8001/api/chat

redis_host = NetworkConstants.REDIS_VM_IP
# Result: 172.16.168.23

# WRONG - Using localhost (won't work from remote VMs)
backend_url = "http://localhost:8001/api/chat"
redis_host = "localhost"
```

### Network Testing

**Test connectivity between VMs**:

```bash
# From main machine, test backend accessibility
curl http://172.16.168.20:8001/api/health

# From frontend VM, test backend accessibility
ssh autobot@172.16.168.21 "curl http://172.16.168.20:8001/api/health"

# From any VM, test Redis
redis-cli -h 172.16.168.23 ping
# Should return: PONG

# Test all VMs from main machine
for ip in 20 21 22 23 24 25; do
    echo "Testing 172.16.168.$ip..."
    ping -c 1 172.16.168.$ip
done
```

---

## VM Infrastructure Overview

### Service Layout

| VM | IP:Port | Service | Purpose |
|----|---------|---------|---------|
| **Main (WSL)** | 172.16.168.20:8001 | Backend API | FastAPI backend, business logic |
| **Main (WSL)** | 172.16.168.20:6080 | VNC Desktop | noVNC web-based terminal |
| **VM1 Frontend** | 172.16.168.21:5173 | Web UI | Vue.js frontend (SINGLE SERVER) |
| **VM2 NPU Worker** | 172.16.168.22:8081 | AI Acceleration | Hardware NPU for AI tasks |
| **VM3 Redis** | 172.16.168.23:6379 | Data Layer | Redis database, cache, queues |
| **VM4 AI Stack** | 172.16.168.24:8080 | AI Processing | LLM inference, AI services |
| **VM5 Browser** | 172.16.168.25:3000 | Web Automation | Playwright browser automation |

### Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────┐
│                     Main Machine (WSL)                       │
│                    172.16.168.20                             │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │ Backend API  │  │ VNC Desktop  │                         │
│  │   :8001      │  │   :6080      │                         │
│  └──────────────┘  └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼─────────┐ ┌──────▼──────────┐ ┌─────▼──────────┐
│  VM1: Frontend  │ │  VM3: Redis     │ │  VM4: AI Stack │
│  172.16.168.21  │ │  172.16.168.23  │ │  172.16.168.24 │
│  Port: 5173     │ │  Port: 6379     │ │  Port: 8080    │
└─────────────────┘ └─────────────────┘ └────────────────┘
        │                   │                   │
┌───────▼─────────┐ ┌──────▼──────────┐
│ VM2: NPU Worker │ │ VM5: Browser    │
│ 172.16.168.22   │ │ 172.16.168.25   │
│ Port: 8081      │ │ Port: 3000      │
└─────────────────┘ └─────────────────┘
```

---

## Deployment Workflows

### Development Deployment

**Daily development workflow**:

```bash
# 1. Start AutoBot services (main machine)
scripts/start-services.sh start
# Or: sudo systemctl start autobot-backend

# 2. Make code changes locally
vim /home/kali/Desktop/AutoBot/autobot-user-backend/api/chat.py

# 3. Sync changes to VMs (if needed)
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-backend/ /opt/autobot/autobot-user-backend/

# 4. Restart affected services
scripts/start-services.sh restart backend
# Or: sudo systemctl restart autobot-backend

# 5. View logs
scripts/start-services.sh logs backend
# Or: journalctl -u autobot-backend -f
```

**See**: [Service Management Guide](SERVICE_MANAGEMENT.md) for complete documentation.

### Production Deployment

**Production deployment workflow**:

```bash
# 1. Test locally first
scripts/start-services.sh start
# Verify everything works

# 2. Commit changes
git add .
git commit -m "Production-ready changes"

# 3. Deploy via Ansible
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-native-services.yml

# 4. Verify health checks
curl -k https://172.16.168.20:8443/api/health
curl https://172.16.168.21

# 5. Monitor via SLM GUI
# Visit: https://172.16.168.19/orchestration
```

**See**: [Service Management Guide](SERVICE_MANAGEMENT.md) for Ansible deployment details.

### Rolling Updates

**Update one VM at a time using Ansible**:

```bash
# Update specific node via Ansible
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-native-services.yml --limit 172.16.168.21 --tags frontend

# Wait for health check
curl https://172.16.168.21

# Update NPU Worker VM
ansible-playbook playbooks/deploy-native-services.yml --limit 172.16.168.22 --tags npu

# Or use SLM GUI for rolling updates
# Visit: https://172.16.168.19/orchestration
# Select node → Deploy → Monitor progress
```

**Manual alternative (not recommended)**:

```bash
# Update Frontend VM
./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-slm-frontend/ /opt/autobot/autobot-slm-frontend/
ssh autobot@172.16.168.21 "sudo systemctl restart autobot-frontend"
```

---

## VM Management

### Check VM Status

```bash
# Check all VMs are reachable
for ip in 20 21 22 23 24 25; do
    echo "Checking 172.16.168.$ip..."
    ping -c 1 172.16.168.$ip && echo "UP" || echo "DOWN"
done

# Check services on each VM
ssh autobot@172.16.168.21 "systemctl status frontend"
ssh autobot@172.16.168.23 "systemctl status redis"
```

### Restart Services

```bash
# Main machine services (CLI wrapper)
scripts/start-services.sh restart backend
scripts/start-services.sh restart celery

# Or direct systemctl
sudo systemctl restart autobot-backend
sudo systemctl restart autobot-celery

# Remote VM services (via SSH)
ssh autobot@172.16.168.21 "sudo systemctl restart autobot-frontend"
ssh autobot@172.16.168.23 "sudo systemctl restart redis-stack-server"

# Or use SLM Orchestration GUI
# Visit: https://172.16.168.19/orchestration
```

### View Logs

```bash
# Main machine - Backend logs (systemd)
scripts/start-services.sh logs backend
# Or: journalctl -u autobot-backend -f

# Main machine - Celery logs
journalctl -u autobot-celery -f

# Remote VMs - Frontend logs
ssh autobot@172.16.168.21 "journalctl -u autobot-frontend -f"

# Remote VMs - Redis logs
ssh autobot@172.16.168.23 "journalctl -u redis-stack-server -f"

# Or use SLM GUI for log viewing
# Visit: https://172.16.168.19/orchestration → Select service → Logs
```

---

## Infrastructure Directory Structure

The infrastructure folder uses a per-role organization:

```text
infrastructure/
├── autobot-user-backend/       # User backend infra (docker, tests, config, scripts, templates)
├── autobot-user-frontend/      # User frontend infra
├── autobot-slm-backend/        # SLM backend infra
├── autobot-slm-frontend/       # SLM frontend infra
├── autobot-npu-worker/         # NPU worker infra
├── autobot-browser-worker/     # Browser worker infra
└── shared/                     # Shared infrastructure
    ├── scripts/                # Common utilities, sync scripts
    ├── certs/                  # Certificate management
    ├── config/                 # Shared configurations
    ├── docker/                 # Shared docker resources
    ├── mcp/                    # MCP server configs
    ├── tools/                  # Development tools
    ├── tests/                  # Shared test utilities
    └── analysis/               # Analysis tools
```

---

## Troubleshooting

### Sync Script Not Working

**Issue**: `sync-to-vm.sh` fails with permission denied

**Solution**:

```bash
# Make script executable
chmod +x infrastructure/shared/scripts/sync-to-vm.sh

# Verify SSH key permissions
chmod 600 ~/.ssh/autobot_key

# Test SSH connection
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "echo 'Connected'"
```

### Services Not Accessible

**Issue**: Can't reach service from remote VM

**Solution**:

```bash
# 1. Verify service is running
ssh autobot@172.16.168.21 "ps aux | grep node"  # Frontend
ps aux | grep uvicorn  # Backend (main machine)

# 2. Verify service is binding to 0.0.0.0
netstat -tulpn | grep 8001  # Should show 0.0.0.0:8001

# 3. Test from source VM
ssh autobot@172.16.168.21 "curl http://172.16.168.20:8001/api/health"
```

### VM Out of Sync

**Issue**: Code changes not reflected on VM

**Solution**:

```bash
# Recommended: Full redeploy via Ansible
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-native-services.yml

# Or manual re-sync (not recommended)
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-backend/ /opt/autobot/autobot-user-backend/
sudo systemctl restart autobot-backend

# Verify sync
ssh autobot@172.16.168.20 "md5sum /opt/autobot/autobot-user-backend/api/chat.py"
md5sum /home/kali/Desktop/AutoBot/autobot-user-backend/api/chat.py
# Hashes should match
```

---

## Related Documentation

- **Network Constants**: `autobot-shared/network_constants.py`
- **Setup Guide**: `docs/developer/PHASE_5_DEVELOPER_SETUP.md`
- **Hardcoding Prevention**: `docs/developer/HARDCODING_PREVENTION.md`
- **Redis Client Usage**: `docs/developer/REDIS_CLIENT_USAGE.md`

---

## Summary Checklist

**Before deploying**:

- [ ] All changes committed to git (local version control)
- [ ] Services bind to `0.0.0.0` (not localhost)
- [ ] Using `NetworkConstants` for IPs/ports (not hardcoded)
- [ ] Tested locally first (`bash run_autobot.sh --dev`)
- [ ] Synced to VMs (`./infrastructure/shared/scripts/sync-to-vm.sh`)
- [ ] Health checks pass on all services

**Development workflow**:

- [ ] Edit locally in `/home/kali/Desktop/AutoBot/`
- [ ] Sync immediately after changes
- [ ] NEVER edit directly on VMs
- [ ] Test changes on target VM
- [ ] Commit to git

**Avoid**:

- [ ] No direct edits on remote VMs (172.16.168.21-25)
- [ ] No binding to localhost/127.0.0.1
- [ ] No hardcoded IPs/ports in code
- [ ] No skipping sync after changes
- [ ] No untracked changes on VMs

---
