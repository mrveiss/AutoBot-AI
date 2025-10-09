# Access Control Safe Rollout Guide

## Overview

This document provides step-by-step instructions for safely deploying and rolling out the Access Control Enforcement feature (Task 3.4) across AutoBot's distributed 6-VM infrastructure.

**Feature**: Session Ownership Validation  
**Security Impact**: Fixes CVSS 9.1 vulnerability - unauthorized conversation access  
**Rollout Strategy**: Gradual enforcement with three modes (DISABLED → LOG_ONLY → ENFORCED)

---

## Architecture Summary

### Components

1. **Feature Flag Service** (`backend/services/feature_flags.py`)
   - Redis-backed (DB 5 cache)
   - Real-time updates across all VMs
   - Default mode: DISABLED (safe)

2. **Session Ownership Validator** (`backend/security/session_ownership.py`)
   - Validates user owns conversation
   - Integrates with feature flags
   - Supports three enforcement modes

3. **Metrics Collection** (`backend/services/access_control_metrics.py`)
   - Tracks violations in LOG_ONLY mode
   - Stores in Redis DB 4 (metrics)
   - 7-day retention for analysis

4. **Admin API** (`backend/api/feature_flags.py`)
   - Runtime control without restart
   - Admin-only access
   - Metrics dashboard

### Enforcement Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| **DISABLED** | No validation | Initial deployment, development |
| **LOG_ONLY** | Validate + audit, but don't block | Monitoring phase, identify issues |
| **ENFORCED** | Full enforcement, block unauthorized | Production security enforcement |

---

## Safe Rollout Procedure

### Phase 1: Initial Deployment (DISABLED Mode) ⏱️ 30 minutes

**Objective**: Deploy all components with enforcement DISABLED

#### Step 1.1: Verify Code Deployment
```bash
# Ensure all new files are in place
ls -la /home/kali/Desktop/AutoBot/backend/services/feature_flags.py
ls -la /home/kali/Desktop/AutoBot/backend/services/access_control_metrics.py
ls -la /home/kali/Desktop/AutoBot/backend/api/feature_flags.py

# Check updated files
grep -A 3 "feature_flags" /home/kali/Desktop/AutoBot/config/config.yaml
grep "EnforcementMode" /home/kali/Desktop/AutoBot/backend/security/session_ownership.py
```

#### Step 1.2: Deploy to Backend VM
```bash
# Sync to VM4 (AI Stack - main backend)
cd /home/kali/Desktop/AutoBot
./scripts/utilities/sync-to-vm.sh ai-stack backend/services/feature_flags.py /home/autobot/backend/services/
./scripts/utilities/sync-to-vm.sh ai-stack backend/services/access_control_metrics.py /home/autobot/backend/services/
./scripts/utilities/sync-to-vm.sh ai-stack backend/api/feature_flags.py /home/autobot/backend/api/
./scripts/utilities/sync-to-vm.sh ai-stack backend/security/session_ownership.py /home/autobot/backend/security/
./scripts/utilities/sync-to-vm.sh ai-stack config/config.yaml /home/autobot/config/
```

#### Step 1.3: Restart Backend Service
```bash
# SSH to backend VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.24

# Restart backend (or reload via systemd if configured)
cd /home/autobot
pkill -f "uvicorn.*backend.app_factory"
nohup python -m uvicorn backend.app_factory:app --host 0.0.0.0 --port 8080 &

# Exit SSH
exit
```

#### Step 1.4: Verify Deployment
```bash
# Check feature flags status (from main machine)
curl http://172.16.168.24:8080/api/admin/feature-flags/status

# Expected response:
# {
#   "success": true,
#   "data": {
#     "current_mode": "disabled",
#     "history": [],
#     "endpoint_overrides": {},
#     "total_endpoints_configured": 0
#   }
# }
```

**✅ Success Criteria**:
- Backend service running without errors
- Feature flags API responding
- Current mode is `disabled`
- No errors in logs

---

### Phase 2: Enable LOG_ONLY Mode ⏱️ 2 minutes + 24-48 hour monitoring

