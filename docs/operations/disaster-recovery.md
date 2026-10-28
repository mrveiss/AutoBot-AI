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

### Scenario 4: AI Stack or LLM Failure (<aiml-ip>, LLM node)

**Impact**: LLM responses fail, embeddings unavailable

Two services, deployed by different roles. Check both:

| Service | Unit | Port and health path | Deployed by |
|---|---|---|---|
| Ollama (LLM inference) | `ollama` | `11434`, `/api/version` | `roles/llm` (SLM roles **LLM CPU Node** / **LLM GPU Node**) |
| AI Stack API | `autobot-ai-stack` | `8080`, `/health` | `roles/ai-stack` |
| ChromaDB (the AI Stack starts after it) | `autobot-chromadb` | `8100`, `/api/v2/heartbeat` | `roles/ai-stack` |

**Symptoms**:
- Chat responses time out
- `curl http://<llm-ip>:11434/api/version` fails (Ollama), or `curl http://<aiml-ip>:8080/health` fails (AI Stack)
- Backend logs show Ollama connection errors

**Recovery Steps**:

1. **Check the services**
   ```bash
   ssh autobot@<llm-ip>
   sudo systemctl status ollama --no-pager
   ssh autobot@<aiml-ip>
   sudo systemctl status autobot-chromadb autobot-ai-stack --no-pager
   ```

2. **Restart what is down** (ChromaDB before the AI Stack)
   ```bash
   sudo systemctl restart ollama                              # on the LLM node
   sudo systemctl restart autobot-chromadb autobot-ai-stack   # on the AI Stack node
   ```

3. **Verify the models are present**
   ```bash
   curl http://<llm-ip>:11434/api/tags
   ```
   Compare with the models the role pulls: `llm_cpu_models` on every LLM node and `llm_gpu_models`
   on GPU nodes, both in `autobot-slm-backend/ansible/roles/llm/defaults/main.yml`. That file is
   the list; it is not copied here, so it cannot drift.

4. **If models are missing**, re-run the LLM role through the SLM: the **Roles** page, **Redeploy** on
   **LLM CPU Node** or **LLM GPU Node** for that node. Redeploy re-runs the role's playbook, which pulls
   the models and then checks that each one it meant to pull is present. **Code Sync does not do
   this**: it updates code and never runs the `llm` role. Don't pull by hand on the node.

**Estimated Recovery Time**: 5-20 minutes

**Fallback**: Without an LLM node, inference falls back to cloud providers if any are configured.

---

### Scenario 5: NPU Worker Failure (<npu-ip>)

**Impact**: Slower embeddings (falls back to cloud/CPU)

**Symptoms**:
- Embedding generation slower
- Backend logs show NPU connection warnings
- `curl http://<npu-ip>:8081/health` fails

**Recovery Steps** (unit, port and path from `roles/npu-worker`):

1. **Check NPU worker status**
   ```bash
   ssh autobot@<npu-ip>
   sudo systemctl status autobot-npu-worker --no-pager
   ```

2. **Restart NPU service**
   ```bash
   sudo systemctl restart autobot-npu-worker
   ```

3. **Verify OpenVINO** with the worker's own interpreter, the one its unit runs
   ```bash
   /opt/autobot/autobot-npu-worker/venv/bin/python -c "import openvino.runtime as ov; print(ov.Core().available_devices)"
   ```

**Estimated Recovery Time**: 5-10 minutes

**Fallback**: System automatically falls back to cloud embeddings.

---

### Scenario 6: Browser VM Failure (<browser-ip>)

**Impact**: Browser automation unavailable

**Symptoms**:
- Playwright operations fail
- Browser automation workflows error
- `curl http://<browser-ip>:9001/health` fails (`playwright_port` in `roles/browser/defaults/main.yml`)

**Recovery Steps**:

1. **Check Playwright**
   ```bash
   ssh autobot@<browser-ip>
   sudo systemctl status autobot-playwright --no-pager
   ```

2. **Restart Playwright**
   ```bash
   sudo systemctl restart autobot-playwright
   ```

3. **If Chromium is missing**, re-run the browser role through the SLM: the **Roles** page, **Redeploy**
   on **Browser Automation** for that node. The `browser` role installs Chromium into
   `/var/lib/autobot/playwright-browsers`, the path the service reads. Code Sync reinstalls it only
   when the browser worker's Node.js dependencies changed. A hand-run `npx playwright install chromium`
   installs into the invoking user's cache instead, where the service never looks.

**Estimated Recovery Time**: 5-15 minutes

---

### Scenario 7: Complete System Failure

**Impact**: All services down

**Recovery Steps**:

1. **Power the nodes on in dependency order**, with your hypervisor's own tools (or the host
   itself, on bare metal). The order follows the systemd units' `After=` lines:

   | Order | Node | Units | Why this position |
   |---|---|---|---|
   | 1 | Database node and SLM node | `redis-stack-server`, `postgresql` | `autobot-backend` and `autobot-celery` start `After=redis-stack-server.service` |
   | 2 | AI Stack, LLM, NPU, browser nodes (any order) | `autobot-chromadb` → `autobot-ai-stack`, `ollama`, `autobot-npu-worker`, `autobot-playwright` | Nothing below waits on them at boot, but the backend degrades until they answer |
   | 3 | Backend node | `autobot-backend`, then `autobot-celery` | Celery starts `After=autobot-backend.service` |
   | 4 | Frontend node | `nginx` (`roles/frontend` installs the `autobot-frontend` site) | Serves the UI that calls the backend |

   **Single host** (every role on one machine): power it on. The units are enabled, and systemd
   applies the same `After=` order itself.

2. **Wait for the nodes to boot** (2-3 minutes), then check for units that did not come up:
   ```bash
   systemctl --failed --no-pager
   ```

3. **Start anything that failed**, in the table's order, for example:
   ```bash
   sudo systemctl start autobot-backend
   ```

4. **Verify the backend**
   ```bash
   sudo systemctl status autobot-backend --no-pager
   curl http://localhost:8001/api/health
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
    if ! curl -sk --max-time 5 "$1" > /dev/null 2>&1; then  # -k: the frontend's certificate may be self-signed
        echo "ALERT: $2 is DOWN at $(date)" | mail -s "AutoBot Alert: $2" admin@example.com
        return 1
    fi
    return 0
}

check_service "http://localhost:8001/api/health" "Backend API"
check_service "https://<frontend-ip>/" "Frontend"   # nginx, frontend_port 443 (roles/frontend)
check_service "http://<llm-ip>:11434/api/version" "Ollama"
check_service "http://<aiml-ip>:8080/health" "AI Stack"

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
