# AutoBot Backend Debugging Guide

> Derived from real-world diagnosis during Issue #881 (UFW firewall deadlock) and related issues.
> This guide covers the most common failure modes and their diagnostic steps.

---

## Table of Contents

1. [Backend Won't Start](#1-backend-wont-start)
2. [Backend Starts But Doesn't Respond](#2-backend-starts-but-doesnt-respond)
3. [Connection Timeouts](#3-connection-timeouts)
4. [Python Version / Import Issues](#4-python-version--import-issues)
5. [Common Red Herrings](#5-common-red-herrings)
6. [Diagnostic Toolkit](#6-diagnostic-toolkit)
7. [Systemd Troubleshooting](#7-systemd-troubleshooting)
8. [Symlink Issues (WSL2)](#8-symlink-issues-wsl2)

---

## 1. Backend Won't Start

### Step 1: Check systemd status and logs

```bash
sudo systemctl status autobot-backend.service --no-pager
journalctl -u autobot-backend.service -n 100 --no-pager
```

### Step 2: Check application log files

```bash
tail -50 /var/log/autobot/backend.log
tail -50 /var/log/autobot/backend-error.log
```

### Step 3: Test the import chain directly

```bash
cd /opt/autobot
source venv/bin/activate
python -c 'from backend.app_factory import create_app; print("Import OK")'
```

If this fails, you'll see the exact ImportError with module path.

### Step 4: Check for broken symlinks

```bash
ls -la /opt/autobot/autobot-user-backend/backend
ls -la /opt/autobot/autobot-user-backend/autobot_shared
```

Both should be symlinks pointing to valid targets. If they're plain text files containing a path (WSL2 `core.symlinks=false`), recreate them manually:

```bash
cd /opt/autobot/autobot-user-backend
rm backend && ln -s autobot-user-backend backend 2>/dev/null || ln -s ../autobot-user-backend backend
rm autobot_shared && ln -s ../autobot-shared autobot_shared
```

### Step 5: Check Python interpreter and venv

```bash
/opt/autobot/venv/bin/python --version
/opt/autobot/venv/bin/pip list | grep -E "fastapi|uvicorn|pydantic"
```

Mismatch between venv Python and system Python causes silent import failures.

### Step 6: Verify the .env file exists

```bash
cat /opt/autobot/.env | grep -v "KEY\|SECRET\|PASSWORD"  # safe preview
```

Missing `.env` → backend fails to start. Deploy via Ansible:

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-backend-env.yml --limit main_server
```

---

## 2. Backend Starts But Doesn't Respond

### ⚠️ CRITICAL FIRST CHECK: Firewall (UFW)

**This is the #1 cause of "backend starts, no response" issues.**

```bash
# Check if UFW is blocking packets (look for DPT=8001 or your port)
sudo dmesg | grep UFW | tail -20

# Check UFW status
sudo ufw status verbose

# Quick test: temporarily disable UFW
sudo ufw disable
curl -s http://localhost:8001/api/health
sudo ufw enable  # re-enable immediately after test
```

If disabling UFW fixes it: add a rule instead of leaving it disabled:

```bash
sudo ufw allow 8001/tcp comment "AutoBot backend"
sudo ufw allow 8443/tcp comment "AutoBot backend HTTPS"
sudo ufw reload
```

### Socket binding check

```bash
# Is the backend actually listening?
ss -tlnp | grep 8001
netstat -tulpn | grep 8001
lsof -i :8001
```

If nothing shows: the backend crashed at startup. Check logs (section 1).

If it shows `127.0.0.1:8001` but you're connecting from another host: binding to loopback only. Fix in `.env` or Ansible template:

```
BACKEND_HOST=0.0.0.0
```

### Middleware deadlock check

```bash
# Test with a curl that bypasses the frontend
curl -v --max-time 10 http://localhost:8001/api/health

# If it hangs: strace the uvicorn process to see where it's blocked
sudo strace -p $(pgrep -f uvicorn) -e trace=network,futex 2>&1 | head -50
```

---

## 3. Connection Timeouts

**Diagnose in this order — stop when you find the cause:**

### 1. Firewall (UFW/iptables) — check first, always

```bash
sudo dmesg | grep UFW | tail -20
sudo iptables -L -v -n | grep DROP
```

### 2. Network binding

```bash
# Is it bound to 0.0.0.0 or 127.0.0.1?
ss -tlnp | grep PORT
```

### 3. Health endpoint test

```bash
# From the server itself
curl -s --max-time 5 http://127.0.0.1:8001/api/health

# From another host
curl -s --max-time 5 https://172.16.168.20:8443/api/health
```

### 4. Network path check

```bash
# Can you reach the port at all?
telnet 172.16.168.20 8001

# Packet-level view
sudo tcpdump -i any port 8001 -n
```

### 5. Event loop check

```bash
# See what the process is actually doing
sudo strace -p $(pgrep -f autobot-backend) -e trace=network 2>&1 | head -30
```

---

## 4. Python Version / Import Issues

### Symptoms of actual Python version issues

- `ImportError: No module named 'something'` for stdlib modules
- `SyntaxError` on valid Python code
- C extension build failures

### Symptoms that are NOT Python version issues

- Connection timeouts → check firewall first
- Socket binding failures → check permissions and ports
- Event loop "deadlocks" → usually application code or middleware

### Checking Python versions

```bash
which python3
python3 --version
/opt/autobot/venv/bin/python --version

# Conda env (main backend on WSL)
conda activate autobot-backend
python --version
```

### Python 3.13 + aioredis compatibility

If you see `ModuleNotFoundError: No module named 'aioredis'`:

```bash
# Create compatibility shim
cat > /opt/autobot/venv/lib/python3.13/site-packages/aioredis.py << 'EOF'
"""Compatibility shim: aioredis merged into redis package."""
from redis import asyncio as aioredis  # noqa: F401
EOF
```

### venv rebuild after OS upgrade

```bash
rm -rf /opt/autobot/venv
python3 -m venv /opt/autobot/venv
source /opt/autobot/venv/bin/activate
pip install --upgrade pip
pip install -r /opt/autobot/autobot-user-backend/requirements.txt
```

---

## 5. Common Red Herrings

These were investigated during Issue #881 and ruled out as causes of connection timeout. **Do not spend time on these until you've confirmed it's not firewall-related.**

| Suspected Cause | Investigation | Verdict |
|----------------|---------------|---------|
| Python 3.13 incompatibility | Tested with Python 3.12 | ❌ Same issue |
| httptools ASGI server | Switched to h11 parser | ❌ Same issue |
| uvloop event loop | Disabled, used asyncio | ❌ Same issue |
| systemd service config | Ran directly via bash | ❌ Same issue |
| Missing middleware | Removed all middleware | ❌ Same issue |
| **UFW firewall** | Disabled UFW | ✅ **Immediately fixed** |

**Lesson: Connection timeout + backend running = firewall. Check UFW first.**

---

## 6. Diagnostic Toolkit

### Firewall

```bash
sudo dmesg | grep UFW                    # Live packet drops
sudo ufw status verbose                  # Current rules
sudo iptables -L -v -n                   # Raw iptables state
sudo ufw allow PORT/tcp && sudo ufw reload  # Add rule
```

### Network

```bash
ss -tlnp | grep PORT                     # Listening sockets
netstat -tulpn | grep PORT               # Alternative
lsof -i :PORT                            # Process using port
telnet HOST PORT                         # TCP connectivity test
sudo tcpdump -i any port PORT -n         # Packet capture
```

### Application

```bash
strace -p PID -e trace=network           # System calls
curl -v --max-time 10 URL               # Verbose HTTP test
```

### Logs

```bash
journalctl -u autobot-backend.service -f              # Follow service logs
journalctl -u autobot-backend.service -n 100          # Last 100 lines
tail -f /var/log/autobot/backend.log                  # App log
tail -f /var/log/autobot/backend-error.log            # Error log
journalctl -u autobot-backend.service --since "5 min ago" | grep -i error
```

---

## 7. Systemd Troubleshooting

### Service won't restart after code change

```bash
sudo systemctl daemon-reload
sudo systemctl restart autobot-backend.service
sudo systemctl status autobot-backend.service --no-pager
```

### Service starts then immediately dies

```bash
journalctl -u autobot-backend.service --since "1 min ago"
# Look for: ImportError, RuntimeError, missing .env, port already in use
```

### Port already in use

```bash
sudo lsof -i :8001
sudo kill -9 PID  # if safe to kill
# Or use a different port in .env
```

### EnvironmentFile not loading

```bash
# Check the service file
cat /etc/systemd/system/autobot-backend.service | grep Environ

# Verify secrets file exists
ls -la /etc/autobot/
cat /etc/autobot/db-credentials.env  # check format: KEY=value
```

---

## 8. Symlink Issues (WSL2)

WSL2 with `core.symlinks=false` stores symlinks as text files containing the target path. After `git pull` or `git checkout`, symlinks may break.

### Detection

```bash
file autobot-user-backend/backend
# Should show: "symbolic link to ../autobot-user-backend"
# BAD: "ASCII text" (contains path as text)
```

### Fix

```bash
cd /home/kali/Desktop/AutoBot/autobot-user-backend
rm backend && ln -s ../autobot-user-backend backend
rm autobot_shared && ln -s ../autobot-shared autobot_shared
```

### Prevent recurrence

Enable symlinks in WSL:

```bash
git config core.symlinks true
```

Or set in `/etc/wsl.conf` on the WSL instance:

```ini
[automount]
options = "metadata"
```

---

## Related Issues

| Issue | Problem | Root Cause |
|-------|---------|-----------|
| [#881](https://github.com/mrveiss/AutoBot-AI/issues/881) | Backend deadlock / no response | UFW firewall blocking port |
| [#886](https://github.com/mrveiss/AutoBot-AI/issues/886) | WSL2 symlink issues | `core.symlinks=false` |
| [#887](https://github.com/mrveiss/AutoBot-AI/issues/887) | UFW default rules | Needed explicit port rule |
| [#888](https://github.com/mrveiss/AutoBot-AI/issues/888) | Requirements.txt conflicts | Pinning incompatibility |
| [#868](https://github.com/mrveiss/AutoBot-AI/issues/868) | Backend crash-looping | Missing .env, aioredis compat, PYTHONPATH |
