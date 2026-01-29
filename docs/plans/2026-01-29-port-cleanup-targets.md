# Port Cleanup Targets for Issue #725

**Related to:** mTLS Service Authentication Migration
**Date:** 2026-01-29

---

## Summary

Remove stale port references (8000, 8090) from main-host and clean up unused configurations before mTLS implementation.

---

## Files Requiring Changes

### 1. `ansible/inventory/group_vars/all.yml` (Line 118)

**Current:**
```yaml
    # Health check endpoints
    - rule: allow
      port: "8000:8099"
      src: "192.168.100.0/24"
```

**Action:** Remove entire block or replace with specific ports needed:
```yaml
    # Health check endpoints
    - rule: allow
      port: 8001
      src: "192.168.100.0/24"
      comment: "Backend API"
```

**Reason:** Port range 8000-8099 is overly broad. Only specific ports should be allowed.

---

### 2. `ansible/inventory/group_vars/aiml.yml` (Lines 361-366)

**Current:**
```yaml
  # Model serving endpoints
  - rule: allow
    port: "8090:8099"
    protocol: tcp
    src: "192.168.100.0/24"
    comment: "Model serving endpoints"
```

**Action:** Remove entire block.

**Reason:** No services use ports 8090-8099. AI Stack uses 8080, NPU Worker uses 8081.

---

### 3. `main.py` (Project Root)

**Current:** Legacy FastAPI application with ~1100 lines

**Action:**
1. Rename to `main.py.deprecated`
2. Add deprecation notice
3. Update any references to use `backend/main.py`

**Reason:**
- Production entry point is `backend/main.py`
- Root `main.py` is legacy code from earlier development
- Causes confusion about which entry point to use

**References to Update:**
- `tests/screenshots/test_security_endpoints.py:26` - Update test to use `backend/main.py`
- `scripts/utilities/settings_diagnostic_utility.py:164` - Update script
- `scripts/utilities/verify_backend_config.py:115` - Update instructions
- `scripts/utilities/fix_settings_loading.py:160` - Update script

---

### 4. `docker/` Directory

**Current:** Contains Docker configurations for services that run natively

**Action:**
1. Create `docker/DEPRECATED.md` explaining these are not used
2. Optionally move to `archive/docker/`

**Reason:** All services run natively via systemd, not Docker.

**Contents:**
- `docker/ai-stack/` - Not used (AI Stack runs natively on VM4)
- `docker/npu-worker/` - Not used (NPU Worker runs natively on VM2)
- `docker/compose/` - Not used

---

### 5. SLM Agent References

**Files with correct 8000 references (NO CHANGE NEEDED):**
- `ansible/roles/slm_agent/files/slm/agent/agent.py:34` - `DEFAULT_ADMIN_URL = "http://172.16.168.19:8000"`
- `ansible/roles/slm_agent/defaults/main.yml:9` - `slm_admin_url: "http://172.16.168.19:8000"`
- `slm-server/config.py:32` - `port: int = 8000`
- `scripts/slm-agent-standalone.py:54` - SLM URL

**Note:** These are correct - SLM Server runs on VM0 (172.16.168.19), not main-host.

---

## Verification Commands

After cleanup, run these on main-host (172.16.168.20):

```bash
# Should return NO results
grep -r "8000" /etc/autobot/ 2>/dev/null
grep -r "8090" /etc/autobot/ 2>/dev/null

# Should show NO listeners on these ports
netstat -tlnp | grep -E ":8000|:8090"
ss -tlnp | grep -E ":8000|:8090"

# Should only show 8001 for backend
netstat -tlnp | grep python
```

---

## Implementation Order

1. **Backup current configs**
2. **Update `ansible/inventory/group_vars/all.yml`** - Remove port range
3. **Update `ansible/inventory/group_vars/aiml.yml`** - Remove 8090-8099 range
4. **Deprecate root `main.py`** - Rename and add notice
5. **Update test/script references** - Point to `backend/main.py`
6. **Add deprecation notice to `docker/`** - Create DEPRECATED.md
7. **Run ansible to apply firewall changes**
8. **Verify with commands above**
