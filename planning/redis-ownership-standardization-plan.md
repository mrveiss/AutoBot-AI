# Redis Ownership Standardization Implementation Plan

**Date:** 2025-10-05
**Status:** Planning Complete - Ready for Implementation
**Total Time Estimate:** ~111 minutes (~2 hours)
**Risk Level:** LOW
**Downtime:** Zero (service restart not required for most changes)

---

## Executive Summary

**Architecture Decision:** Standardize on `autobot:autobot` ownership for Redis Stack service across all AutoBot infrastructure.

**Rationale:**
- Systemd service already configured for `User=autobot` (zero changes needed)
- Maintains AutoBot architectural consistency across all 5 VMs
- Lowest migration risk (no service restart required for most changes)
- Simplest implementation path

**Scope:**
- **Files Affected:** 5 configuration and script files
- **Directories Affected:** 2 Redis directories on VM3 (172.16.168.23)
- **Infrastructure:** Distributed VM setup (main + 5 VMs)

---

## Implementation Phases

### Phase 1: Immediate Fix (8 minutes)
**Critical Path - Start Immediately**

#### Task 1.1: Emergency Ownership Fix on Redis VM
- **Agent:** devops-engineer
- **Time:** 5 minutes
- **Commands:**
  ```bash
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "sudo chown -R autobot:autobot /var/lib/redis-stack"
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "sudo chown -R autobot:autobot /var/log/redis-stack"
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "sudo systemctl restart redis-stack-server"
  ```
- **Success Criteria:** Redis service starts successfully, no permission errors in logs
- **Risk:** Medium - Service restart required (but quick recovery)
- **Mitigation:** Verify service health immediately after restart

#### Task 1.2: Verify Redis Health Post-Fix
- **Agent:** testing-engineer
- **Time:** 3 minutes
- **Commands:**
  ```bash
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "systemctl status redis-stack-server"
  redis-cli -h 172.16.168.23 ping
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "ls -la /var/lib/redis-stack /var/log/redis-stack"
  ```
- **Success Criteria:** Service active, PONG response, `autobot:autobot` ownership confirmed
- **Dependencies:** Task 1.1 complete

---

### Phase 2: Ansible Configuration Updates (25 minutes)
**Persistence Layer - Infrastructure as Code**

#### Task 2.1: Update Ansible Group Variables
- **Agent:** devops-engineer
- **Time:** 5 minutes
- **File:** `/home/kali/Desktop/AutoBot/ansible/inventory/group_vars/database.yml`
- **Changes:**
  ```yaml
  # Line 15-16: Update systemd service configuration
  redis_systemd_user: "autobot"
  redis_systemd_group: "autobot"

  # Line 20-21: Update file ownership
  redis_file_owner: "autobot"
  redis_file_group: "autobot"
  ```
- **Success Criteria:** File updated, syntax valid, changes match standardization decision
- **Risk:** Low - Variable changes only, no immediate impact
- **Dependencies:** Phase 1 complete (need working baseline)

#### Task 2.2: Update Ansible Deploy Database Playbook
- **Agent:** devops-engineer
- **Time:** 5 minutes
- **File:** `/home/kali/Desktop/AutoBot/ansible/playbooks/deploy-database.yml`
- **Changes:**
  ```yaml
  # Line 45-46: Update Redis user/group variables
  redis_user: "autobot"
  redis_group: "autobot"
  ```
- **Success Criteria:** Playbook variables updated, no syntax errors
- **Risk:** Low - Declarative changes only
- **Dependencies:** Task 2.1 complete (maintain variable consistency)

#### Task 2.3: Code Review - Ansible Changes
- **Agent:** code-reviewer (MANDATORY)
- **Time:** 10 minutes
- **Review Focus:**
  - Variable naming consistency
  - Systemd service configuration alignment
  - File permission implications
  - Idempotency of playbook
- **Success Criteria:** Code review passed, no issues identified
- **Dependencies:** Task 2.1 + 2.2 complete

#### Task 2.4: Test Ansible Playbook (Dry Run)
- **Agent:** testing-engineer
- **Time:** 5 minutes
- **Commands:**
  ```bash
  ansible-playbook -i ansible/inventory ansible/playbooks/deploy-database.yml --check --diff
  ```
- **Success Criteria:** Check mode passes, no errors, changes preview looks correct
- **Dependencies:** Task 2.3 complete (reviewed code)

---

### Phase 3: Startup Script Updates (28 minutes)
**Automated Ownership Management**

