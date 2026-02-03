# Infrastructure & Deployment Guide

**Status**: 🚨 MANDATORY - Local-only development with immediate sync

This guide provides detailed instructions for AutoBot's distributed VM infrastructure and deployment workflows.

> **⚠️ MANDATORY RULE**: NEVER edit code directly on remote VMs - Edit locally, sync immediately

---

## 🔑 SSH Authentication

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

## 🔄 File Synchronization

### Sync Script

**Script Location**: `./scripts/utilities/sync-to-vm.sh`

**Basic Usage**:
```bash
# Syntax
./scripts/utilities/sync-to-vm.sh <vm-name> <local-path> <remote-path>

# Example: Sync frontend component to Frontend VM
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/components/Chat.vue /home/autobot/autobot-vue/src/components/Chat.vue

# Example: Sync entire directory
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/components/ /home/autobot/autobot-vue/src/components/
```

### Sync to All VMs

```bash
# Sync to ALL VMs at once
./scripts/utilities/sync-to-vm.sh all scripts/setup.sh /home/autobot/scripts/

# Sync directory to all VMs
./scripts/utilities/sync-to-vm.sh all src/utils/ /home/autobot/src/utils/
```

### Common Sync Patterns

**Sync frontend changes**:
```bash
# Single component
./scripts/utilities/sync-to-vm.sh frontend \
    autobot-vue/src/components/ChatMessages.vue \
    /home/autobot/autobot-vue/src/components/ChatMessages.vue

# Entire components directory
./scripts/utilities/sync-to-vm.sh frontend \
    autobot-vue/src/components/ \
    /home/autobot/autobot-vue/src/components/

# Full frontend rebuild
./scripts/utilities/sync-to-vm.sh frontend \
    autobot-vue/ \
    /home/autobot/autobot-vue/
```

**Sync backend changes**:
```bash
# Single API file
./scripts/utilities/sync-to-vm.sh all \
    backend/api/chat.py \
    /home/autobot/backend/api/chat.py

# Entire backend directory
./scripts/utilities/sync-to-vm.sh all \
    backend/ \
    /home/autobot/backend/
```

**Sync configuration**:
```bash
# Environment file (be careful with secrets!)
./scripts/utilities/sync-to-vm.sh all \
    .env.example \
    /home/autobot/.env.example

# Config file
./scripts/utilities/sync-to-vm.sh all \
    config/config.yaml \
    /home/autobot/config/config.yaml
```

### Sync Shortcuts

**Use the convenience script**:
```bash
# Frontend sync (uses sync-to-vm.sh internally)
./sync-frontend.sh

# Equivalent to:
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/ /home/autobot/autobot-vue/
```

---

## 🚨 MANDATORY: Local-Only Development

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
| **VMs are ephemeral** | Can be reinstalled anytime → **PERMANENT WORK LOSS** |
| **No recovery mechanism** | Cannot track or recover remote changes |

### What This Means

**✅ CORRECT workflow**:
```bash
# Step 1: Edit locally
vim /home/kali/Desktop/AutoBot/backend/api/chat.py

# Step 2: Sync immediately
./scripts/utilities/sync-to-vm.sh all backend/api/chat.py /home/autobot/backend/api/chat.py

# Step 3: Commit changes (version control)
git add backend/api/chat.py
git commit -m "Update chat API"
```

**❌ FORBIDDEN workflow**:
```bash
# NEVER DO THIS - Direct editing on VM
ssh autobot@172.16.168.21
vim /home/autobot/backend/api/chat.py  # ❌ PERMANENT WORK LOSS RISK!
```

### Enforcement

- **Pre-commit checks**: Verify no unsynced changes exist
- **Code review**: Check for evidence of direct VM edits
- **Periodic VM reinstalls**: Prove resilience (all work is local)

---

## 🌐 Network Configuration

### Service Binding Rules

**✅ CORRECT - Bind to all interfaces**:
```python
# Backend service
app.run(host="0.0.0.0", port=8001)  # Accessible from network

# Frontend development server
vite --host 0.0.0.0 --port 5173  # Accessible from network
```

**❌ FORBIDDEN - Localhost binding**:
```python
# ❌ NOT accessible from remote VMs
app.run(host="localhost", port=8001)
app.run(host="127.0.0.1", port=8001)

# ❌ NOT accessible from remote VMs
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
# ✅ CORRECT - Use NetworkConstants
from src.constants.network_constants import NetworkConstants

backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}/api/chat"
# Result: http://172.16.168.20:8001/api/chat

redis_host = NetworkConstants.REDIS_VM_IP
# Result: 172.16.168.23

# ❌ WRONG - Using localhost (won't work from remote VMs)
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

## 🏗️ VM Infrastructure Overview

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

```
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