**Objective**: Enable validation and violation tracking without blocking access

#### Step 2.1: Switch to LOG_ONLY Mode
```bash
# Update enforcement mode via API
curl -X PUT http://172.16.168.24:8080/api/admin/feature-flags/enforcement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "log_only"}'

# Expected response:
# {
#   "success": true,
#   "message": "Enforcement mode updated to log_only",
#   "data": {
#     "new_mode": "log_only",
#     "updated_by": "admin",
#     "updated_at": "2025-10-06T..."
#   }
# }
```

#### Step 2.2: Verify Mode Change
```bash
# Check current mode
curl http://172.16.168.24:8080/api/admin/feature-flags/status

# Should show: "current_mode": "log_only"
```

#### Step 2.3: Monitor for Violations (24-48 hours)

**Monitor Logs**:
```bash
# SSH to backend VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.24

# Tail backend logs for LOG_ONLY violations
tail -f /home/autobot/logs/backend.log | grep "LOG_ONLY MODE"

# Expected output (if violations occur):
# [LOG_ONLY MODE] Unauthorized access: user alice tried to access session abc123... owned by bob
# [LOG_ONLY MODE] Would block access but allowing due to log-only mode
```

**Check Metrics Dashboard** (every 6-12 hours):
```bash
# Get violation statistics
curl http://172.16.168.24:8080/api/admin/access-control/metrics?days=7

# Example response:
# {
#   "success": true,
#   "data": {
#     "total_violations": 15,
#     "period_days": 7,
#     "by_endpoint": {
#       "/api/chat/sessions/{session_id}": 10,
#       "/api/conversation/{session_id}/list": 5
#     },
#     "by_user": {
#       "alice": 8,
#       "bob": 7
#     },
#     "by_day": {
#       "2025-10-06": 15
#     },
#     "current_mode": "log_only"
#   }
# }
```

#### Step 2.4: Analyze Violations

**Questions to answer**:
1. Are violations legitimate (malicious access) or false positives?
2. Which endpoints have the most violations?
3. Which users trigger the most violations?
4. Are there patterns suggesting bugs in ownership tracking?

**Common False Positives**:
- Session transfer between users (legitimate sharing)
- Legacy sessions with no owner (migration issue)
- Multi-user access to shared resources

**Action Items**:
- If false positives found: Fix ownership tracking logic
- If legitimate violations: Prepare for enforcement
- If uncertain: Extend monitoring period

**✅ Success Criteria**:
- 24-48 hours of monitoring completed
- Violation patterns understood
- False positives identified and fixed
- Team confident in enforcement

---

### Phase 3: Gradual ENFORCED Rollout ⏱️ 1-3 days

**Objective**: Gradually enable full enforcement per-endpoint or globally

#### Option A: Global Enforcement (Recommended if no false positives)

```bash
# Switch entire system to ENFORCED mode
curl -X PUT http://172.16.168.24:8080/api/admin/feature-flags/enforcement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "enforced"}'
```

#### Option B: Per-Endpoint Gradual Rollout (Recommended if high-risk)

```bash
# Enable enforcement for safest endpoint first
curl -X PUT "http://172.16.168.24:8080/api/admin/feature-flags/endpoint//api/chat/sessions/{session_id}/export" \
  -H "Content-Type: application/json" \
  -d '{"mode": "enforced"}'

# Monitor for 4-6 hours, then enable next endpoint
curl -X PUT "http://172.16.168.24:8080/api/admin/feature-flags/endpoint//api/chat/sessions/{session_id}" \
  -H "Content-Type: application/json" \
  -d '{"mode": "enforced"}'

# Continue until all endpoints enforced, then set global mode
curl -X PUT http://172.16.168.24:8080/api/admin/feature-flags/enforcement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "enforced"}'
```

#### Step 3.2: Monitor Enforcement

**Watch for Blocked Access**:
```bash
# SSH to backend VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.24

# Monitor for blocked access (403 errors)
tail -f /home/autobot/logs/backend.log | grep "403\|Unauthorized access"
```