#### Task 3.1: Update VM Management Start Redis Script
- **Agent:** senior-backend-engineer
- **Time:** 3 minutes
- **File:** `/home/kali/Desktop/AutoBot/scripts/vm-management/start-redis.sh`
- **Changes:**
  ```bash
  # Line 78: Update chown command
  # OLD: chown -R redis:redis /var/lib/redis-stack /var/log/redis-stack
  # NEW: chown -R autobot:autobot /var/lib/redis-stack /var/log/redis-stack
  ```
- **Success Criteria:** Script updated, ownership command uses `autobot:autobot`
- **Risk:** Low - Single line change, no logic modification
- **Dependencies:** Phase 2 complete (Ansible aligned first)

#### Task 3.2: Add Ownership Verification Function to run_autobot.sh
- **Agent:** senior-backend-engineer
- **Time:** 15 minutes
- **File:** `/home/kali/Desktop/AutoBot/run_autobot.sh`
- **Changes:**
  ```bash
  # Add new function after line 200 (in verification section)
  verify_redis_ownership() {
      echo "Verifying Redis ownership..."
      local owner=$(ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "stat -c '%U:%G' /var/lib/redis-stack" 2>/dev/null)
      if [[ "$owner" != "autobot:autobot" ]]; then
          echo "WARNING: Redis ownership mismatch detected: $owner (expected autobot:autobot)"
          echo "Fixing ownership..."
          ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "sudo chown -R autobot:autobot /var/lib/redis-stack /var/log/redis-stack"
          echo "Ownership corrected."
      else
          echo "Redis ownership verified: autobot:autobot"
      fi
  }

  # Add call in startup sequence (after Redis health check, around line 450)
  verify_redis_ownership
  ```