## 🚀 Deployment Workflows

### Development Deployment

**Daily development workflow**:
```bash
# 1. Start AutoBot services (main machine)
bash run_autobot.sh --dev

# 2. Make code changes locally
vim /home/kali/Desktop/AutoBot/backend/api/chat.py

# 3. Sync changes to VMs
./scripts/utilities/sync-to-vm.sh all backend/api/chat.py /home/autobot/backend/api/chat.py

# 4. Restart affected services
ssh autobot@172.16.168.21 "cd /home/autobot && bash run_autobot.sh --restart"
```

### Production Deployment

**Production deployment workflow**:
```bash
# 1. Test locally first
bash run_autobot.sh --dev
# Verify everything works

# 2. Commit changes
git add .
git commit -m "Production-ready changes"

# 3. Sync to all VMs
./scripts/utilities/sync-to-vm.sh all ./ /home/autobot/

# 4. Start in production mode
bash run_autobot.sh --prod

# 5. Verify health checks
curl http://172.16.168.20:8001/api/health
curl http://172.16.168.21:5173
```

### Rolling Updates

**Update one VM at a time**:
```bash
# Update Frontend VM
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/ /home/autobot/autobot-vue/
ssh autobot@172.16.168.21 "cd /home/autobot && bash run_autobot.sh --restart"

# Wait for health check
curl http://172.16.168.21:5173

# Update NPU Worker VM
./scripts/utilities/sync-to-vm.sh npu-worker src/ /home/autobot/src/
ssh autobot@172.16.168.22 "cd /home/autobot && bash run_autobot.sh --restart"

# Continue for other VMs...
```

---

## 🔧 VM Management

### Check VM Status

```bash
# Check all VMs are reachable
for ip in 20 21 22 23 24 25; do
    echo "Checking 172.16.168.$ip..."
    ping -c 1 172.16.168.$ip && echo "✅ UP" || echo "❌ DOWN"
done

# Check services on each VM
ssh autobot@172.16.168.21 "systemctl status frontend"
ssh autobot@172.16.168.23 "systemctl status redis"
```

### Restart Services

```bash
# Restart frontend service
ssh autobot@172.16.168.21 "cd /home/autobot && bash run_autobot.sh --restart"

# Restart Redis
ssh autobot@172.16.168.23 "sudo systemctl restart redis"

# Restart all services on main machine
bash run_autobot.sh --restart
```

### View Logs

```bash
# Backend logs (main machine)
tail -f logs/backend.log

# Frontend logs (VM1)
ssh autobot@172.16.168.21 "tail -f /home/autobot/logs/frontend.log"

# Redis logs (VM3)
ssh autobot@172.16.168.23 "sudo tail -f /var/log/redis/redis-server.log"
```

---

## 🐛 Troubleshooting

### Sync Script Not Working

**Issue**: `sync-to-vm.sh` fails with permission denied

**Solution**:
```bash
# Make script executable
chmod +x scripts/utilities/sync-to-vm.sh

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
# Full re-sync of entire project
./scripts/utilities/sync-to-vm.sh all ./ /home/autobot/

# Restart services
ssh autobot@172.16.168.21 "cd /home/autobot && bash run_autobot.sh --restart"

# Verify sync
ssh autobot@172.16.168.21 "md5sum /home/autobot/backend/api/chat.py"
md5sum /home/kali/Desktop/AutoBot/backend/api/chat.py
# Hashes should match
```

---

## 📚 Related Documentation

- **Network Constants**: `src/constants/network_constants.py`
- **Setup Guide**: `docs/developer/PHASE_5_DEVELOPER_SETUP.md`
- **Hardcoding Prevention**: `docs/developer/HARDCODING_PREVENTION.md`
- **Redis Client Usage**: `docs/developer/REDIS_CLIENT_USAGE.md`

---

## 🎯 Summary Checklist

**Before deploying**:
- [ ] All changes committed to git (local version control)
- [ ] Services bind to `0.0.0.0` (not localhost)
- [ ] Using `NetworkConstants` for IPs/ports (not hardcoded)
- [ ] Tested locally first (`bash run_autobot.sh --dev`)
- [ ] Synced to VMs (`./scripts/utilities/sync-to-vm.sh`)
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
