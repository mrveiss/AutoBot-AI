> **IP addresses** in this document use role placeholders (e.g. `<backend-ip>`). Replace with your actual VM IPs. See [VM_ROLES.md](../architecture/VM_ROLES.md) for role definitions.

# Runbook: Deploy a Code Update

**Issue #926 Phase 8** | Last updated: 2026-02-18

---

## Overview

This runbook describes how to deploy a code update to the AutoBot fleet after committing changes to the git repository. The update process is role-scoped — only nodes running the affected role(s) are updated.

---

## Prerequisites

- SLM server (`.19`) is running and healthy
- SSH access from dev machine to all target nodes
- `autobot-slm-backend/ansible/` is the working directory
- Post-commit hook is configured (see Quick Reference below)

---

## Quick Reference

```bash
# Standard workflow (hook fires automatically on commit)
git add autobot-backend/some_file.py
git commit -m "feat(backend): description (#issue)"
git push
# → hook detects changed role, notifies SLM, SLM marks nodes OUTDATED

# Trigger update from SLM GUI
# https://<slm-manager-ip> → Code Sync → "Update All Nodes"

# Manual trigger via Ansible
cd autobot-slm-backend/ansible
ansible-playbook playbooks/update-all-nodes.yml -i inventory/slm-nodes.yml

# Single node only
ansible-playbook playbooks/update-all-nodes.yml \
  -i inventory/slm-nodes.yml \
  --limit 01-Backend
```

---

## Standard Code Update Flow

### 1. Commit and Push

```bash
# Stage only changed files (avoid accidental large commits)
git add autobot-backend/api/some_endpoint.py
git add autobot_shared/utils/helper.py

git commit -m "feat(backend): add new API endpoint (#926)"
git push origin Dev_new_gui
```

### 2. Post-Commit Hook Auto-Fires

The hook at `scripts/hooks/slm-post-commit` runs automatically:

- Detects changed role directories via `git diff`
- `rsync`s changed roles to `/opt/autobot/cache/` on SLM (`.19`)
- Calls `POST /api/code-source/notify` with changed roles and commit hash

Expected: SLM marks nodes with the changed role(s) as `OUTDATED`.

**If the hook is not installed:**

```bash
# Install hook
cp scripts/hooks/slm-post-commit .git/hooks/post-commit
chmod +x .git/hooks/post-commit

# Or trigger manually
scripts/hooks/slm-post-commit
```

### 3. Trigger Fleet Update

Via SLM GUI (recommended):
1. Navigate to `https://<slm-manager-ip>` → **Code Sync**
2. Review which nodes are `OUTDATED` and which commit they're on
3. Click **"Update All"** or select individual nodes

Via CLI:

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/update-all-nodes.yml -i inventory/slm-nodes.yml
```

### 4. Monitor Progress

SLM GUI: **Code Sync** page shows real-time Ansible output via WebSocket.

CLI:

```bash
# Watch node status
watch -n 5 "curl -sk https://<slm-manager-ip>/api/nodes \
  -H 'Authorization: Bearer ${SLM_TOKEN}' \
  | jq '.[] | {node_id, code_status}'"
```

### 5. Verify

```bash
# Check all nodes are UP_TO_DATE
curl -sk https://<slm-manager-ip>/api/nodes \
  -H "Authorization: Bearer ${SLM_TOKEN}" \
  | jq '.[] | select(.code_status != "UP_TO_DATE") | {node_id, code_status}'
# Expected: empty array

# Check backend health
ssh autobot@<slm-manager-ip> 'curl --insecure https://<backend-ip>:8443/api/health'

# Check frontend
curl -sk https://<frontend-ip>/api/health
```

---

## Updating Only autobot_shared

`autobot_shared` is deployed to all backend nodes. When you change shared code:

```bash
# Push the change
git add autobot_shared/
git commit -m "fix(shared): fix redis client (#issue)"
git push

# Hook detects autobot_shared change → marks ALL backend nodes OUTDATED
# Then trigger update normally
cd autobot-slm-backend/ansible
ansible-playbook playbooks/update-all-nodes.yml -i inventory/slm-nodes.yml
```

---

## Updating the Frontend

The frontend requires a build step before deployment.

```bash
# After committing frontend changes and pushing
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-full.yml \
  -i inventory/slm-nodes.yml \
  --tags frontend
```

This:
1. Rsyncs `autobot-frontend/` source to `.21`
2. Runs `npm ci && npm run build` on `.21`
3. Copies `dist/` to `/var/www/html/`
4. Nginx serves the new build (no restart needed)

---

## Emergency: Deploy Specific Commit

If you need to roll back to a specific commit:

```bash
# 1. Check out old commit on dev machine
git stash
git checkout <old-commit-hash>

# 2. Rsync to SLM cache manually
rsync -av --exclude='node_modules' --exclude='venv' \
  autobot-backend/ \
  autobot@<slm-manager-ip>:/opt/autobot/cache/autobot-backend/