- **Success Criteria:** Function added, properly integrated into startup flow, handles errors gracefully
- **Risk:** Medium - Logic addition to critical startup script
- **Mitigation:** Non-blocking verification (warns but doesn't fail startup)
- **Dependencies:** Task 3.1 complete

#### Task 3.3: Code Review - Startup Script Changes
- **Agent:** code-reviewer (MANDATORY)
- **Time:** 10 minutes
- **Review Focus:**
  - Bash syntax correctness
  - Error handling completeness
  - Startup flow integration
  - SSH command security (key-based auth)
  - Non-blocking behavior (shouldn't prevent startup)
- **Success Criteria:** Code review passed, no security or logic issues
- **Dependencies:** Task 3.1 + 3.2 complete

---

### Phase 4: Testing & Validation (50 minutes)
**End-to-End Verification**

#### Task 4.1: Create Test Plan for Redis Ownership
- **Agent:** testing-engineer
- **Time:** 15 minutes
- **Test Scenarios:**
  1. Fresh startup verification (`run_autobot.sh --dev`)
  2. Ownership auto-correction test (manually break, verify fix)
  3. Service restart validation (ownership persists)
  4. Ansible playbook deployment test (full infrastructure-as-code)
  5. Log file ownership verification
  6. Data directory ownership verification
- **Success Criteria:** Complete test plan documented, all edge cases covered
- **Dependencies:** Phase 3 complete (all code changes done)

#### Task 4.2: Execute Integration Tests
- **Agent:** testing-engineer
- **Time:** 20 minutes
- **Test Commands:**
  ```bash
  # Test 1: Fresh startup
  bash run_autobot.sh --dev --no-browser

  # Test 2: Ownership auto-correction
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "sudo chown -R redis:redis /var/lib/redis-stack"
  bash run_autobot.sh --restart

  # Test 3: Service restart
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "sudo systemctl restart redis-stack-server"
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "stat -c '%U:%G' /var/lib/redis-stack"

  # Test 4: Ansible deployment
  ansible-playbook -i ansible/inventory ansible/playbooks/deploy-database.yml

  # Test 5 & 6: File/directory verification
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "find /var/lib/redis-stack /var/log/redis-stack -not -user autobot -o -not -group autobot"
  ```
- **Success Criteria:** All tests pass, ownership always `autobot:autobot`, no permission errors
- **Dependencies:** Task 4.1 complete

#### Task 4.3: Performance & Stability Validation
- **Agent:** performance-engineer (PARALLEL with Task 4.2)
- **Time:** 15 minutes
- **Validation Points:**
  - Redis response times (baseline vs post-change)
  - Service startup time (no delays)
  - Log file write performance
  - Data persistence operations
- **Success Criteria:** No performance regression, all metrics within baseline
- **Dependencies:** Task 4.2 complete (working system)

---

## Rollback Plan

### Phase-Specific Rollback Procedures

#### Phase 1 Rollback (if Redis fails to start)
- **Agent:** devops-engineer
- **Time:** 3 minutes
- **Commands:**
  ```bash
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "sudo chown -R redis:redis /var/lib/redis-stack /var/log/redis-stack"
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "sudo systemctl restart redis-stack-server"
  ```

#### Phase 2 Rollback (if Ansible playbook breaks)
- **Agent:** devops-engineer
- **Time:** 2 minutes
- **Commands:**
  ```bash
  cd /home/kali/Desktop/AutoBot
  git checkout HEAD -- ansible/inventory/group_vars/database.yml
  git checkout HEAD -- ansible/playbooks/deploy-database.yml
  ```

#### Phase 3 Rollback (if startup script fails)
- **Agent:** senior-backend-engineer
- **Time:** 2 minutes
- **Commands:**
  ```bash
  git checkout HEAD -- scripts/vm-management/start-redis.sh
  git checkout HEAD -- run_autobot.sh
  ```

#### Complete Rollback (nuclear option)
- **Agent:** systems-architect
- **Time:** 5 minutes
- **Commands:**
  ```bash
  git revert <commit-hash> --no-edit
  bash run_autobot.sh --restart
  ```

---

## Risk Assessment & Mitigation

### Risk 1: Service Downtime During Ownership Change
- **Severity:** Low
- **Probability:** Low
- **Mitigation:** Systemd already uses `User=autobot`, no restart needed for most changes
- **Contingency:** Phase 1 rollback script ready

### Risk 2: Data Corruption from Permission Changes
- **Severity:** High
- **Probability:** Very Low
- **Mitigation:** Redis running as autobot can already read/write data
- **Contingency:** Redis data backed up automatically, restore from `dump.rdb`

### Risk 3: Ansible Playbook Breaking Infrastructure
- **Severity:** Medium
- **Probability:** Low
- **Mitigation:** Dry-run testing (Task 2.4), git version control
- **Contingency:** Git revert capability, manual SSH fixes

### Risk 4: Startup Script Logic Errors
- **Severity:** Medium
- **Probability:** Low
- **Mitigation:** Code review mandatory, non-blocking verification function
- **Contingency:** Script continues even if verification fails (warn only)

**Overall Risk Level:** LOW - Comprehensive mitigation strategies in place

---

## Agent Assignments Summary

| Agent | Tasks | Total Time |
|-------|-------|------------|
| **devops-engineer** | Phase 1 (emergency fix), Phase 2 (Ansible updates) | 15 min |
| **senior-backend-engineer** | Phase 3 (startup scripts) | 18 min |
| **testing-engineer** | Phase 1 (verification), Phase 2 (dry run), Phase 4 (testing) | 28 min |
| **code-reviewer** | Phase 2 (Ansible review), Phase 3 (script review) | 20 min |
| **performance-engineer** | Phase 4 (performance validation) | 15 min |
| **systems-architect** | Rollback coordination (if needed) | 0 min (standby) |

**Parallel Execution Opportunities:**
- Phase 4: testing-engineer and performance-engineer can work simultaneously

---

## Success Criteria (Overall Implementation)

1. ✅ Redis service runs with `autobot:autobot` ownership
2. ✅ All Ansible playbooks updated and tested
3. ✅ Startup scripts automatically verify/correct ownership
4. ✅ Zero service downtime during implementation
5. ✅ All tests pass (functionality, performance, stability)
6. ✅ Documentation updated (Memory MCP + system-state.md)
7. ✅ Rollback plan validated and ready

---

## Critical Path Timeline

```
Phase 1: Immediate Fix (8 min)
    ↓
Phase 2: Ansible Updates (25 min)
    ↓
Phase 3: Startup Scripts (28 min)
    ↓
Phase 4: Testing & Validation (50 min)
    ↓
TOTAL: ~111 minutes (~2 hours)
```

---

## Next Steps

1. **Get Implementation Approval** - Review plan with stakeholders
2. **Execute Phase 1** - Emergency ownership fix (8 minutes)
3. **Proceed Sequentially** - Follow critical path through phases
4. **Continuous Monitoring** - Track progress, handle blockers immediately
5. **Final Validation** - Comprehensive testing before completion

---

## Memory MCP Storage

All plan details stored in Memory MCP:
- Entity: `Redis Ownership Standardization Plan 2025-10-05`
- Type: `implementation_plan`
- Related Entities: 6 phase/plan entities with full task details
- Relations: Complete dependency graph established

**Retrieve Plan:**
```bash
mcp__memory__open_nodes --names '["Redis Ownership Standardization Plan 2025-10-05"]'
```

---

**Plan Status:** COMPLETE - Ready for Implementation Phase
**Created:** 2025-10-05
**Last Updated:** 2025-10-05
