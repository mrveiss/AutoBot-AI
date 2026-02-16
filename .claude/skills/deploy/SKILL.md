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

1. **Verify Infrastructure as Code compliance:**

   **CRITICAL: ALL config changes MUST be in Ansible, not manual VM edits.**

   If the user asks to make config changes directly on VMs, STOP and redirect:

   ```
   ❌ Direct VM config changes are not allowed.

   Instead, follow Infrastructure as Code workflow:
   1. Edit Ansible role/template locally
   2. Commit the change
   3. Deploy via ansible-playbook
   4. Verify change took effect

   This ensures changes are:
   - Version controlled
   - Reproducible
   - Won't be lost on VM rebuild

   Which config do you want to change? I'll show you the correct Ansible file.
   ```

2. **Verify no uncommitted changes:**
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
- **WRONG FIX:** `ssh {target} "mv /opt/autobot/.env /opt/autobot/.env.backup"`
- **RIGHT FIX:** Remove .env from Ansible template or set correct precedence in playbook

**Issue: Wrong Python interpreter**
- **WRONG FIX:** `ssh {target} "cd /opt/autobot && python3 -m venv venv --upgrade-deps"`
- **RIGHT FIX:** Update Ansible role to recreate venv with correct Python

**Issue: Service won't start**
- Check: `ssh {target} "sudo journalctl -u autobot-backend -n 100"`
- Common causes: Port already in use, missing dependencies, config errors
- **FIX:** Update systemd template in Ansible, redeploy

**Issue: Endpoint returns 500**
- Check application logs for stack traces
- Verify database connection and migrations
- Check Redis connectivity
- **FIX:** Update application config in Ansible, redeploy

**Issue: Frontend build errors**
- Verify Node.js version: `ssh {target} "node --version"` (should be 20.x)
- Check build logs: `ssh {target} "cd /opt/autobot && npm run build"`
- **FIX:** Update Node.js installation in Ansible role, redeploy

## Dealing with Manual Changes (Emergency Cleanup)

**If manual changes were made on VMs (against policy):**

1. **Document what was changed:**
   ```bash
   # Compare deployed files against Ansible templates
   ssh {target} "cat /etc/systemd/system/autobot-backend.service" > /tmp/deployed.service
   cat autobot-slm-backend/ansible/roles/backend/templates/autobot-backend.service.j2 > /tmp/template.service
   diff /tmp/deployed.service /tmp/template.service
   ```

2. **Update Ansible to match the manual change:**
   ```bash
   # Edit the Ansible template/config
   vim autobot-slm-backend/ansible/roles/backend/templates/autobot-backend.service.j2

   # Commit the fix
   git add ansible/
   git commit -m "feat(ansible): replicate manual production change to service file

   Manual change made to fix [incident description].
   Now codified in Ansible to prevent configuration drift."
   ```

3. **Deploy Ansible to overwrite manual change:**
   ```bash
   cd autobot-slm-backend/ansible
   ansible-playbook playbooks/deploy-full.yml --tags backend
   ```

4. **Verify Ansible now controls the config:**
   ```bash
   # Compare again - should be identical now
   ssh {target} "cat /etc/systemd/system/autobot-backend.service" > /tmp/deployed.service
   # Process template to compare
   diff /tmp/deployed.service <(ansible all -i inventory -m template -a "src=roles/backend/templates/autobot-backend.service.j2 dest=/tmp/test.service" --limit {target})
   ```

**Configuration Drift Prevention:**

Run this periodically to detect manual changes:

```bash
# Compare all key config files against Ansible
cd autobot-slm-backend/ansible

# Check systemd services
ansible all -m shell -a "md5sum /etc/systemd/system/autobot-*.service"

# Check nginx configs
ansible all -m shell -a "md5sum /etc/nginx/sites-available/autobot*"

# If MD5 sums don't match templates, investigate
```
