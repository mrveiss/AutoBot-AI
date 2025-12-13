# AutoBot Disaster Recovery Procedures

**Last Updated**: 2025-12-13
**Related Issue**: [#251](https://github.com/mrveiss/AutoBot-AI/issues/251)
**Classification**: Operations Critical

This document provides disaster recovery procedures for AutoBot's distributed infrastructure.

---

## Recovery Objectives

| Metric | Target | Maximum Acceptable |
|--------|--------|-------------------|
| **RTO** (Recovery Time Objective) | 30 minutes | 2 hours |
| **RPO** (Recovery Point Objective) | 1 hour | 4 hours |

---

## Failure Scenarios

### Scenario 1: Main Backend Failure (172.16.168.20)

**Impact**: Complete API outage, no chat functionality

**Symptoms**:
- Frontend shows connection errors
- Health check fails: `curl http://localhost:8001/api/health`
- VNC desktop unavailable

**Recovery Steps**:

1. **Diagnose the failure**
   ```bash
   # Check if process is running
   ps aux | grep uvicorn

   # Check system logs
   journalctl -u autobot-backend -n 100

   # Check application logs
   tail -f /home/kali/Desktop/AutoBot/logs/backend.log
   ```

2. **Restart the service**
   ```bash
   # Stop existing process
   pkill -f "uvicorn backend.main:app"

   # Start fresh
   cd /home/kali/Desktop/AutoBot
   bash run_autobot.sh --dev
   ```

3. **Verify recovery**
   ```bash
   curl http://localhost:8001/api/health
   ```

**Estimated Recovery Time**: 5-10 minutes

---

### Scenario 2: Frontend VM Failure (172.16.168.21)

**Impact**: No web interface, API still functional

**Symptoms**:
- Cannot access `http://172.16.168.21:5173`
- SSH to VM1 fails or shows issues

**Recovery Steps**:

1. **Check VM status**
   ```powershell
   # On Hyper-V host
   Get-VM -Name "AutoBot-Frontend" | Select-Object State, Status
   ```

2. **Restart VM if needed**
   ```powershell
   Restart-VM -Name "AutoBot-Frontend" -Force
   ```

3. **SSH and restart service**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21

   # On VM1:
   cd ~/autobot-vue
   npm run dev -- --host 0.0.0.0
   ```

4. **Or use startup script from main machine**
   ```bash
   bash run_autobot.sh --dev
   ```

**Estimated Recovery Time**: 5-15 minutes

---

### Scenario 3: Redis Failure (172.16.168.23)

**Impact**: Session loss, knowledge base unavailable, cache miss

**Symptoms**:
- Connection errors in backend logs
- `redis-cli -h 172.16.168.23 ping` fails
- Chat responses very slow or fail

**Recovery Steps**:

1. **Check Redis status**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23
   sudo systemctl status redis-stack-server
   ```

2. **Restart Redis**
   ```bash
   sudo systemctl restart redis-stack-server
   ```

3. **Verify connectivity**
   ```bash
   redis-cli -h 172.16.168.23 ping
   redis-cli -h 172.16.168.23 INFO
   ```

4. **Restore from backup if data lost**
   ```bash
   # Stop Redis
   sudo systemctl stop redis-stack-server

   # Restore RDB file
   sudo cp /path/to/backup/dump.rdb /var/lib/redis-stack/dump.rdb
   sudo chown redis:redis /var/lib/redis-stack/dump.rdb

   # Start Redis
   sudo systemctl start redis-stack-server
   ```

**Estimated Recovery Time**: 5-30 minutes (depending on restore need)

---

### Scenario 4: AI Stack Failure (172.16.168.24)

**Impact**: LLM responses fail, embeddings unavailable

**Symptoms**:
- Chat responses timeout
- `curl http://172.16.168.24:8080/api/tags` fails
- Backend logs show Ollama connection errors

**Recovery Steps**:

1. **Check Ollama status**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.24
   sudo systemctl status ollama
   ```

2. **Restart Ollama**
   ```bash
   sudo systemctl restart ollama
   ```

3. **Verify models are loaded**
   ```bash
   curl http://172.16.168.24:8080/api/tags
   ```

4. **Pull models if missing**
   ```bash
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ```

**Estimated Recovery Time**: 5-20 minutes

**Fallback**: Backend automatically falls back to cloud LLM if configured.

---

### Scenario 5: NPU Worker Failure (172.16.168.22)

**Impact**: Slower embeddings (falls back to cloud/CPU)

**Symptoms**:
- Embedding generation slower
- Backend logs show NPU connection warnings

**Recovery Steps**:

1. **Check NPU worker status**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.22
   sudo systemctl status npu-worker
   ```

2. **Restart NPU service**
   ```bash
   sudo systemctl restart npu-worker
   ```

3. **Verify OpenVINO**
   ```bash
   python3 -c "from openvino.runtime import Core; print(Core().available_devices)"
   ```

**Estimated Recovery Time**: 5-10 minutes

**Fallback**: System automatically falls back to cloud embeddings.

---

### Scenario 6: Browser VM Failure (172.16.168.25)

**Impact**: Browser automation unavailable

**Symptoms**:
- Playwright operations fail
- Browser automation workflows error

**Recovery Steps**:

1. **Check VM and Playwright**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.25
   sudo systemctl status playwright-server
   ```

2. **Restart Playwright**
   ```bash
   sudo systemctl restart playwright-server
   ```

3. **Verify browser**
   ```bash
   npx playwright install chromium
   ```

**Estimated Recovery Time**: 5-15 minutes

---

### Scenario 7: Complete System Failure

**Impact**: All services down

**Recovery Steps**:

1. **Start VMs in order**
   ```powershell
   # On Hyper-V host
   Start-VM -Name "AutoBot-Redis"      # Start first
   Start-VM -Name "AutoBot-AI"
   Start-VM -Name "AutoBot-NPU"
   Start-VM -Name "AutoBot-Browser"
   Start-VM -Name "AutoBot-Frontend"   # Start last
   ```

2. **Wait for VMs to boot** (2-3 minutes)

3. **Start AutoBot**
   ```bash
   cd /home/kali/Desktop/AutoBot
   bash run_autobot.sh --dev
   ```

4. **Verify all services**
   ```bash
   bash run_autobot.sh --status
   ```

**Estimated Recovery Time**: 15-30 minutes

---

## Backup Procedures

### Daily Backups

```bash
#!/bin/bash
# backup_autobot.sh - Run daily via cron

BACKUP_DIR="/backups/autobot/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

# Redis backup
ssh autobot@172.16.168.23 "redis-cli BGSAVE"
sleep 10
scp autobot@172.16.168.23:/var/lib/redis-stack/dump.rdb "$BACKUP_DIR/"

# Configuration backup
cp -r /home/kali/Desktop/AutoBot/.env "$BACKUP_DIR/"
cp -r /home/kali/Desktop/AutoBot/backend/core/config.py "$BACKUP_DIR/"

# Knowledge base metadata
redis-cli -h 172.16.168.23 -n 1 KEYS "doc:*" > "$BACKUP_DIR/kb_keys.txt"

echo "Backup completed: $BACKUP_DIR"
```

### Weekly Backups

- Full VM snapshots via Hyper-V
- Off-site backup of Redis dump
- Git repository backup

---

## Health Monitoring

### Automated Health Checks

```bash
#!/bin/bash
# health_check.sh - Run every 5 minutes via cron

check_service() {
    if ! curl -s --max-time 5 "$1" > /dev/null 2>&1; then
        echo "ALERT: $2 is DOWN at $(date)" | mail -s "AutoBot Alert: $2" admin@example.com
        return 1
    fi
    return 0
}

check_service "http://localhost:8001/api/health" "Backend API"
check_service "http://172.16.168.21:5173" "Frontend"
check_service "http://172.16.168.24:8080/api/tags" "Ollama"

# Redis check
if ! redis-cli -h 172.16.168.23 ping > /dev/null 2>&1; then
    echo "ALERT: Redis is DOWN at $(date)" | mail -s "AutoBot Alert: Redis" admin@example.com
fi
```

### Key Metrics to Monitor

| Service | Metric | Warning Threshold | Critical Threshold |
|---------|--------|-------------------|-------------------|
| Backend | Response time | > 1s | > 5s |
| Redis | Memory usage | > 80% | > 95% |
| Redis | Connected clients | > 100 | > 500 |
| Ollama | Request latency | > 10s | > 30s |
| VMs | CPU usage | > 80% | > 95% |
| VMs | Disk usage | > 80% | > 95% |

---

## Contact Information

| Role | Contact | Escalation Time |
|------|---------|-----------------|
| Primary On-Call | [To be configured] | Immediate |
| Secondary On-Call | [To be configured] | 15 minutes |
| Infrastructure Lead | [To be configured] | 30 minutes |

---

## Post-Incident Review

After any significant outage:

1. **Document the incident**
   - Timeline of events
   - Root cause
   - Actions taken
   - Resolution time

2. **Update procedures**
   - Add new failure scenarios if needed
   - Improve detection if delayed
   - Automate recovery where possible

3. **Preventive measures**
   - Implement additional monitoring
   - Add redundancy if needed
   - Update backup frequency if RPO was missed

---

## Related Documentation

- [Distributed VM Architecture](../adr/001-distributed-vm-architecture.md)
- [Redis Schema](../architecture/redis-schema.md)
- [Infrastructure Deployment](../developer/INFRASTRUCTURE_DEPLOYMENT.md)

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