**Check Audit Logs**:
```bash
# Query audit logs for denied access
# (Audit logs are in Redis DB 10, accessible via audit API if implemented)
```

#### Step 3.3: Rollback if Needed

**If issues occur, immediately rollback**:
```bash
# Emergency rollback to LOG_ONLY
curl -X PUT http://172.16.168.24:8080/api/admin/feature-flags/enforcement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "log_only"}'

# Or complete disable
curl -X PUT http://172.16.168.24:8080/api/admin/feature-flags/enforcement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "disabled"}'
```

**Rollback triggers**:
- Legitimate users blocked from their own sessions
- Critical workflow broken
- Unexpected 403 errors
- User complaints

**✅ Success Criteria**:
- No legitimate users blocked
- Only actual unauthorized access denied
- Audit logs show expected denials
- System stable for 72 hours

---

## Monitoring & Maintenance

### Daily Health Checks

```bash
# Check current enforcement mode
curl http://172.16.168.24:8080/api/admin/feature-flags/status

# View violation metrics (if in LOG_ONLY)
curl http://172.16.168.24:8080/api/admin/access-control/metrics?days=1

# Check backend logs for errors
ssh -i ~/.ssh/autobot_key autobot@172.16.168.24 \
  "tail -100 /home/autobot/logs/backend.log | grep -i error"
```

### Weekly Metrics Review

```bash
# Get 7-day violation statistics
curl http://172.16.168.24:8080/api/admin/access-control/metrics?days=7&include_details=true

# Analyze trends:
# - Are violations increasing or decreasing?
# - New violation patterns?
# - False positives creeping in?
```

### Monthly Cleanup

```bash
# Clean up old metrics (automatic via Redis TTL, but can force)
curl -X POST http://172.16.168.24:8080/api/admin/access-control/cleanup
```

---

## Troubleshooting

### Issue: Feature Flags Not Working

**Symptoms**: Mode changes don't take effect

**Diagnosis**:
```bash
# Check Redis connection
redis-cli -h 172.16.168.23 -p 6379 ping

# Check if flag is stored in Redis
redis-cli -h 172.16.168.23 -p 6379 -n 5 get "feature_flag:access_control:enforcement_mode"
```

**Solution**:
```bash
# Manually set in Redis
redis-cli -h 172.16.168.23 -p 6379 -n 5 set "feature_flag:access_control:enforcement_mode" "log_only"

# Restart backend to reload
ssh -i ~/.ssh/autobot_key autobot@172.16.168.24 "pkill -f uvicorn; cd /home/autobot && nohup python -m uvicorn backend.app_factory:app --host 0.0.0.0 --port 8080 &"
```

### Issue: Metrics Not Recording

**Symptoms**: Violation metrics always show 0

**Diagnosis**:
```bash
# Check Redis metrics DB
redis-cli -h 172.16.168.23 -p 6379 -n 4 keys "violations:*"

# Should show keys like:
# violations:daily:2025-10-06
# violations:by_endpoint:2025-10-06
# violations:by_user:2025-10-06
```

**Solution**:
```bash
# Check metrics service initialization in logs
ssh -i ~/.ssh/autobot_key autobot@172.16.168.24 \
  "grep -i 'metrics.*initialized' /home/autobot/logs/backend.log"

# If not initialized, restart backend
```

### Issue: False Positives in LOG_ONLY

**Symptoms**: Legitimate users showing up as violations

**Common Causes**:
1. **Session ownership not set on creation** - Check session creation endpoints
2. **Session ID mismatch** - Verify session IDs match between request and storage
3. **Case sensitivity** - Username comparison might be case-sensitive

**Fix**:
```python
# In backend/security/session_ownership.py
# Add case-insensitive comparison (if needed):
if stored_owner.lower() != username.lower():
    # Handle violation
```

### Issue: Performance Degradation

**Symptoms**: Slow API responses after enabling enforcement

**Diagnosis**:
```bash
# Check feature flag cache hit rate
# (Would need to add stats endpoint)
curl http://172.16.168.24:8080/api/admin/feature-flags/stats
```

