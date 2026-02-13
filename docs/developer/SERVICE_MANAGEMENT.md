# AutoBot Service Management Guide

> **Last Updated:** 2026-02-13
> **Related Issues:** #862, #863
> **Deprecation Notice:** `run_autobot.sh` is deprecated. Use the methods described in this guide.

---

## Overview

AutoBot uses **SLM (System Lifecycle Manager) orchestration** and **systemd** for all service management across the distributed fleet. This provides:

- ✅ Single source of truth for all services
- ✅ Consistent configuration across dev and production
- ✅ Web GUI for visual monitoring
- ✅ Standard systemd tooling for CLI operations

## Service Management Methods

### Method 1: SLM Orchestration GUI (Recommended)

**Best for:** Visual monitoring, fleet-wide operations, production management

**Access:** https://172.16.168.19/orchestration

**Features:**
- Start/stop/restart all services
- Real-time health monitoring
- Service logs viewer
- Bulk operations across fleet
- Service dependency visualization

**Usage:**
1. Open https://172.16.168.19/orchestration in browser
2. Navigate to "Services" tab
3. Select node (e.g., "Main - 172.16.168.20")
4. Click service action buttons (Start/Stop/Restart)
5. View logs by clicking "Logs" button

### Method 2: CLI Wrapper Script

**Best for:** Developers who prefer terminal commands

**Command:** `scripts/start-services.sh`

**Usage:**
```bash
# Start all local services
scripts/start-services.sh start

# Start specific service
scripts/start-services.sh start backend

# Stop services
scripts/start-services.sh stop backend

# Restart services
scripts/start-services.sh restart all

# Check status
scripts/start-services.sh status

# Follow logs
scripts/start-services.sh logs backend

# Open SLM GUI in browser
scripts/start-services.sh gui

# Show help
scripts/start-services.sh --help
```

### Method 3: Direct systemctl Commands

**Best for:** Advanced debugging, automation scripts

**Available Services:**

| Service | Description | Default Port |
|---------|-------------|--------------|
| `autobot-backend` | FastAPI backend API | 8443 (HTTPS) |
| `autobot-celery` | Celery worker (background tasks) | N/A |
| `redis-stack-server` | Redis database | 6379 |
| `ollama` | Ollama LLM service | 11434 |
| `autobot-frontend` | Vue.js frontend (VM .21) | 443 (nginx) |
| `autobot-npu-worker` | NPU acceleration (VM .22) | 8081 |
| `playwright` | Browser automation (VM .25) | 3000 |

**Common Commands:**
```bash
# Start service
sudo systemctl start autobot-backend

# Stop service
sudo systemctl stop autobot-backend

# Restart service
sudo systemctl restart autobot-backend

# Check status
systemctl status autobot-backend

# Enable auto-start on boot
sudo systemctl enable autobot-backend

# Disable auto-start
sudo systemctl disable autobot-backend

# View logs (last 100 lines)
journalctl -u autobot-backend -n 100

# Follow logs (live)
journalctl -u autobot-backend -f

# View logs for specific time range
journalctl -u autobot-backend --since "1 hour ago"

# View logs with priority
journalctl -u autobot-backend -p err  # Only errors
```

---

## Common Tasks

### Starting the Backend for Development

**Option A: Foreground (debugging)**
```bash
# Activate venv
cd autobot-user-backend
source venv/bin/activate

# Run directly
python backend/main.py

# Logs appear in terminal
# Press Ctrl+C to stop
```

**Option B: Background (systemd)**
```bash
# Start as service
sudo systemctl start autobot-backend

# View logs
journalctl -u autobot-backend -f
```

**Option C: CLI wrapper**
```bash
scripts/start-services.sh start backend
scripts/start-services.sh logs backend
```

### Viewing Service Logs

**Real-time (follow mode):**
```bash
# Using systemd
journalctl -u autobot-backend -f

# Using wrapper
scripts/start-services.sh logs backend

# Multiple services
journalctl -u autobot-backend -u redis-stack-server -f
```

**Historical logs:**
```bash
# Last 100 lines
journalctl -u autobot-backend -n 100

# Last hour
journalctl -u autobot-backend --since "1 hour ago"

# Specific time range
journalctl -u autobot-backend --since "2026-02-13 08:00" --until "2026-02-13 09:00"

# Only errors and warnings
journalctl -u autobot-backend -p warning

# Export to file
journalctl -u autobot-backend > backend.log
```

### Debugging Service Failures

**1. Check service status:**
```bash
systemctl status autobot-backend

# Look for:
# - Active: active (running)  ← should be running
# - Exit code (if failed)
# - Recent log entries
```

**2. Check service logs:**
```bash
journalctl -u autobot-backend -n 50 --no-pager

# Look for:
# - Error messages
# - Stack traces
# - Configuration issues
```

