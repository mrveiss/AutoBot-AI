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

### Scenario 1: Main Backend Failure (<backend-ip>)

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
   tail -f logs/backend.log
   ```

2. **Restart the service**
   ```bash
   # Stop existing process
   pkill -f "uvicorn backend.main:app"

   # Start fresh
   cd /opt/autobot
   sudo systemctl start autobot-backend
   ```

3. **Verify recovery**
   ```bash
   curl http://localhost:8001/api/health
   ```

**Estimated Recovery Time**: 5-10 minutes

---

### Scenario 2: Frontend VM Failure (<frontend-ip>)

**Impact**: No web interface, API still functional

**Symptoms**:
- Cannot access `http://<frontend-ip>:5173`
- SSH to the frontend role fails or shows issues

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
   ssh -i ~/.ssh/autobot_key autobot@<frontend-ip>

   # On the frontend role's machine:
   cd /opt/autobot/autobot-slm-frontend
   npm run dev -- --host 0.0.0.0
   ```

4. **Or use startup script from main machine**
   ```bash
   sudo systemctl start autobot-backend
   ```

**Estimated Recovery Time**: 5-15 minutes

---

### Scenario 3: Redis Failure (<database-ip>)

**Impact**: Session loss, knowledge base unavailable, cache miss

**Symptoms**:
- Connection errors in backend logs
- `redis-cli -h <database-ip> ping` fails
- Chat responses very slow or fail

**Recovery Steps**:

1. **Check Redis status**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@<database-ip>
   sudo systemctl status redis-stack-server
   ```

2. **Restart Redis**
   ```bash
   sudo systemctl restart redis-stack-server
   ```

3. **Verify connectivity**
   ```bash
   redis-cli -h <database-ip> ping
   redis-cli -h <database-ip> INFO
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

### Scenario 4: AI Stack Failure (<aiml-ip>)

**Impact**: LLM responses fail, embeddings unavailable

**Symptoms**:
- Chat responses timeout
- `curl http://<aiml-ip>:8080/api/tags` fails
- Backend logs show Ollama connection errors

**Recovery Steps**:

1. **Check Ollama status**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@<aiml-ip>
   sudo systemctl status ollama
   ```

2. **Restart Ollama**
   ```bash
   sudo systemctl restart ollama
   ```

3. **Verify models are loaded**
   ```bash
   curl http://<aiml-ip>:8080/api/tags
   ```

4. **Pull models if missing**
   ```bash
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ```

**Estimated Recovery Time**: 5-20 minutes

**Fallback**: Backend automatically falls back to cloud LLM if configured.

---

### Scenario 5: NPU Worker Failure (<npu-ip>)

**Impact**: Slower embeddings (falls back to cloud/CPU)

**Symptoms**:
- Embedding generation slower
- Backend logs show NPU connection warnings

**Recovery Steps**:

1. **Check NPU worker status**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@<npu-ip>
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

### Scenario 6: Browser VM Failure (<browser-ip>)

**Impact**: Browser automation unavailable

**Symptoms**:
- Playwright operations fail
- Browser automation workflows error

**Recovery Steps**:

1. **Check VM and Playwright**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@<browser-ip>
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
   cd /opt/autobot
   sudo systemctl start autobot-backend
   ```

4. **Verify all services**
   ```bash
   sudo systemctl status autobot-backend --no-pager
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
ssh autobot@<database-ip> "redis-cli BGSAVE"
sleep 10
scp autobot@<database-ip>:/var/lib/redis-stack/dump.rdb "$BACKUP_DIR/"

# Configuration backup
cp -r .env "$BACKUP_DIR/"
cp -r backend/core/config.py "$BACKUP_DIR/"

# Knowledge base metadata
redis-cli -h <database-ip> -n 1 KEYS "doc:*" > "$BACKUP_DIR/kb_keys.txt"

echo "Backup completed: $BACKUP_DIR"
```

### Weekly Backups

- Full VM snapshots via Hyper-V
- Off-site backup of Redis dump
- Git repository backup

---

### Secrets-store backup and restore (#18281)

The secrets store (`secrets.db` in the backend's data directory) is backed up by the SLM backup
service as service type `secrets`: a consistent SQLite online-backup snapshot, copied to SLM backup
storage with a recorded sha256. Create it with `POST /api/stateful/backups`
with `service_type: "secrets"` for the node that carries the backend role; with no such node the
backup is refused and its row is `failed` with the reason.
Old secrets backups are never pruned automatically (no agent deletes stored credential data, #17038).
The snapshot runs on that node as the backend service user (`sudo -n -u`, no password prompt, skipped when the
ssh user already is that user), because the data directory is `0750` to its group. The SLM learns the data
directory and user from `SLM_BACKEND_DATA_DIR` / `SLM_BACKEND_SERVICE_USER`, rendered into its unit from the
backend role's `backend_data_dir` / `backend_user`.

**Only `encrypted_value` is ciphertext.** Secret values stay Fernet-encrypted exactly as stored, but secret
names, descriptions, scopes, metadata and the audit table travel as plaintext in the artifact, so treat the
backup file as sensitive; the key
(`AUTOBOT_SECRETS_KEY`, `security.secrets_key` or `<data_dir>/secrets.key`) is never copied. A restore
therefore works only on a host that holds the **same key**. Without it the snapshot is unreadable.
Key escrow is a separate decision, tracked in #16406.

Restore (operator, on the backend host, with the backend stopped):

1. Confirm the artifact: the backup row must be `completed`, and its sha256 must equal the checksum
   recorded on the row (`verify_backup_integrity`).
2. Keep the current `secrets.db` aside (do not delete it), then place the snapshot at
   `<data_dir>/secrets.db`, owned by the backend service account, mode `0600`.
3. Make sure the same key is in force (the env var, or `<data_dir>/secrets.key`).
4. Start the backend and read one known secret through the secrets API. A decrypt error means the
   key differs from the one that wrote the snapshot.

The OAuth bundle strip (#13630) and any later destructive secrets proposal call one verifier,
`verify_backup`, which accepts a `backup_reference` only for a completed, intact secrets backup newer
than `AUTOBOT_SECRETS_BACKUP_MAX_AGE_S` (default one day), and refuses otherwise.

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
check_service "http://<frontend-ip>:5173" "Frontend"
check_service "http://<aiml-ip>:8080/api/tags" "Ollama"

# Redis check
if ! redis-cli -h <database-ip> ping > /dev/null 2>&1; then
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
