# AutoBot Disaster Recovery Procedures

**Last Updated**: 2026-10-24
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
   # The backend runs as the systemd unit autobot-backend
   sudo systemctl status autobot-backend --no-pager

   # Its logs (startup validation runs before the server starts, so a failed start shows here)
   journalctl -u autobot-backend -n 100 --no-pager
   ```

2. **Restart the service**
   ```bash
   sudo systemctl restart autobot-backend
   ```

3. **Verify recovery**
   ```bash
   curl http://localhost:8001/api/health
   ```

**Estimated Recovery Time**: 5-10 minutes

---

### Scenario 2: Frontend Failure (<frontend-ip>)

**Impact**: No web interface, API still functional

The deployed frontend is a production build served by nginx from the frontend role's
`autobot-frontend/current` directory under the install root (`frontend_dist_dir`), on ports 80 and 443.
It is not a Vite dev server.

**Symptoms**:
- `https://<frontend-ip>/` doesn't load, or loads a blank page
- SSH to the frontend role's machine fails

**Recovery Steps**:

1. **If the machine itself is down**, start or restart it from your hypervisor or cloud console, then continue.

2. **Check nginx**
   ```bash
   ssh autobot@<frontend-ip>
   sudo systemctl status nginx --no-pager
   sudo nginx -t                      # a config error stops a reload
   journalctl -u nginx -n 100 --no-pager
   ```

3. **Restart nginx**
   ```bash
   sudo systemctl restart nginx
   ```

4. **If nginx runs but the page is blank or 404**, the build is missing or broken. Rebuild it through
   the builtin updater: the SLM's **Maintenance → Updates → Code Sync** tab, for the frontend node.
   (**System Updates** on the same page is OS packages, not the AutoBot build.) Don't build by hand on the node.

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
   ssh autobot@<database-ip>
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

   Use the SLM: **Backups**, then **Restore** on a completed Redis backup. It stops Redis, puts the
   snapshot in place as `dump.rdb` and starts Redis again (see [Backup and restore](#backup-and-restore)).
   By hand, on the Redis node, with a verified snapshot:
   ```bash
   sudo systemctl stop redis-stack-server
   # Keep the current file aside, never delete it
   sudo mv /var/lib/redis/dump.rdb /var/lib/redis/dump.rdb.before-restore
   sudo cp /path/to/backup/dump.rdb /var/lib/redis/dump.rdb
   sudo chown redis:redis /var/lib/redis/dump.rdb
   sudo systemctl start redis-stack-server
   ```
   `/var/lib/redis` is the redis role's `redis_data_dir`. If your node overrides it, use
   `redis-cli CONFIG GET dir` before stopping Redis.

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
   ssh autobot@<aiml-ip>
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
   ssh autobot@<npu-ip>
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
   ssh autobot@<browser-ip>
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

## Backup and restore

AutoBot has two backup mechanisms. Neither copies off the machine on its own: keep copies elsewhere
yourself (VM snapshots, an off-site copy of the backup directories).

### SLM backups (GUI and API)

The SLM's **Backups** page (`autobot-slm-frontend/src/views/BackupsView.vue`) and its API
(`/api/stateful/backups`, `autobot-slm-backend/api/stateful.py`) back up three services on a node,
**on demand**:

| `service_type` | What is captured | Restore from the SLM |
|---|---|---|
| `redis` | `BGSAVE`, then the node's `dump.rdb` copied to SLM backup storage | **Yes**: **Restore** in the GUI, or `POST /api/stateful/backups/{id}/restore` |
| `postgres` | a `pg_dumpall` of the cluster | No: operator restore |
| `secrets` | an SQLite online snapshot of the backend's `secrets.db` | No: operator restore, [below](#secrets-store-backup-and-restore-18281) |

- Storage: `SLM_BACKUP_DIR` (default `/var/lib/slm/backups`) on the SLM host. Each completed backup
  records a sha256, which `verify_backup_integrity` checks.
- Retention (`services/backup.py` `apply_retention`): after each successful `redis` or `postgres`
  backup, older completed backups of that node and type beyond `SLM_BACKUP_RETENTION_COUNT`
  (default 10) or older than `SLM_BACKUP_RETENTION_DAYS` (default 30) are pruned. Secrets backups are
  never pruned automatically (#17038).
- **No schedule.** Nothing triggers SLM backups periodically. Create them from the Backups page or
  the API, for example before an update.
- Restore is offered for Redis only (#19455). Restoring a PostgreSQL or secrets backup through the
  Redis restore path would overwrite Redis's data, so the SLM refuses it.

**Restoring a `postgres` backup (operator).** The artifact is a gzipped `pg_dumpall --clean --if-exists`.
On the PostgreSQL node, with the backend and SLM services stopped:
```bash
gunzip -c <backup>.sql.gz | sudo -u postgres psql -X postgres 2>&1 | tee /tmp/autobot-restore.log
grep ERROR /tmp/autobot-restore.log
```
Expect exactly two errors, both harmless: `current user cannot be dropped` and
`role "postgres" already exists`. The dump drops and recreates every role, including the one
running the restore. Any other `ERROR` line needs investigating before the services start again.

**Don't add `-v ON_ERROR_STOP=1`.** `--clean` drops each database before recreating it, and the
dump drops roles after that. Stopping on the first error aborts after the databases are already
gone, at `DROP ROLE IF EXISTS postgres`, which leaves no data at all. This was checked on a
PostgreSQL 16 scratch cluster: with the flag the database was dropped and not restored, and
without it the data came back with the two errors above.

`--clean` drops and recreates every database in the dump, so take a fresh backup of the current state first.

### Scheduled PostgreSQL dumps (systemd timer)

The postgresql role installs `autobot-pg-backup.timer`
(`autobot-slm-backend/ansible/roles/postgresql/tasks/backup.yml`), on by default
(`postgresql_backup_enabled`):

- Nightly at `postgresql_backup_on_calendar` (default `*-*-* 02:30:00`, with up to 15 minutes of
  random delay), it writes `postgresql-all-<timestamp>.sql.gz` (`pg_dumpall`) to
  `postgresql_backup_dir` (default `/var/backups/autobot/postgresql`) on the PostgreSQL node.
- It deletes its own dumps older than `postgresql_backup_retention_days` (default 14).
- These dumps are local files. They aren't rows on the SLM's Backups page, and the SLM doesn't restore them.
  Restore one with the `psql` command above.

Check it: `systemctl list-timers autobot-pg-backup.timer` and `journalctl -u autobot-pg-backup.service`.

### Verifying a backup set

`autobot-slm-backend/ansible/verify-backup-restore.yml` restores every artifact into a scratch
directory and checks it (checksums, the PostgreSQL dump, `redis-check-rdb`, archive contents)
without touching live data.

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