# 3. Trigger update
cd autobot-slm-backend/ansible
ansible-playbook playbooks/update-all-nodes.yml \
  -i inventory/slm-nodes.yml \
  --limit 01-Backend

# 4. Return to development branch
git checkout Dev_new_gui
git stash pop
```

---

## Recovery when the SLM dashboard itself is unreachable (#15462)

A failed SLM frontend build can leave `/slm/` serving 403 for the whole
dashboard — including the "Update All Nodes" button and the code-sync UI you
would normally use to fix it — while every `autobot-*` service still reports
`active (running)`. The backend API stays reachable throughout; only its UI
is gone.

For that situation, a static, dependency-free recovery page is served
directly by the SLM backend, independent of the frontend build:

```
https://<slm-manager-ip>/slm/api/recovery
```

It shows the backend's own `/api/health` (including the frontend-bundle
probe below), and lets you sign in and trigger the same self-update the
dashboard's "Update All Nodes" button runs — with no build step of its own,
so a broken frontend build cannot take it down too.

A degraded `frontend` field in `/api/health` (`unhealthy: build output has
no index.html — a build failed or was never published`) is the signal that
this is the situation you are in, versus a process actually being down.

---

## Triggering a self-update from the SLM host itself, with no credentials (#15728)

`POST /api/code-sync/self-update` requires an authenticated user — correct
for the network-facing API, but it means routine maintenance run from a
shell already on the box still needs a password every time, which is
exactly the kind of place a credential ends up typed into a script or a
CI job where it shouldn't be.

An operator with a shell on the SLM host has a second, credential-free way
to fire the SAME update — no login, no bearer token, nothing on a command
line to leak into shell history:

```bash
curl -s --unix-socket /run/autobot/slm-self-update.sock \
  -X POST http://localhost/self-update
```

`/run/autobot/slm-self-update.sock` is the **default** path, not a fixed one:
it comes from the `slm_self_update_socket_path` variable in the `slm_manager`
role's defaults, and a deployment may override it. On a host where it has been
overridden the command above targets a socket that does not exist and fails
with a connection error rather than anything explanatory. Confirm the actual
path first:

```bash
systemctl show autobot-slm-self-update.socket -p Listen
```

This reaches a second ASGI listener bound ONLY to a Unix domain socket that
systemd's `autobot-slm-self-update.socket` unit creates and owns. The
socket file's own permissions (root, or a member of the backend's service
group) ARE the access control — the same boundary that already lets that
operator restart every service on the box by hand. Nothing here is a secret
to type, store, or rotate: reachability of the socket IS the credential.

Ansible role `slm_manager`'s `slm_self_update_socket_enabled` (default
`true`) can turn both the socket unit and the backend's `Sockets=` wiring
off for a host that should not carry this surface at all.

This is deliberately NOT a replacement for `/recovery` above: `/recovery`
solves a BROKEN frontend, reachable from any browser, off-host included.
This solves "trigger routine maintenance from a shell that already has
root, without a password" — a different problem, and neither folds into
the other.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Hook doesn't fire | Not installed | `cp scripts/hooks/slm-post-commit .git/hooks/post-commit && chmod +x .git/hooks/post-commit` |
| Nodes stay OUTDATED after push | SLM not notified | Run hook manually: `scripts/hooks/slm-post-commit` |
| Ansible `UNREACHABLE` | SSH key issue | Test: `ssh -i ~/.ssh/autobot_ed25519 autobot@<node-ip> echo ok` |
| Backend takes 6 min after restart | Normal startup (GPUSemanticChunker + ChromaDB) | Wait; check `/var/log/autobot/backend.log` |
| `rsync` wipes `/opt/autobot/data/` | Missing `--exclude` | Never use `--delete` without excludes in sync scripts |
| Node shows wrong commit | Heartbeat overwrote mark-synced | Issue fixed in #918; check `code_version` in DB |
| `/slm/` returns 403, all services green | Frontend build failed/incomplete (#15462) | Use `https://<slm-manager-ip>/slm/api/recovery` — see section above |

---

## Post-Update Verification Checklist

- [ ] All nodes show `code_status: UP_TO_DATE` in SLM
- [ ] Backend health check returns 200: `curl -sk https://<slm-manager-ip> 'curl --insecure https://<backend-ip>:8443/api/health'`
- [ ] Frontend serves updated build: `curl -sk https://<frontend-ip>/ | grep <version-or-feature>`
- [ ] No error spikes in logs: `ssh autobot@<backend-ip> "tail -50 /var/log/autobot/backend.log" | grep -i error`

---

## Related

- `docs/architecture/UPDATE_FLOWS.md` — flow diagrams for all update channels
- `update-all-nodes.yml` — code update playbook
- `scripts/hooks/slm-post-commit` — post-commit hook
- `docs/runbooks/SYSTEM_UPDATE.md` — OS package updates (separate from code)
- `autobot-slm-backend/static/recovery.html` — backend-served recovery page (#15462)
- `autobot-slm-backend/services/local_admin_socket.py` — credential-free local self-update socket (#15728)
