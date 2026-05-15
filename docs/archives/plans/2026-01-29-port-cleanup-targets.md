# Port Cleanup Targets for Issue #725

**Related to:** mTLS Service Authentication Migration
**Date:** 2026-01-29

---

## Summary

Remove stale port references (8000, 8090) from main-host and clean up unused configurations before mTLS implementation.

---

## Files Requiring Changes

### 1. Firewall Port Ranges (via SLM/SSOT Config)

**Note:** Ansible inventory files contain template values (192.168.100.0/24). The actual production network (172.16.168.0/24) is configured via SLM and SSOT config.

**Port ranges to clean up via SLM firewall management:**

| Port Range | Location | Action | Reason |
|------------|----------|--------|--------|
| `8000:8099` | all.yml:118 | Replace with specific ports | Only 8001, 8080, 8081 needed |
| `8090:8099` | aiml.yml:363 | Remove | No services use these ports |

**Specific ports needed:**
- 8001 - Backend API (Main Host)
- 8080 - AI Stack API (VM4)
- 8081 - NPU Worker API (VM2)

**TODO markers added to ansible files for tracking.**

**Action:** Update firewall rules through SLM service management UI or API, not direct file edits.

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
- `ansible/roles/slm_agent/files/slm/agent/agent.py:34` - `DEFAULT_ADMIN_URL = "http://${AUTOBOT_SLM_HOST}:8000"`
- `ansible/roles/slm_agent/defaults/main.yml:9` - `slm_admin_url: "http://${AUTOBOT_SLM_HOST}:8000"`
- `slm-server/config.py:32` - `port: int = 8000`
- `scripts/slm-agent-standalone.py:54` - SLM URL

**Note:** These are correct - SLM Server runs on VM0 (${AUTOBOT_SLM_HOST}), not main-host.

---

## Verification Commands

After cleanup, run these on main-host (${AUTOBOT_BACKEND_HOST}):

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

1. **Deprecate root `main.py`** - Rename and add notice ✅
2. **Update test/script references** - Point to `backend/main.py`
3. **Add deprecation notice to `docker/`** - Create DEPRECATED.md ✅
4. **Update firewall rules via SLM** - Remove unused port ranges (separate task)
5. **Verify with commands above**
