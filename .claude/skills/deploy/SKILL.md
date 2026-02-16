---
name: deploy
description: Deploy code to remote servers with comprehensive verification
---

# Deploy to Remote Server

Complete deployment workflow from local machine to remote VMs with mandatory verification steps to prevent cascading failures.

## Supported Targets

- `main` - User backend (172.16.168.20:8001)
- `frontend` - User frontend (172.16.168.21:443)
- `slm` - SLM backend + frontend (172.16.168.19:443)
- `npu` - NPU worker (172.16.168.22:8081)
- `browser` - Browser worker (172.16.168.25:3000)

## Pre-Flight Checks (MANDATORY - run first)

Before deploying anything:

1. **Verify no uncommitted changes:**
   ```bash
   git status
   ```
   - If uncommitted changes exist, ask user: commit first or deploy anyway?

2. **Run local linting/type checks:**

   For **backend** changes:
   ```bash
   ruff check autobot-user-backend/  # or autobot-slm-backend/
   ```

   For **frontend** changes:
   ```bash
   cd autobot-user-frontend && npm run type-check && npm run lint
   # or cd autobot-slm-frontend && npm run type-check && npm run lint
   ```

   For **Ansible** changes:
   ```bash
   cd autobot-slm-backend/ansible
   ansible-playbook playbooks/<playbook>.yml --syntax-check
   ```

   - If ANY checks fail, STOP - fix locally before deploying

3. **Confirm deployment target:**
   - Ask user to confirm: "Deploy to {target} server ({IP})?"
   - Verify SSH access: `ssh autobot@{target_ip} echo "Connected"`

## Deployment Phase

4. **Choose deployment method:**

   **Method A: Ansible (PREFERRED for production)**
   ```bash
   cd autobot-slm-backend/ansible

   # Full deployment
   ansible-playbook playbooks/deploy-full.yml

   # Specific service
   ansible-playbook playbooks/deploy-full.yml --tags backend
   ansible-playbook playbooks/deploy-full.yml --tags frontend

   # Specific node
   ansible-playbook playbooks/deploy-full.yml --limit slm_server
   ```

   **Method B: Manual rsync (for quick iterations)**
   ```bash
   # Backend
   ./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-backend/

   # Frontend
   ./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-user-frontend/

   # SLM
   ./infrastructure/shared/scripts/sync-to-vm.sh slm autobot-slm-backend/
   ./infrastructure/shared/scripts/sync-to-vm.sh slm autobot-slm-frontend/

   # NPU
   ./infrastructure/shared/scripts/sync-to-vm.sh npu autobot-npu-worker/

   # Browser
   ./infrastructure/shared/scripts/sync-to-vm.sh browser autobot-browser-worker/
   ```

5. **Verify sync completed:**
   ```bash
   # Check file timestamps on remote
   ssh autobot@{target_ip} "ls -lht /opt/autobot/ | head -10"
   ```
   - If timestamps don't match, rsync failed - STOP and investigate

## Verification Phase (MANDATORY - all 6 checks)

**CRITICAL: Only proceed if ALL six checks pass. If ANY fails, STOP and fix immediately.**

### Check 1: No .env Override Conflicts

```bash
ssh autobot@{target_ip} "grep -E '(HOST|PORT|PASSWORD)' /opt/autobot/.env 2>/dev/null || echo 'No .env found'"
```

- ✅ PASS: No .env file OR .env doesn't override dynamic config
- ❌ FAIL: .env has static values that should be dynamic → Remove conflicting entries

### Check 2: Correct Python Interpreter

```bash
ssh autobot@{target_ip} "which python3 && /opt/autobot/venv/bin/python --version"
```

- ✅ PASS: Points to venv Python with correct version (3.10+ for Ubuntu 22.04)
- ❌ FAIL: Wrong path or version → Fix venv or activate correct Python

### Check 3: Database Migrations Current

```bash
ssh autobot@{target_ip} "cd /opt/autobot && source venv/bin/activate && alembic current 2>&1 | head -5"
```

- ✅ PASS: Shows current migration HEAD
- ❌ FAIL: Migration mismatch or error → Run migrations before restarting

### Check 4: Service Actually Restarted

```bash
ssh autobot@{target_ip} "sudo systemctl restart autobot-backend && sleep 3 && sudo systemctl status autobot-backend --no-pager"
```

Then check startup logs:
```bash
ssh autobot@{target_ip} "sudo journalctl -u autobot-backend -n 50 --no-pager | tail -20"
```

- ✅ PASS: Service shows "active (running)" AND logs show successful startup
- ❌ FAIL: Service failed OR logs show errors → Fix startup issues

### Check 5: Endpoints Responding Correctly

```bash
# Health check
curl -s http://{target_ip}:8001/api/health | jq

# Service-specific endpoints (adjust per service)
curl -s https://172.16.168.19/api/nodes | jq '.[] | .status'
```

- ✅ PASS: Endpoints return expected responses (200 OK with valid JSON)
- ❌ FAIL: Errors, 500s, or wrong responses → Check application logs

### Check 6: No Errors in Recent Logs

```bash
ssh autobot@{target_ip} "sudo journalctl -u autobot-backend --since '30 seconds ago' | grep -i error || echo 'No errors found'"
```

- ✅ PASS: No error messages in logs
- ❌ FAIL: Errors present → Investigate and fix

## Post-Deployment

7. **Verify full functionality:**
   - For backend: Test 2-3 critical API endpoints
   - For frontend: Load UI in browser, check console for errors
   - For workers: Verify worker registration and health

8. **Document deployment:**
   ```bash
   git log --oneline -1
   echo "Deployed commit $(git rev-parse --short HEAD) to {target} at $(date)"
   ```

9. **Store in memory:**
   - Use `mcp__memory__create_entities` to record:
     - What was deployed
     - Which server/service
     - Any issues encountered
     - Verification results

## Guardrails

**If ANY verification check fails:**
- ❌ DO NOT continue to next check
- ❌ DO NOT deploy more changes on top
- ✅ DO stop and fix the issue immediately
- ✅ DO re-run ALL six checks after fixing

**If deployment breaks production:**
- Rollback: `git revert {commit}` → redeploy previous working version
- Document incident in memory MCP
- Create GitHub issue for root cause analysis

**If unsure about deployment method:**
- Ask user: "Use Ansible (production) or manual rsync (quick iteration)?"
- When in doubt, prefer Ansible for consistency

## Success Criteria

✅ All pre-flight checks passed (linting, type checks, uncommitted work)
✅ Code synced to remote server (verified timestamps)
✅ All 6 deployment verification checks passed
✅ Service restarted successfully (verified in logs)
✅ Endpoints responding correctly
✅ No errors in recent logs
✅ Full functionality verified
✅ Deployment documented in memory MCP

## Common Issues & Fixes

**Issue: .env overriding dynamic config**
- Fix: `ssh {target} "mv /opt/autobot/.env /opt/autobot/.env.backup"`

**Issue: Wrong Python interpreter**
- Fix: `ssh {target} "cd /opt/autobot && python3 -m venv venv --upgrade-deps"`

**Issue: Service won't start**
- Check: `ssh {target} "sudo journalctl -u autobot-backend -n 100"`
- Common causes: Port already in use, missing dependencies, config errors

**Issue: Endpoint returns 500**
- Check application logs for stack traces
- Verify database connection and migrations
- Check Redis connectivity

**Issue: Frontend build errors**
- Verify Node.js version: `ssh {target} "node --version"` (should be 20.x)
- Check build logs: `ssh {target} "cd /opt/autobot && npm run build"`
