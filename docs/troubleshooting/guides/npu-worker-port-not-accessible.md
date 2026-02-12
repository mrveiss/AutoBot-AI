# NPU Worker Port Not Accessible

**Issue Number**: #851
**Date Reported**: 2026-02-12
**Severity**: High
**Component**: Infrastructure / NPU Worker

---

## Symptoms

- NPU Worker service shows `active (running)` status
- Connection to port 8081 fails: `curl: (7) Failed to connect`
- `/var/log/autobot/npu-worker.log` is empty (no startup messages)
- Backend cannot offload AI inference to NPU
- Health checks fail from main server

## Root Cause

The NPU worker deployed via Ansible was a **placeholder implementation**:
- Python process ran successfully but only executed an infinite sleep loop
- No HTTP server was ever bound to port 8081
- Service appeared healthy in systemd but wasn't actually listening

## Quick Fix

```bash
# Check if NPU worker has FastAPI installed
ssh autobot@172.16.168.22 "pip list | grep fastapi"

# If missing, install dependencies
ssh autobot@172.16.168.22 "cd /opt/autobot/npu-worker && ./venv/bin/pip install 'fastapi>=0.100.0' 'uvicorn[standard]>=0.20.0'"

# Restart service
ssh autobot@172.16.168.22 "sudo systemctl restart autobot-npu-worker"

# Verify port is accessible
curl http://172.16.168.22:8081/health
```

## Detailed Resolution Steps

### Step 1: Verify Service Status
```bash
ssh autobot@172.16.168.22 "sudo systemctl status autobot-npu-worker"
```
**Expected Output**:
```
● autobot-npu-worker.service - AutoBot NPU Acceleration Worker
     Active: active (running)
```

### Step 2: Check Port Binding
```bash
ssh autobot@172.16.168.22 "sudo netstat -tlnp | grep 8081"
```
**Expected Output** (if broken):
```
(empty - no process listening on 8081)
```

### Step 3: Review NPU Worker Code
```bash
ssh autobot@172.16.168.22 "head -30 /opt/autobot/npu-worker/npu-worker.py"
```
Look for:
- FastAPI imports
- `uvicorn.run()` call
- Port binding to `0.0.0.0:8081`

If missing, the worker needs to be updated.

### Step 4: Deploy Fixed Version
```bash
# From AutoBot repo root
cd autobot-slm-backend/ansible
ansible-playbook -i inventory.yml setup-npu-worker.yml --limit vm2

# Or manually copy updated npu-worker.py template
scp roles/npu-worker/templates/npu-worker.py.j2 autobot@172.16.168.22:/opt/autobot/npu-worker/npu-worker.py
```

### Step 5: Install Dependencies
```bash
ssh autobot@172.16.168.22 "cd /opt/autobot/npu-worker && sudo -u autobot ./venv/bin/pip install 'fastapi>=0.100.0' 'uvicorn[standard]>=0.20.0'"
```
**Expected Output**:
```
Successfully installed fastapi-0.129.0 uvicorn-0.40.0 [...]
```

### Step 6: Configure Firewall
```bash
ssh autobot@172.16.168.22 "sudo ufw allow 8081/tcp comment 'NPU Worker API'"
```

### Step 7: Restart Service
```bash
ssh autobot@172.16.168.22 "sudo systemctl restart autobot-npu-worker"
sleep 3
ssh autobot@172.16.168.22 "sudo systemctl status autobot-npu-worker"
```

## Verification

```bash
# Test health endpoint from main server
curl http://172.16.168.22:8081/health

# Expected response:
# {
#   "status": "healthy" | "degraded",
#   "service": "npu-worker",
#   "version": "1.0.0",
#   "capabilities": {
#     "device": "NPU",
#     "available": true | false
#   }
# }

# Check logs for startup messages
ssh autobot@172.16.168.22 "tail -20 /var/log/autobot/npu-worker.log"

# Should show:
# INFO:     Uvicorn running on http://0.0.0.0:8081
```

**Success Indicators**:
- Port 8081 responds to HTTP requests
- Health endpoint returns JSON
- Logs show "Uvicorn running on http://0.0.0.0:8081"
- Firewall allows port 8081 (check with `sudo ufw status | grep 8081`)

## Prevention

1. **Always deploy using Ansible roles** instead of manual file copies
2. **Test endpoints after deployment**:
   ```bash
   curl http://172.16.168.22:8081/health
   ```
3. **Monitor startup logs** during service restart:
   ```bash
   sudo journalctl -u autobot-npu-worker -f
   ```
4. **Add health check to monitoring** system to detect port accessibility issues

## Related Issues

- #590: NPU Worker Dashboard Improvements
- #808: Hardcoded IP removal (related infrastructure cleanup)

## References

- PR #852: Fix implementation
- Commit: `a02cc6ad`
- Ansible Role: `autobot-slm-backend/ansible/roles/npu-worker/`
- Service File: `/etc/systemd/system/autobot-npu-worker.service`
