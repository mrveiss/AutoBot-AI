# Backend Crash-Loop Fix Playbooks

Quick reference for resolving backend service issues (Issue #893).

## Workflow

```
1. Run diagnostics  →  2. Identify root cause  →  3. Apply fix  →  4. Verify
```

## Playbook Selection Guide

### 1. Diagnostic Playbook (Always Run First)

**`diagnose-backend-crash.yml`**
- Collects all diagnostic data
- Identifies root cause
- No changes made to system

```bash
ansible-playbook playbooks/diagnose-backend-crash.yml
```

**Review output at:** `/tmp/backend-diagnostics-<timestamp>/`

---

## Fix Playbooks (Based on Root Cause)

### 2a. Fix Symlink Issues

**`fix-backend-symlink.yml`**

**Use when diagnostics show:**
- Import errors mentioning `backend.models`, `backend.services`
- "No module named 'backend'" errors
- Conflict between Issue #891 and #886

**Options:**

```bash
# Remove symlink (Issue #891 approach - no symlink, PYTHONPATH only)
ansible-playbook playbooks/fix-backend-symlink.yml -e "symlink_action=remove"

# Restore symlink (Issue #886 approach - symlink automation)
ansible-playbook playbooks/fix-backend-symlink.yml -e "symlink_action=restore"
```

**Decision matrix:**
- **Remove** if: Imports use absolute paths (`from backend.X`)
- **Restore** if: Imports need symlink (`from models.X` patterns exist)

---

### 2b. Fix Environment Configuration

**`fix-backend-environment.yml`**

**Use when diagnostics show:**
- `.env` file not found
- PYTHONPATH errors
- `ModuleNotFoundError` for local modules
- Conda environment issues

**Fixes:**
- Corrects `.env` path in systemd service
- Updates PYTHONPATH to include all required directories
- Verifies conda environment
- Tests imports

```bash
ansible-playbook playbooks/fix-backend-environment.yml
```

---

### 2c. Clean Restart

**`fix-backend-clean-restart.yml`**

**Use when:**
- Other fixes completed
- Service stuck in crash-loop
- Need to clear stale processes/cache
- Log files too large

**Actions:**
- Kills all backend processes
- Clears Python bytecode cache
- Rotates large log files
- Clean startup with verification
- Health check

```bash
ansible-playbook playbooks/fix-backend-clean-restart.yml
```

---

## Common Scenarios

### Scenario 1: Import Errors

```bash
# 1. Diagnose
ansible-playbook playbooks/diagnose-backend-crash.yml

# 2. Check 09-import-test.txt - if "No module named 'backend'"
ansible-playbook playbooks/fix-backend-symlink.yml -e "symlink_action=restore"

# 3. Restart cleanly
ansible-playbook playbooks/fix-backend-clean-restart.yml
```

### Scenario 2: Environment Misconfiguration

```bash
# 1. Diagnose
ansible-playbook playbooks/diagnose-backend-crash.yml

# 2. Check 08-environment.txt - if .env missing or wrong PYTHONPATH
ansible-playbook playbooks/fix-backend-environment.yml

# 3. Verify
ansible-playbook playbooks/fix-backend-clean-restart.yml
```

### Scenario 3: Unknown Cause

```bash
# 1. Diagnose
ansible-playbook playbooks/diagnose-backend-crash.yml

# 2. Try environment fix (most common)
ansible-playbook playbooks/fix-backend-environment.yml

# 3. If still failing, try symlink removal
ansible-playbook playbooks/fix-backend-symlink.yml -e "symlink_action=remove"

# 4. Clean restart
ansible-playbook playbooks/fix-backend-clean-restart.yml

# 5. If still failing, escalate to GitHub issue #893 with diagnostic output
```

---

## Verification After Fix

All fix playbooks automatically verify the fix, but you can manually check:

```bash
# Check service status
ansible autobot-backend -m shell -a "systemctl status autobot-backend --no-pager"

# Check if listening on port
ansible autobot-backend -m shell -a "ss -tlnp | grep 8443"

# Test health endpoint
ansible autobot-backend -m shell -a "curl -s http://localhost:8443/api/health"

# Monitor logs
ansible autobot-backend -m shell -a "journalctl -u autobot-backend -n 50 --no-pager"
```

---

## Related Issues

- **#893** - Backend service configuration issues (parent issue)
- **#891** - Fix infinite import loops (symlink removal)
- **#886** - WSL2 symlink automation (symlink restoration)

---

## Troubleshooting

**If all playbooks fail:**

1. Check if backend can run manually:
   ```bash
   ssh autobot@172.16.168.20
   cd /opt/autobot/autobot-user-backend
   source /home/autobot/miniconda3/envs/autobot-backend/bin/activate
   uvicorn main:app --host 0.0.0.0 --port 8443
   ```

2. Look for specific error messages in:
   - `/var/log/autobot/backend-error.log`
   - `journalctl -u autobot-backend -n 200`

3. Post findings to Issue #893 with diagnostic output

---

## Quick Reference

| Problem | Playbook | Command |
|---------|----------|---------|
| Don't know cause | `diagnose-backend-crash.yml` | `ansible-playbook playbooks/diagnose-backend-crash.yml` |
| Import errors | `fix-backend-symlink.yml` | `ansible-playbook playbooks/fix-backend-symlink.yml -e "symlink_action=restore"` |
| Environment issues | `fix-backend-environment.yml` | `ansible-playbook playbooks/fix-backend-environment.yml` |
| Need clean restart | `fix-backend-clean-restart.yml` | `ansible-playbook playbooks/fix-backend-clean-restart.yml` |
