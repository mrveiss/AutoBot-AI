# SSH Manager Deployment Checklist

## Pre-Deployment Verification

### ✅ Code Implementation
- [x] SSH Connection Pool implemented (`backend/services/ssh_connection_pool.py`)
- [x] SSH Manager Service implemented (`backend/services/ssh_manager.py`)
- [x] Remote Terminal API implemented (`backend/api/remote_terminal.py`)
- [x] FastAPI integration completed (`backend/app_factory.py`)
- [x] Configuration added (`config/config.yaml`)

### ✅ Testing
- [x] Unit tests created (`tests/test_ssh_connection_pool.py`)
- [x] Integration tests created (`tests/test_ssh_manager_integration.py`)
- [x] Verification script created (`scripts/utilities/verify_ssh_manager.py`)

### ✅ Documentation
- [x] Feature documentation (`docs/features/SSH_CONNECTION_MANAGER.md`)
- [x] Implementation summary (`docs/SSH_MANAGER_IMPLEMENTATION_SUMMARY.md`)
- [x] Deployment checklist (this document)

---

## Deployment Steps

### Step 1: Verify Installation

Run the verification script:
```bash
cd /home/kali/Desktop/AutoBot
python3 scripts/utilities/verify_ssh_manager.py
```

**Expected Output**:
- ✅ All modules import successfully
- ✅ SSH key found and permissions correct
- ✅ Configuration file found with SSH section
- ✅ SSH Manager initializes and starts successfully
- ✅ All test and documentation files present

**If Verification Fails**:
- Check error messages carefully
- Ensure all dependencies installed: `pip install paramiko pyyaml`
- Verify file paths and permissions

---

### Step 2: SSH Key Setup

#### Generate SSH Key (if not exists)

```bash
# Check if key exists
ls ~/.ssh/autobot_key

# If not, generate new key
ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key -N ""

# Set correct permissions
chmod 600 ~/.ssh/autobot_key
chmod 644 ~/.ssh/autobot_key.pub
```

#### Deploy Key to All Hosts

```bash
# Copy public key to all AutoBot hosts
for host in 172.16.168.{20..25}; do
    echo "Deploying to $host..."
    ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@$host
done

# Verify SSH access to each host
for host in 172.16.168.{20..25}; do
    echo "Testing $host..."
    ssh -i ~/.ssh/autobot_key autobot@$host "echo 'SSH access verified'"
done
```

**Expected Result**: All hosts should respond with "SSH access verified"

**Troubleshooting**:
- If connection refused: Ensure SSH service running on target host
- If permission denied: Check authorized_keys permissions (644)
- If host key verification fails: Add host keys to known_hosts

---

### Step 3: Configuration Verification

Check `config/config.yaml` has SSH section:

```yaml
ssh:
  enabled: true
  key_path: ~/.ssh/autobot_key
  connection_pool:
    max_connections_per_host: 5
    connect_timeout: 30
    idle_timeout: 300
    health_check_interval: 60
  hosts:
    main:
      ip: 172.16.168.20
      port: 22
      user: autobot
      description: Main machine - Backend API + VNC Desktop
      enabled: true
    # ... (other 5 hosts)
```

**Verify**:
```bash
grep -A 30 "^ssh:" config/config.yaml
```

---

### Step 4: Run Unit Tests

```bash
# Run connection pool tests
pytest tests/test_ssh_connection_pool.py -v

# Expected: All tests pass (uses mocks, no SSH required)
```

**Expected Output**:
```
tests/test_ssh_connection_pool.py::test_pool_initialization PASSED
tests/test_ssh_connection_pool.py::test_pool_start_stop PASSED
tests/test_ssh_connection_pool.py::test_create_connection_success PASSED
...
======================== 15 passed in 2.34s ========================
```

**If Tests Fail**:
- Check import errors
- Verify pytest installed: `pip install pytest pytest-asyncio`
- Review error messages for missing dependencies

---

### Step 5: Run Integration Tests

```bash
# Run integration tests (requires SSH access)
pytest tests/test_ssh_manager_integration.py -v -m integration

# Tests will skip if SSH not available
```

**Expected Output**:
```
tests/test_ssh_manager_integration.py::test_ssh_manager_initialization PASSED
tests/test_ssh_manager_integration.py::test_execute_command_simple PASSED
tests/test_ssh_manager_integration.py::test_health_check_all_hosts PASSED
...
======================== 15 passed in 12.45s ========================
```

**If Tests Fail**:
- Verify SSH key deployed to all hosts (Step 2)
- Check network connectivity to hosts
- Review logs for connection errors

---

### Step 6: Start AutoBot Backend

