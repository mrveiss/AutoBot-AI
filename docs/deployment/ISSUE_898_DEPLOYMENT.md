# Issue #898 Deployment Instructions
## SQLAlchemy Relationship Fixes - Backend Deployment

**Status:** Code fixes complete locally, requires deployment to server

---

## Summary

All SQLAlchemy relationship fixes are implemented and verified:
- ✅ `vnc_manager.py` has `List` imported (line 17)
- ✅ User.user_roles relationship has `foreign_keys` parameter (commit e9abf21a)
- ✅ User.api_keys relationship has `foreign_keys` parameter (commit 852518e1)
- ✅ All 5 activity relationships properly defined
- ✅ Activity models each have single FK to users (no ambiguity)

**The issue is deployment:** Server at `/opt/autobot/` has outdated code.

---

## Pre-Deployment Verification

Run the verification script to confirm code is correct:

```bash
python3 autobot-user-backend/scripts/verify_issue_898.py
```

Expected output:
```
✓ vnc_manager.py: List and Dict imported correctly
✓ Activity models: All 5 models have FK to users
✓ User model: All 5 activity relationships defined
✓ All checks passed - code is correct locally
```

---

## Deployment Steps

### Option 1: Ansible Deployment (Recommended)

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-full.yml --tags backend

# Verify backend restarts successfully
ssh autobot@172.16.168.20 "systemctl status autobot-backend"
```

### Option 2: Manual Sync

```bash
# Sync backend code to server
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-backend/

# SSH to server and restart backend
ssh autobot@172.16.168.20
cd /opt/autobot
sudo systemctl restart autobot-backend

# Check for NameError in logs
journalctl -u autobot-backend -n 100 --no-pager | grep -i "nameerror\|list"
```

---

## Post-Deployment Verification

### 1. Check Backend Startup (No NameError)

```bash
ssh autobot@172.16.168.20 "journalctl -u autobot-backend -n 50 --no-pager"
```

**Expected:** No `NameError: name 'List' is not defined` errors

### 2. Test Backend Health

```bash
curl -sk https://172.16.168.20:8443/api/health | jq
```

**Expected:** `{"status": "healthy"}` or similar

### 3. Test Login (Returns JWT Token)

```bash
curl -sk https://172.16.168.20:8443/api/auth/login \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  | jq
```

**Expected:** JSON response with `access_token` field

### 4. Test Frontend Authentication

```bash
# Check frontend can reach backend
curl -Ik https://172.16.168.21

# Test from frontend to backend
ssh autobot@172.16.168.21 \
  "curl -s http://172.16.168.20:8443/api/health | jq"
```

---

## Troubleshooting

### Backend Still Crashes with NameError

**Symptom:** `NameError: name 'List' is not defined` in logs

**Cause:** Deployment didn't update vnc_manager.py

**Fix:**
```bash
# Verify file on server has List import
ssh autobot@172.16.168.20 \
  "head -20 /opt/autobot/autobot-user-backend/api/vnc_manager.py | grep 'from typing'"
```

Expected output should include: `from typing import Dict, List`

If not, manually copy the file:
```bash
scp autobot-user-backend/api/vnc_manager.py \
  autobot@172.16.168.20:/opt/autobot/autobot-user-backend/api/vnc_manager.py
ssh autobot@172.16.168.20 "sudo systemctl restart autobot-backend"
```

### Login Returns "Could not determine join condition"

**Symptom:** SQLAlchemy error about ambiguous relationships

**Cause:** User relationships missing `foreign_keys` parameter

**Fix:** Verify commits e9abf21a and 852518e1 are deployed:
```bash
ssh autobot@172.16.168.20 \
  "cd /opt/autobot && git log --oneline -10 | grep -E 'e9abf21a|852518e1'"
```

If missing, pull latest code and restart.

### Backend Takes 2-5 Minutes to Accept Connections

**Status:** Under investigation (Issue #898 item 3)

**Current behavior:** Backend shows LISTEN state immediately but refuses connections for 2-5 minutes after restart.

**Workaround:** Wait 5 minutes after restart before testing.

**Note:** This may be a separate issue requiring deeper investigation.

---

## Acceptance Criteria Checklist

After deployment, verify:

- [ ] Backend workers start without NameError
- [ ] All User relationships have explicit `foreign_keys` where needed
- [ ] Login with `admin/admin` returns JWT token successfully
- [ ] Frontend at .21 can authenticate against backend at .20
- [ ] Initialization delay documented (separate issue if persistent)

---

## Related Issues

- **#888** - Backend authentication fixes (parent issue)
- **#868** - Backend crash-looping (resolved)
- **Commits:** e9abf21a (user_roles fix), 852518e1 (api_keys fix)

---

**Document Version:** 1.0
**Last Updated:** 2026-02-16
**Issue:** #898
