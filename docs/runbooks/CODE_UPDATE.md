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
# https://172.16.168.19 → Code Sync → "Update All Nodes"

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
git add autobot-shared/utils/helper.py

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
1. Navigate to `https://172.16.168.19` → **Code Sync**
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
watch -n 5 "curl -sk https://172.16.168.19/api/nodes \
  -H 'Authorization: Bearer ${SLM_TOKEN}' \
  | jq '.[] | {node_id, code_status}'"
```

### 5. Verify

```bash
# Check all nodes are UP_TO_DATE
curl -sk https://172.16.168.19/api/nodes \
  -H "Authorization: Bearer ${SLM_TOKEN}" \
  | jq '.[] | select(.code_status != "UP_TO_DATE") | {node_id, code_status}'
# Expected: empty array

# Check backend health
ssh autobot@172.16.168.19 'curl --insecure https://172.16.168.20:8443/api/health'

# Check frontend
curl -sk https://172.16.168.21/api/health
```

---

## Updating Only autobot-shared

`autobot-shared` is deployed to all backend nodes. When you change shared code:

```bash
# Push the change
git add autobot-shared/
git commit -m "fix(shared): fix redis client (#issue)"
git push

# Hook detects autobot-shared change → marks ALL backend nodes OUTDATED
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
  autobot@172.16.168.19:/opt/autobot/cache/autobot-backend/

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

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Hook doesn't fire | Not installed | `cp scripts/hooks/slm-post-commit .git/hooks/post-commit && chmod +x .git/hooks/post-commit` |
| Nodes stay OUTDATED after push | SLM not notified | Run hook manually: `scripts/hooks/slm-post-commit` |
| Ansible `UNREACHABLE` | SSH key issue | Test: `ssh -i ~/.ssh/autobot_ed25519 autobot@<node-ip> echo ok` |
| Backend takes 6 min after restart | Normal startup (GPUSemanticChunker + ChromaDB) | Wait; check `/var/log/autobot/backend.log` |
| `rsync` wipes `/opt/autobot/data/` | Missing `--exclude` | Never use `--delete` without excludes in sync scripts |
| Node shows wrong commit | Heartbeat overwrote mark-synced | Issue fixed in #918; check `code_version` in DB |

---

## Post-Update Verification Checklist

- [ ] All nodes show `code_status: UP_TO_DATE` in SLM
- [ ] Backend health check returns 200: `curl -sk https://172.16.168.19 'curl --insecure https://172.16.168.20:8443/api/health'`
- [ ] Frontend serves updated build: `curl -sk https://172.16.168.21/ | grep <version-or-feature>`
- [ ] No error spikes in logs: `ssh autobot@172.16.168.20 "tail -50 /var/log/autobot/backend.log" | grep -i error`

---

## Related

- `docs/architecture/UPDATE_FLOWS.md` — flow diagrams for all update channels
- `update-all-nodes.yml` — code update playbook
- `scripts/hooks/slm-post-commit` — post-commit hook
- `docs/runbooks/SYSTEM_UPDATE.md` — OS package updates (separate from code)