```bash
# Start backend with SSH manager
bash run_autobot.sh --dev --no-build
```

**Check Startup Logs**:
```
✅ Optional router loaded: remote_terminal (includes prefix /api/remote-terminal)
SSH Manager initialized with 6 hosts, key_path=~/.ssh/autobot_key
SSH connection pool started with health monitoring
```

**If Router Not Loaded**:
- Check `backend/app_factory.py` has remote_terminal import
- Verify no import errors in logs
- Ensure paramiko installed

---

### Step 7: API Verification

#### Test 1: API Info Endpoint

```bash
curl http://172.16.168.20:8001/api/remote-terminal/
```

**Expected Response**:
```json
{
  "name": "Remote Terminal API",
  "version": "1.0.0",
  "description": "Multi-host SSH terminal access and remote command execution",
  "features": [...],
  "endpoints": {...}
}
```

#### Test 2: List Hosts

```bash
curl http://172.16.168.20:8001/api/remote-terminal/hosts
```

**Expected Response**:
```json
{
  "hosts": [
    {
      "name": "main",
      "ip": "172.16.168.20",
      "port": 22,
      "username": "autobot",
      "description": "Main machine - Backend API + VNC Desktop",
      "enabled": true
    },
    ...
  ],
  "total": 6,
  "enabled": 6
}
```

#### Test 3: Health Check

```bash
curl http://172.16.168.20:8001/api/remote-terminal/health
```

**Expected Response**:
```json
{
  "timestamp": "2025-10-04T10:30:15.123456",
  "hosts": {
    "main": true,
    "frontend": true,
    "npu-worker": true,
    "redis": true,
    "ai-stack": true,
    "browser": true
  },
  "total": 6,
  "healthy": 6,
  "unhealthy": 0
}
```

#### Test 4: Execute Simple Command

```bash
curl -X POST http://172.16.168.20:8001/api/remote-terminal/execute \
  -H "Content-Type: application/json" \
  -d '{
    "host": "main",
    "command": "echo \"SSH Manager Deployed\"",
    "timeout": 10,
    "validate": true
  }'
```

**Expected Response**:
```json
{
  "host": "main",
  "command": "echo \"SSH Manager Deployed\"",
  "stdout": "SSH Manager Deployed\n",
  "stderr": "",
  "exit_code": 0,
  "success": true,
  "execution_time": 0.123,
  "timestamp": "2025-10-04T10:30:15.123456",
  "security_info": {
    "validated": true,
    "risk_level": "safe"
  }
}
```

#### Test 5: Connection Pool Stats

```bash
curl http://172.16.168.20:8001/api/remote-terminal/stats
```

**Expected Response**:
```json
{
  "timestamp": "2025-10-04T10:30:15.123456",
  "pools": {
    "autobot@172.16.168.20:22": {
      "total": 1,
      "idle": 1,
      "active": 0,
      "unhealthy": 0,
      "closed": 0
    }
  },
  "total_connections": 1,
  "active_connections": 0,
  "idle_connections": 1
}
```

---

### Step 8: Security Validation Test

#### Test Dangerous Command Blocking

```bash
curl -X POST http://172.16.168.20:8001/api/remote-terminal/execute \
  -H "Content-Type: application/json" \
  -d '{
    "host": "main",
    "command": "rm -rf /",
    "timeout": 10,
    "validate": true
  }'
```

**Expected Response** (403 Forbidden):
```json
{
  "detail": "Command blocked: Dangerous command blocked by security policy"
}
```

---

### Step 9: Batch Execution Test

```bash
curl -X POST http://172.16.168.20:8001/api/remote-terminal/batch \
  -H "Content-Type: application/json" \
  -d '{
    "hosts": ["main", "frontend", "redis"],
    "command": "uptime",
    "timeout": 30,
    "validate": true,
    "parallel": true
  }'
```

**Expected Response**:
```json
{
  "command": "uptime",
  "hosts": ["main", "frontend", "redis"],
  "parallel": true,
  "results": {
    "main": {
      "stdout": "10:30:15 up 5 days, 12:34...",
      "exit_code": 0,
      "success": true
    },
    ...
  },
  "total_hosts": 3,
  "successful": 3
}
```

---

### Step 10: Monitoring Setup

#### Enable Audit Logging

Already enabled by default in `config/config.yaml`:
```yaml
backend:
  audit_log_file: logs/audit.log
```

#### Monitor SSH Operations

```bash
# Watch audit log in real-time
tail -f logs/audit.log | grep ssh_audit

# View recent SSH operations
grep ssh_audit logs/audit.log | tail -20
```

#### Monitor Connection Pool