**Solution**:
- Feature flag service has local caching (5-second TTL)
- If cache misses high, increase TTL in config.yaml
- Check Redis DB 5 performance

---

## Testing Before Production

### Test Scenario 1: DISABLED Mode
```bash
# 1. Set mode to disabled
curl -X PUT http://172.16.168.24:8080/api/admin/feature-flags/enforcement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "disabled"}'

# 2. Try accessing someone else's session (should succeed)
curl http://172.16.168.24:8080/api/chat/sessions/test-session-id \
  -H "Authorization: Bearer <user-token>"

# Expected: 200 OK (access allowed)
```

### Test Scenario 2: LOG_ONLY Mode
```bash
# 1. Set mode to log_only
curl -X PUT http://172.16.168.24:8080/api/admin/feature-flags/enforcement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "log_only"}'

# 2. Try accessing someone else's session (should succeed but log violation)
curl http://172.16.168.24:8080/api/chat/sessions/test-session-id \
  -H "Authorization: Bearer <user-token>"

# Expected: 200 OK (access allowed, but violation logged)

# 3. Check metrics increased
curl http://172.16.168.24:8080/api/admin/access-control/metrics?days=1

# Expected: total_violations > 0
```

### Test Scenario 3: ENFORCED Mode
```bash
# 1. Set mode to enforced
curl -X PUT http://172.16.168.24:8080/api/admin/feature-flags/enforcement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "enforced"}'

# 2. Try accessing someone else's session (should fail)
curl http://172.16.168.24:8080/api/chat/sessions/test-session-id \
  -H "Authorization: Bearer <user-token>"

# Expected: 403 Forbidden

# 3. Try accessing own session (should succeed)
curl http://172.16.168.24:8080/api/chat/sessions/my-session-id \
  -H "Authorization: Bearer <user-token>"

# Expected: 200 OK
```

---

## Rollback Plan

### Emergency Rollback (< 2 minutes)

**If major issues occur during any phase:**

```bash
# IMMEDIATE: Set mode to DISABLED
curl -X PUT http://172.16.168.24:8080/api/admin/feature-flags/enforcement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "disabled"}'

# Verify rollback
curl http://172.16.168.24:8080/api/admin/feature-flags/status

# Expected: "current_mode": "disabled"
```

**No restart required** - Feature flags update in real-time across all VMs

---

## Success Metrics

### Phase 1 (DISABLED) Success:
- ✅ All components deployed without errors
- ✅ Feature flags API responding
- ✅ No impact on existing functionality

### Phase 2 (LOG_ONLY) Success:
- ✅ Violations tracked accurately
- ✅ No false positives blocking work
- ✅ Violation patterns understood
- ✅ 24-48 hours of clean monitoring

### Phase 3 (ENFORCED) Success:
- ✅ Only unauthorized access blocked
- ✅ Legitimate users unaffected
- ✅ 72 hours of stable operation
- ✅ Audit logs show expected denials
- ✅ CVSS 9.1 vulnerability mitigated

---

## Maintenance

### Weekly Tasks
- Review violation metrics
- Check for new false positive patterns
- Verify audit logs are clean

### Monthly Tasks
- Review enforcement mode history
- Clean up old metrics (automatic)
- Validate ownership tracking accuracy

### Quarterly Tasks
- Security audit of access control
- Review and update documentation
- Performance optimization if needed

---

## Contact & Escalation

**For Issues During Rollout**:
1. Immediately rollback to DISABLED mode
2. Capture error logs and metrics
3. Review troubleshooting section
4. Document issue for future reference

**Rollout Timeline Summary**:
- **Phase 1 (DISABLED)**: 30 minutes
- **Phase 2 (LOG_ONLY)**: 24-48 hours monitoring
- **Phase 3 (ENFORCED)**: 1-3 days gradual rollout
- **Total**: 3-5 days for complete safe rollout

**Next Steps After Successful Rollout**:
- Apply ownership validation to remaining endpoints
- Implement frontend UI for admin feature flag management
- Add automated alerting for violation spikes
- Plan backfill of legacy session ownership data
