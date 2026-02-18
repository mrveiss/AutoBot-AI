# AutoBot Update Flows

> **Status:** Active — implemented in Phase 5 of [#926](https://github.com/mrveiss/AutoBot-AI/issues/926)
> **Implementation:** `autobot-slm-backend/ansible/playbooks/update-all-nodes.yml`

---

## Overview

There are two independent update channels in AutoBot:

1. **Code updates** — push new Python/Vue/config code to fleet nodes
2. **System updates** — `apt upgrade` OS packages on fleet nodes

They use different playbooks, different schedules, and different node-restart policies.

---

## Code Update Flow

### Overview

```
Dev Machine                 SLM Server (.19)              Fleet Node
──────────                  ────────────────              ──────────
git commit
  │
  ▼
post-commit hook
  │
  ├─ detect changed roles
  │   (git diff HEAD~1)
  │
  ├─ rsync changed roles ──────────────────────────────►
  │   to /opt/autobot/cache/                            /opt/autobot/cache/
  │                                                       autobot-backend/
  │                                                       autobot-shared/
  │
  └─ POST /api/code-source/notify ───────────────────►
       { changed_roles, commit_hash }
                                        │
                                        ├─ mark affected nodes OUTDATED
                                        │   (per-role in DB)
                                        │
                                        └─ (optional: auto-update)

Operator: POST /api/updates/trigger ──► Ansible deploy
  or: SLM GUI "Update All"               update-all-nodes.yml
                                            │
                                            ├─ Play 1: SLM self-update (if SLM is in scope)
                                            │   - rsync cache → /opt/autobot/ on .19
                                            │   - restart autobot-slm-backend
                                            │
                                            └─ Play 2: fleet nodes
                                                - rsync cache → /opt/autobot/ on each node
                                                - restart affected services
                                                - POST /api/nodes/{id}/mark-synced
                                                  → node status → UP_TO_DATE
```

### Step-by-Step

**1. Developer pushes code:**

```bash
git add .
git commit -m "feat(backend): add NL-SQL endpoint (#723)"
git push
```

**2. Post-commit hook fires:**

```bash
# scripts/hooks/slm-post-commit
curl -sk -X POST https://172.16.168.19/api/code-source/notify \
  -H "Authorization: Bearer ${SLM_API_TOKEN}" \
  -d '{"commit": "abc123", "changed_roles": ["autobot-backend"]}'
```

**3. SLM marks nodes outdated:**

- `01-Backend` → `OUTDATED` (has `autobot-backend`)
- Other nodes unchanged

**4. Operator triggers update via SLM GUI** (or `POST /api/updates/trigger`).

**5. Ansible runs `update-all-nodes.yml`:**

```
Play 1 (SLM self): if SLM node is in scope
  - rsync autobot-slm-backend/ from cache → /opt/autobot/
  - systemctl restart autobot-slm-backend
  - wait for health check to pass

Play 2 (fleet nodes): all nodes except SLM
  - rsync changed role dirs from cache → /opt/autobot/
  - systemctl restart <role-service>
  - call /api/nodes/{id}/mark-synced with new commit hash
```

**6. Node status → `UP_TO_DATE`:**

- `node_code_versions` DB row updated with commit hash
- SLM dashboard reflects all-green

---

### Per-Role Version Tracking

Each node tracks each role's version independently in `node_code_versions`:

```sql
SELECT node_id, role, commit_hash, updated_at
FROM node_code_versions
WHERE node_id = '01-Backend';
```

A node is `UP_TO_DATE` when all its roles match the latest commit hash in SLM.

---

### Scoped Deploys

To update only one node or role:

```bash
cd autobot-slm-backend/ansible

# One node only
ansible-playbook playbooks/update-all-nodes.yml \
  -i inventory/slm-nodes.yml \
  --limit 02-Frontend

# One role across all nodes (e.g., after changing autobot-shared/)
ansible-playbook playbooks/deploy-full.yml \
  --tags shared
```

---

## System Update Flow (apt)

### Update Policies (from manifests)

Each role declares its system update policy:

| Policy | Nodes | Behavior |
|--------|-------|----------|
| `full` | `.21`, `.25`, `.26`, `.27` | All packages; immediate reboot if needed |
| `security` | `.19`, `.20`, `.22`, `.24` | Security packages only; scheduled reboot |
| `manual` | `.23` | No automatic updates; requires operator action |

### Flow

```
SLM scheduled check (daily, 02:00)
  │
  ├─ apt list --upgradable on each node (via Ansible)
  │
  ├─ compare against update policy
  │
  ├─ if node has pending security updates → alert in SLM dashboard
  ├─ if node has /var/run/reboot-required → alert in SLM dashboard
  │
  └─ for policy=full nodes: auto-apply + reboot (non-peak hours only)

Operator: POST /api/updates/system/{node_id} → Ansible system-update.yml
```

### Playbook

```bash
cd autobot-slm-backend/ansible

# Full system update (respects per-node policy)
ansible-playbook playbooks/system-update.yml -i inventory/slm-nodes.yml

# One node only
ansible-playbook playbooks/system-update.yml \
  -i inventory/slm-nodes.yml \
  --limit 02-Frontend

# Force-full (override policy for emergency patching)
ansible-playbook playbooks/system-update.yml \
  -e "force_full=true" \
  -i inventory/slm-nodes.yml
```

---

## Cert Rotation Flow

### Trigger Conditions

- SLM dashboard alert: any cert < 30 days until expiry
- Manual operator trigger
- Post-incident (cert compromise)
- Annual scheduled rotation

### Flow

```
Operator: ansible-playbook rotate-certs.yml
  │
  ├─ Phase 1: SLM server (.19)
  │   - generate new self-signed cert (or CA-signed via setup-internal-ca.yml)
  │   - backup old cert as server-cert.pem.bak
  │   - nginx graceful reload (zero downtime)
  │
  ├─ Phase 2: Backend (.20)
  │   - generate new cert
  │   - uvicorn restart (brief downtime, ~60s startup)
  │
  └─ Phase 3: Frontend (.21) and other nginx nodes
      - generate new cert
      - nginx graceful reload (zero downtime)

Post-rotation: cert metadata reported to SLM via POST /api/security/certificates/report
  → SLM dashboard Security > TLS Certificates updated
```

---

## SSH Key Rotation Flow

### Rotation Strategy (K0–K6)

```
K0  Generate new key pair on dev machine
K1  Add safety-net key (autobot_admin_temp) to ALL nodes
K2  Verify safety-net key works on ALL nodes      ← abort point if fails
K3  Add new primary key to ALL nodes
K4  Verify new primary key works on ALL nodes     ← abort point if fails
K5  Remove old primary key from ALL nodes
K6  Optionally remove safety-net key (or leave for next window)
```

**Safety guarantee:** If K4 fails, safety-net key from K1 provides access for recovery.

See `docs/runbooks/ROTATE_SSH_KEYS.md` for full procedure.

---

## Role Provisioning Flow (New Node or Re-provision)

### 6-Phase Provisioning

```
Phase 1 — CLEAN
  - Remove legacy dirs from prior role (wrong-node cleanup)
  - Idempotent: skip if already clean

Phase 2 — DEPLOY
  - rsync role code + shared + infra from SLM cache → node
  - Only role-scoped dirs; no full monorepo

Phase 3 — SYSTEM DEPS
  - apt install from manifest.system_dependencies
  - Skip on updates (only run at first provision)

Phase 4 — SECRETS
  - Render .env.j2 templates → /etc/autobot/autobot-<role>.env
  - Mode 640, owned root:<role-user>
  - Per-role Linux service account created if missing

Phase 5 — SERVICES
  - Install systemd unit files (from templates)
  - Enable + start in manifest.start_order
  - Wait for health endpoint to respond

Phase 6 — VERIFY
  - Poll manifest.health.endpoint
  - Report UP_TO_DATE to SLM via /api/nodes/{id}/mark-synced
  - Update node status in SLM DB
```

Updates (code-only) skip Phases 1, 3 — only 2, 4, 5, 6.

---

## SLM Self-Update Flow

SLM server (.19) manages all other nodes — but it also needs to update itself.
`update-all-nodes.yml` handles this with a two-play strategy:

```
Play 1 targets: SLM server ONLY
  - rsync new SLM code from SLM cache → /opt/autobot/
  - restart autobot-slm-backend
  - wait 30s for health check
  → If Play 1 fails: abort entire playbook (don't update broken SLM)

Play 2 targets: ALL OTHER nodes
  - proceed normally
  - SLM is now running new code while deploying to fleet
```

This ensures SLM is never in a broken state when managing fleet nodes.

---

## Monitoring of Update State

All update state is visible in SLM dashboard:

| Location | Shows |
|----------|-------|
| Fleet Overview → Nodes table | Per-node `UP_TO_DATE` / `OUTDATED` / `PENDING` |
| Code Sync page | Commit hashes, last sync time, pending roles |
| System Updates page | Pending apt packages, reboot-required flags |
| Security > TLS Certificates | Days until expiry per node, cert fingerprints |
| Monitoring > Alerts | Active alerts from SLO definitions |

---

## Related

- `docs/runbooks/CODE_UPDATE.md` — step-by-step code update procedure
- `docs/runbooks/SYSTEM_UPDATE.md` — step-by-step system package update procedure
- `docs/runbooks/ROTATE_CERTS.md` — TLS cert rotation procedure
- `docs/runbooks/ROTATE_SSH_KEYS.md` — SSH key rotation procedure
- `docs/runbooks/DEPLOY_NEW_NODE.md` — provision a new fleet node
- `autobot-slm-backend/ansible/playbooks/update-all-nodes.yml` — code update playbook
- `autobot-slm-backend/ansible/playbooks/system-update.yml` — apt update playbook