```bash
# Check pool stats periodically
watch -n 5 'curl -s http://172.16.168.20:8001/api/remote-terminal/stats | jq'
```

---

## Post-Deployment Verification

### Checklist

- [ ] Verification script passed
- [ ] SSH keys deployed to all hosts
- [ ] Unit tests passing
- [ ] Integration tests passing (or skipped if SSH unavailable)
- [ ] Backend started successfully with remote_terminal router
- [ ] API info endpoint responding
- [ ] Host list endpoint showing all 6 hosts
- [ ] Health check showing all hosts healthy (or expected status)
- [ ] Simple command execution successful
- [ ] Dangerous command blocked correctly
- [ ] Batch execution working
- [ ] Connection pool statistics available
- [ ] Audit logging working

### Success Criteria

**Deployment is successful when**:
1. ✅ All API endpoints responding correctly
2. ✅ At least 1 host (main) accessible via SSH
3. ✅ Commands execute successfully
4. ✅ Security validation working (dangerous commands blocked)
5. ✅ Audit logging active

---

## Rollback Procedure

**If deployment fails**, rollback is simple:

1. **Stop Backend**:
   ```bash
   # Stop AutoBot
   pkill -f "uvicorn backend.app_factory"
   ```

2. **Disable SSH Manager**:
   ```yaml
   # In config/config.yaml
   ssh:
     enabled: false
   ```

3. **Restart Backend**:
   ```bash
   bash run_autobot.sh --dev --no-build
   ```

**Note**: The router is optional and will gracefully fail if dependencies unavailable.

---

## Troubleshooting Guide

### Common Issues

#### 1. Import Errors

**Symptom**: Router not loaded, import errors in logs

**Solution**:
```bash
pip install paramiko pyyaml
```

#### 2. SSH Connection Refused

**Symptom**: Health check fails, connection errors

**Solution**:
```bash
# Verify SSH service running on target
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21

# Check firewall
sudo ufw status

# Verify SSH daemon
systemctl status ssh
```

#### 3. Permission Denied

**Symptom**: SSH authentication fails

**Solution**:
```bash
# Fix key permissions
chmod 600 ~/.ssh/autobot_key

# Re-deploy key
ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@172.16.168.21

# Check authorized_keys on target
ssh autobot@172.16.168.21 "ls -la ~/.ssh/authorized_keys"
```

#### 4. Command Blocked Unexpectedly

**Symptom**: Safe commands being blocked

**Solution**:
- Check command risk level in security validation
- Review audit logs for block reason
- Adjust security settings if needed
- Consider disabling validation for specific commands: `validate=False`

#### 5. Pool Exhausted

**Symptom**: "Connection pool exhausted" errors

**Solution**:
```yaml
# Increase pool size in config.yaml
ssh:
  connection_pool:
    max_connections_per_host: 10  # Increased from 5
```

---

## Monitoring Dashboard

### Key Metrics to Monitor

1. **Connection Pool Health**:
   - Total connections per host
   - Idle vs active connections
   - Connection reuse rate

2. **Command Execution**:
   - Success rate
   - Average execution time
   - Commands blocked by security

3. **Host Health**:
   - Hosts online/offline
   - Health check failures
   - Connection errors

### Sample Monitoring Script

```bash
#!/bin/bash
# Monitor SSH Manager health

echo "SSH Manager Health Check"
echo "======================="

# API status
echo "1. API Status:"
curl -s http://172.16.168.20:8001/api/remote-terminal/ | jq -r '.name'

# Host health
echo -e "\n2. Host Health:"
curl -s http://172.16.168.20:8001/api/remote-terminal/health | jq '.hosts'

# Pool stats
echo -e "\n3. Connection Pool:"
curl -s http://172.16.168.20:8001/api/remote-terminal/stats | jq '{
  total_connections,
  active_connections,
  idle_connections
}'

# Recent audit log
echo -e "\n4. Recent SSH Operations:"
tail -5 logs/audit.log | grep ssh_audit
```

---

## Success!

If all steps above pass, SSH Manager is successfully deployed and ready for production use!

**Next Steps**:
1. Monitor audit logs for SSH activity
2. Track connection pool statistics
3. Consider integrating with monitoring dashboards
4. Explore advanced features (file transfer, port forwarding)

**Documentation Reference**:
- User Guide: `docs/features/SSH_CONNECTION_MANAGER.md`
- Implementation Details: `docs/SSH_MANAGER_IMPLEMENTATION_SUMMARY.md`
- API Reference: Source code docstrings

---

**Deployment Date**: _____________
**Deployed By**: _____________
**Verification Status**: _____________
**Notes**: _____________