**3. Check service configuration:**
```bash
# View systemd service file
systemctl cat autobot-backend

# Check for:
# - ExecStart command
# - WorkingDirectory
# - Environment variables
# - EnvironmentFile paths
```

**4. Test service manually:**
```bash
# Run command from service file manually
cd /opt/autobot/autobot-user-backend
source venv/bin/activate
python backend/main.py

# If this works but systemd doesn't:
# - Check file permissions
# - Check environment variables
# - Check working directory
```

**5. Check dependencies:**
```bash
# Ensure Redis is running
systemctl status redis-stack-server

# Check network connectivity
curl -k https://172.16.168.20:8443/api/health
```

### Restarting Services After Configuration Changes

**1. After changing .env file:**
```bash
# Reload doesn't work for environment changes
sudo systemctl restart autobot-backend
```

**2. After changing systemd service file:**
```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Then restart service
sudo systemctl restart autobot-backend
```

**3. After code changes:**
```bash
# If using systemd
sudo systemctl restart autobot-backend

# If running in foreground
# Press Ctrl+C and re-run python backend/main.py
```

---

## Service Configuration

### Backend Service Configuration

**Location:** `/etc/systemd/system/autobot-backend.service` (on deployed systems)

**Configuration Sources (in order):**
1. Ansible variables: `autobot-slm-backend/ansible/roles/backend/defaults/main.yml`
2. Environment file: `/opt/autobot/autobot-user-backend/.env`
3. Service auth keys: `/etc/autobot/service-keys/main-backend.env`

**Key Configuration:**
```ini
[Service]
WorkingDirectory=/opt/autobot/autobot-user-backend
ExecStart=/opt/autobot/autobot-user-backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8443
EnvironmentFile=/opt/autobot/autobot-user-backend/.env
Restart=always
```

**To modify:**
```bash
# Edit service file
sudo systemctl edit autobot-backend --full

# Or edit Ansible template and redeploy
# autobot-slm-backend/ansible/roles/backend/templates/autobot-backend.service.j2
```

### Environment Variables

**Backend (.env file):**
```bash
# Core
AUTOBOT_BACKEND_HOST=0.0.0.0
AUTOBOT_BACKEND_PORT=8443
AUTOBOT_BACKEND_TLS_ENABLED=true

# Redis
AUTOBOT_REDIS_HOST=172.16.168.23
AUTOBOT_REDIS_PORT=6379

# AI Services
AUTOBOT_OLLAMA_HOST=127.0.0.1
AUTOBOT_OLLAMA_PORT=11434

# Logging
AUTOBOT_LOG_LEVEL=INFO
```

**To update environment:**
1. Edit `.env` file
2. Restart service: `sudo systemctl restart autobot-backend`
3. Verify: `journalctl -u autobot-backend -n 20`

---

## Deployment

### Initial Deployment (Ansible)

**Deploy backend to main machine:**
```bash
cd autobot-slm-backend/ansible

# Deploy backend only
ansible-playbook playbooks/deploy-native-services.yml --tags backend

# Deploy all services on all nodes
ansible-playbook playbooks/deploy-native-services.yml
```

**Deploy to specific node:**
```bash
# Deploy to frontend VM
ansible-playbook playbooks/deploy-native-services.yml --limit 172.16.168.21

# Deploy NPU worker
ansible-playbook playbooks/deploy-native-services.yml --tags npu
```

### Code Updates

**Method 1: Via SLM (Recommended)**
1. Commit code changes to git
2. Open SLM GUI → Code Sync tab
3. Click "Deploy to Node"
4. Services restart automatically

**Method 2: Manual Sync**
```bash
# Sync code to remote node
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-backend/

# SSH to node and restart
ssh autobot@172.16.168.20
sudo systemctl restart autobot-backend
```

**Method 3: Ansible Redeploy**
```bash
# Full redeploy (slower but guaranteed clean state)
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-native-services.yml --tags backend
```

---

## Troubleshooting

### Service Won't Start

**Symptom:** `systemctl start autobot-backend` fails

**Diagnosis:**
```bash
# Check exact error
systemctl status autobot-backend

# Check recent logs
journalctl -u autobot-backend -n 50

# Try manual start
cd /opt/autobot/autobot-user-backend
source venv/bin/activate
python backend/main.py
```

**Common causes:**
- Missing Python dependencies: `pip install -r requirements.txt`
- Permission issues: `chown -R autobot:autobot /opt/autobot`
- Port already in use: `lsof -i :8443`
- Missing .env file: Copy from template
- Redis not running: `systemctl start redis-stack-server`

### Service Crashes on Startup

**Symptom:** Service starts then immediately stops

**Diagnosis:**
```bash
# Check exit code
systemctl status autobot-backend

# Full logs since last boot
journalctl -u autobot-backend -b

# Look for Python tracebacks
journalctl -u autobot-backend | grep -A 20 "Traceback"
```

**Common causes:**
- Configuration error in .env
- Database connection failure
- Missing TLS certificates
- Import errors (missing dependencies)
- Port permission issues (< 1024 requires CAP_NET_BIND_SERVICE)

### High CPU/Memory Usage

**Diagnosis:**
```bash
# Check resource usage
systemctl status autobot-backend

# Detailed process info
ps aux | grep autobot-backend

# System resource usage
top -p $(pgrep -f autobot-backend)

# Memory leaks
journalctl -u autobot-backend | grep -i "memory\|oom"
```

**Actions:**
- Check for infinite loops in code
- Review recent log entries for repeated errors
- Monitor Redis memory usage
- Check ChromaDB size
- Review async task queue depth

### Logs Not Appearing

**Symptom:** `journalctl` shows no logs

**Diagnosis:**
```bash
# Check if service is actually running
systemctl status autobot-backend

# Check StandardOutput/StandardError in service file
systemctl cat autobot-backend

# Check system journal
journalctl --disk-usage
journalctl --verify
```

**Solutions:**
- Ensure logging is configured in code
- Check syslog forwarding
- Verify disk space: `df -h`
- Check journal rotation: `/etc/systemd/journald.conf`

---

## Migration from run_autobot.sh

### Why the Change?

**Old way (run_autobot.sh):**
- ❌ Configuration drift (different .env vs Ansible)
- ❌ Manual process (no automation)
- ❌ No monitoring
- ❌ Different from production
- ❌ Hard to debug

**New way (SLM + systemd):**
- ✅ Single source of truth
- ✅ Automated deployment
- ✅ Web GUI monitoring
- ✅ Same as production
- ✅ Standard Linux tooling

### Migration Steps

**1. Stop using run_autobot.sh:**
```bash
# If currently running via run_autobot.sh
# Find and kill the process
pkill -f "uvicorn.*backend"
pkill -f "python.*backend/main.py"
```

**2. Deploy via Ansible (one-time setup):**
```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-native-services.yml --tags backend
```

**3. Use new management methods:**
```bash
# CLI wrapper
scripts/start-services.sh start backend

# Or systemctl
sudo systemctl start autobot-backend

# Or SLM GUI
# Open https://172.16.168.19/orchestration
```

**4. Update your workflow:**
- **Before:** `bash run_autobot.sh --dev`
- **After:** `scripts/start-services.sh start` or SLM GUI

### Frequently Asked Questions

**Q: Can I still run the backend in foreground for debugging?**
A: Yes! See "Starting the Backend for Development" → Option A above.

**Q: What if I need to modify backend arguments?**
A: Edit the systemd service file or Ansible template, don't modify run_autobot.sh.

**Q: Where did my logs go?**
A: They're in systemd journal now. Use `journalctl -u autobot-backend -f`

**Q: Can I still use environment variables?**
A: Yes, they're in `/opt/autobot/autobot-user-backend/.env` and loaded by systemd.

**Q: What about VNC and desktop access?**
A: VNC is a separate service: `sudo systemctl start vncserver@1`

---

## Quick Reference

### Start Services
```bash
scripts/start-services.sh start
```

### Stop Services
```bash
scripts/start-services.sh stop
```

### View Logs
```bash
scripts/start-services.sh logs backend
```

### Check Status
```bash
scripts/start-services.sh status
```

### Open GUI
```bash
scripts/start-services.sh gui
```

### Restart After Code Change
```bash
sudo systemctl restart autobot-backend
```

### Debug Startup Issues
```bash
journalctl -u autobot-backend -n 50
```

---

## Additional Resources

- **SLM Orchestration:** https://172.16.168.19/orchestration
- **Systemd Documentation:** `man systemd`, `man journalctl`
- **Ansible Playbooks:** `autobot-slm-backend/ansible/playbooks/`
- **Service Templates:** `autobot-slm-backend/ansible/roles/*/templates/*.service.j2`
- **Issues:** #862 (architecture decision), #863 (implementation)

---

## Getting Help

**Common Issues:**
1. Service won't start → Check logs: `journalctl -u autobot-backend -n 50`
2. Configuration not loading → Restart: `sudo systemctl restart autobot-backend`
3. Can't access GUI → Check network: `ping 172.16.168.19`
4. Port in use → Find process: `lsof -i :8443`

**Need more help?**
- Check GitHub issues: https://github.com/mrveiss/AutoBot-AI/issues
- Review systemd logs: `journalctl -xe`
- Ask in project discussions

---

**Last Updated:** 2026-02-13
**Maintained by:** AutoBot DevOps Team
**Related:** #862, #863, docs/GETTING_STARTED_COMPLETE.md
