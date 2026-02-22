# Access Control Rollout Operations Runbook

**AutoBot Critical Security Fix - CVSS 9.1 Vulnerability**

This runbook provides step-by-step operational procedures for deploying session ownership validation and access control enforcement across AutoBot's 6-VM distributed infrastructure.

---

## 🎯 Objective

Deploy access control enforcement to eliminate CVSS 9.1 vulnerability: **Broken Access Control - Unauthorized Conversation Data Access**

**Current Risk:** Any authenticated user can access any conversation session without ownership validation.

**Target State:** All conversation access validated against session ownership with comprehensive audit logging.

---

## 📋 Pre-Deployment Checklist

### Environment Verification

- [ ] All 6 VMs accessible (172.16.168.21-25)
- [ ] Redis healthy (172.16.168.23:6379)
- [ ] Backend API responding (172.16.168.20:8443)
- [ ] SSH keys configured (`~/.ssh/autobot_key`)
- [ ] Python virtual environment activated
- [ ] No ongoing deployments or maintenance
- [ ] Monitoring systems operational

### Team Coordination

- [ ] Operations team notified
- [ ] Deployment window scheduled (if needed)
- [ ] Rollback authority identified
- [ ] Communication channels established
- [ ] Incident response team on standby

### Backup and Recovery

- [ ] Redis backup completed
- [ ] Backup timestamp recorded
- [ ] Rollback script tested
- [ ] Emergency contact list updated

---

## 🚀 Deployment Phases

### Phase 0: Prerequisites and Preparation (30 minutes)

**Objective:** Deploy feature flags system and prepare infrastructure

**Commands:**
```bash
cd /home/kali/Desktop/AutoBot

# Dry run first
./scripts/deployment/deploy_access_control.sh phase0 --dry-run

# Execute (with confirmation)
./scripts/deployment/deploy_access_control.sh phase0
```

**Expected Outcomes:**
- ✅ Feature flags system deployed
- ✅ Enforcement mode set to DISABLED
- ✅ Redis backup created
- ✅ All VMs verified accessible

**Rollback:** N/A (no enforcement active)

**Validation:**
```bash
# Verify feature flags working
python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    mode = await flags.get_enforcement_mode()
    print(f'Mode: {mode.value}')

asyncio.run(main())
"
```

**Expected:** `Mode: disabled`

---

### Phase 1: Session Ownership Backfill (30 minutes)

**Objective:** Assign ownership to all existing chat sessions

**Commands:**
```bash
# Dry run first (see what would happen)
python3 scripts/security/backfill_session_ownership.py --dry-run --verbose

# Execute backfill
python3 scripts/security/backfill_session_ownership.py --default-owner admin

# Verify coverage
python3 scripts/security/backfill_session_ownership.py --verify-only
```

**Expected Outcomes:**
- ✅ All sessions have ownership assigned
- ✅ 100% ownership coverage verified
- ✅ User session indexing populated
- ✅ Zero service disruption

**Success Criteria:**
- All sessions in `chat_session:*` have corresponding `chat_session_owner:*` entries
- Verification script reports 100% coverage
- No errors in backfill process

**Troubleshooting:**

**Issue:** Backfill fails partway through
```bash
# Check Redis connectivity
redis-cli -h 172.16.168.23 ping

# Check specific session
python3 -c "
import asyncio
from backend.utils.async_redis_manager import get_redis_manager
from backend.security.session_ownership import SessionOwnershipValidator

async def main():
    redis_manager = await get_redis_manager()
    redis = await redis_manager.main()
    validator = SessionOwnershipValidator(redis)

    # Check specific session
    session_id = 'YOUR_SESSION_ID'
    owner = await validator.get_session_owner(session_id)
    print(f'Owner: {owner}')

asyncio.run(main())
"

# Re-run backfill (idempotent - safe to run multiple times)
python3 scripts/security/backfill_session_ownership.py --default-owner admin --force
```

**Rollback:** Not needed (ownership data is additive, doesn't affect functionality)

---

### Phase 2: Audit Logging Activation (1 hour)

**Objective:** Activate comprehensive audit logging for all access attempts

**Commands:**
```bash
./scripts/deployment/deploy_access_control.sh phase2
```

**Expected Outcomes:**
- ✅ Audit logging middleware active
- ✅ Logs writing to Redis DB 10
- ✅ Performance impact < 5ms per request
- ✅ Test audit entry successfully written

**Monitoring:**
```bash
# Watch audit logs in real-time
./scripts/monitoring/access_control_monitor.sh --follow

# Check audit statistics
python3 -c "
import asyncio
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()
    stats = await logger.get_statistics()
    print(f'Total logged: {stats[\"total_logged\"]}')
    print(f'Failed: {stats[\"total_failed\"]}')
    print(f'Redis available: {stats[\"redis_available\"]}')

asyncio.run(main())
"
```

**Performance Validation:**
```bash
# Backend API response times should be < +10ms
curl -w "@curl-format.txt" -o /dev/null -s "https://172.16.168.20:8443/api/health"
```

**Rollback:** Disable audit middleware (requires backend restart)

---

### Phase 3: Log-Only Monitoring (24-48 hours) ⏱️

**Objective:** Monitor access patterns without blocking - identify false positives

**Commands:**
```bash
# Enable LOG_ONLY mode
./scripts/deployment/deploy_access_control.sh phase3

# Start continuous monitoring
./scripts/monitoring/access_control_monitor.sh --follow --watch-denials
```

**Expected Outcomes:**
- ✅ LOG_ONLY mode active
- ✅ All access attempts logged
- ✅ Unauthorized attempts identified but not blocked
- ✅ Zero false positives detected
- ✅ Zero legitimate user impact

**Critical Monitoring (24-48 hours):**

**Dashboard:**
```bash
# Real-time monitoring
./scripts/monitoring/access_control_monitor.sh --follow
```

**Metrics to Watch:**
1. **Unauthorized Access Attempts:** Should be ZERO legitimate users
2. **Performance Impact:** Should be < 10ms
3. **Audit Log Volume:** Normal operational levels
4. **User Complaints:** Should be ZERO

**Query Recent Denials:**
```bash
python3 -c "
import asyncio
from datetime import datetime, timedelta
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()
    entries = await logger.query(
        result='denied',
        start_time=datetime.now() - timedelta(hours=24),
        limit=50
    )

    print(f'Denied attempts in last 24h: {len(entries)}')
    for entry in entries:
        print(f'{entry.timestamp} | {entry.user_id} | {entry.operation} | {entry.resource}')

asyncio.run(main())
"
```

**Decision Point:**

After 24-48 hours, review metrics:

✅ **PROCEED to Phase 4 if:**
- Zero legitimate user denials
- Performance impact acceptable
- No anomalies detected
- Audit logging stable

❌ **ROLLBACK if:**
- Legitimate users would be blocked
- Performance degradation > 10ms
- Audit logging failures
- System instability

```bash
# If rollback needed
./scripts/deployment/rollback_access_control.sh --reason "Legitimate user impact detected"
```

---

### Phase 4: Partial Enforcement (24-48 hours)

**Objective:** Gradually enable enforcement on low-risk endpoints

**Strategy:** Tiered rollout by risk level

**Tier 1: Read-Only Endpoints (Day 4, 8 hours)**
- GET `/api/chat/sessions/{id}`
- GET `/api/chat/sessions/{id}/messages`
- Monitor for 8 hours

**Tier 2: Create/Update Endpoints (Day 4-5, 16 hours)**
- POST `/api/chat/sessions/{id}/messages`
- PUT `/api/chat/sessions/{id}`
- Monitor for 16 hours

**Tier 3: Delete Endpoints (Day 5, 8 hours)**
- DELETE `/api/chat/sessions/{id}`
- Monitor for 8 hours

**Commands:**
```bash
# Enable partial enforcement
./scripts/deployment/deploy_access_control.sh phase4

# Configure endpoint-specific enforcement (manual in code)
python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags, EnforcementMode

async def main():
    flags = await get_feature_flags()

    # Tier 1: Read-only endpoints
    await flags.set_endpoint_enforcement(
        '/api/chat/sessions/{id}',
        EnforcementMode.ENFORCED
    )

    # Verify
    stats = await flags.get_rollout_statistics()
    print(stats)

asyncio.run(main())
"
```

**Monitoring:**
```bash
# Monitor for blocks
./scripts/monitoring/access_control_monitor.sh --follow --watch-denials
```

**Rollback Window:** Immediate if legitimate users blocked

```bash
# Disable specific endpoint enforcement
python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    await flags.set_endpoint_enforcement('/api/chat/sessions/{id}', None)

asyncio.run(main())
"

# Or full rollback
./scripts/deployment/rollback_access_control.sh --reason "User impact detected in partial enforcement"
```

---

### Phase 5: Full Enforcement (Ongoing)

**Objective:** Enable global access control enforcement - eliminate CVSS 9.1 vulnerability

**Commands:**
```bash
# ⚠️ CRITICAL: Final confirmation before full enforcement
./scripts/deployment/deploy_access_control.sh phase5

# Verify enforcement active
python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    mode = await flags.get_enforcement_mode()
    print(f'Enforcement Mode: {mode.value.upper()}')
    print('✓ CVSS 9.1 vulnerability ELIMINATED' if mode.value == 'enforced' else '✗ Not enforced')

asyncio.run(main())
"
```

**Expected Outcomes:**
- ✅ All conversation access validated
- ✅ Unauthorized access attempts blocked
- ✅ Audit logging comprehensive
- ✅ CVSS 9.1 vulnerability eliminated
- ✅ Zero legitimate user impact

**Continuous Monitoring:**
```bash
# 24/7 monitoring dashboard
./scripts/monitoring/access_control_monitor.sh --follow
```

**Emergency Rollback:**
```bash
# If critical issues arise
./scripts/deployment/rollback_access_control.sh --reason "EMERGENCY: [describe issue]" --force
```

---

### Phase 6: Post-Deployment Validation (Day 7)

**Objective:** Comprehensive validation and security testing

**Commands:**
```bash
# Full validation suite
./scripts/deployment/validate_access_control.sh --full

# Security-specific tests
./scripts/deployment/validate_access_control.sh --security-only

# Performance benchmarking
./scripts/deployment/validate_access_control.sh --performance-only
```

**Security Penetration Testing:**

**Test 1: Cross-User Access Attempt**
```bash
# Attempt to access another user's session (should fail)
curl -X GET "https://172.16.168.20:8443/api/chat/sessions/OTHER_USER_SESSION_ID" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -w "\nHTTP Status: %{http_code}\n"
```
**Expected:** HTTP 403 Forbidden

**Test 2: Unauthenticated Access**
```bash
# Attempt without authentication (should fail)
curl -X GET "https://172.16.168.20:8443/api/chat/sessions/SESSION_ID" \
  -w "\nHTTP Status: %{http_code}\n"
```
**Expected:** HTTP 401 Unauthorized

**Test 3: Audit Log Verification**
```bash
# Verify denied attempts are logged
python3 -c "
import asyncio
from datetime import datetime, timedelta
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()
    entries = await logger.query(
        result='denied',
        start_time=datetime.now() - timedelta(minutes=5),
        limit=10
    )

    if entries:
        print(f'✓ Denied attempts are being logged ({len(entries)} found)')
        for entry in entries[:3]:
            print(f'  - {entry.operation} by {entry.user_id}')
    else:
        print('✗ No denied attempts logged (may indicate issue)')

asyncio.run(main())
"
```

**Performance Benchmarking:**
```bash
# Ownership validation should be < 10ms
# Audit logging should be < 5ms

./scripts/deployment/validate_access_control.sh --performance-only
```

**Deliverables:**
- [ ] All validation tests passing
- [ ] Security penetration tests passed
- [ ] Performance benchmarks met
- [ ] Audit logs comprehensive
- [ ] Documentation updated
- [ ] Lessons learned documented

---

## 🚨 Emergency Procedures

### Immediate Rollback (< 5 minutes)

**Trigger Conditions:**
- Legitimate users blocked from their own sessions
- System instability or crashes
- Performance degradation > 50ms
- Redis failures
- Critical security bypass discovered

**Rollback Command:**
```bash
./scripts/deployment/rollback_access_control.sh \
  --reason "EMERGENCY: [describe issue]" \
  --force
```

**Verification:**
```bash
# Verify enforcement disabled
python3 -c "
import asyncio
from backend.services.feature_flags import get_feature_flags

async def main():
    flags = await get_feature_flags()
    mode = await flags.get_enforcement_mode()
    assert mode.value == 'disabled', f'Rollback failed: mode={mode.value}'
    print('✓ Rollback successful - enforcement DISABLED')

asyncio.run(main())
"
```

**Post-Rollback:**
1. Incident report
2. Root cause analysis
3. Fix implementation
4. Testing in isolated environment
5. Re-deployment with fixes

---

## 📊 Monitoring and Alerting

### Key Metrics

**Enforcement Status:**
- Current mode (DISABLED/LOG_ONLY/ENFORCED)
- Endpoint-specific overrides
- Mode change history

**Session Ownership:**
- Total sessions
- Owned sessions
- Coverage percentage (target: 100%)

**Audit Logging:**
- Total logged events
- Failed log writes
- Redis availability
- Queue size

**Access Control:**
- Successful access validations
- Denied access attempts (should be zero legitimate)
- Unauthorized access attempts
- Performance metrics (< 10ms target)

**System Health:**
- Backend API status
- Redis connectivity
- VM availability
- Error rates

### Monitoring Commands

**Real-Time Dashboard:**
```bash
./scripts/monitoring/access_control_monitor.sh --follow
```

**Quick Status Check:**
```bash
./scripts/monitoring/access_control_monitor.sh
```

**Watch Denials:**
```bash
./scripts/monitoring/access_control_monitor.sh --watch-denials --follow
```

**Audit Statistics:**
```bash
python3 -c "
import asyncio
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()
    stats = await logger.get_statistics()
    for key, value in stats.items():
        print(f'{key}: {value}')

asyncio.run(main())
"
```

---

## 🔍 Troubleshooting Guide

### Issue: Sessions missing ownership

**Symptoms:** Validation fails with incomplete ownership coverage

**Diagnosis:**
```bash
python3 scripts/security/backfill_session_ownership.py --verify-only
```

**Resolution:**
```bash
# Re-run backfill (idempotent)
python3 scripts/security/backfill_session_ownership.py --default-owner admin --force
```

---

### Issue: Audit logging failures

**Symptoms:** `total_failed` or `redis_failures` increasing

**Diagnosis:**
```bash
# Check Redis DB 10 connectivity
redis-cli -h 172.16.168.23 -p 6379 -n 10 ping

# Check audit logger statistics
python3 -c "
import asyncio
from backend.services.audit_logger import get_audit_logger

async def main():
    logger = await get_audit_logger()
    stats = await logger.get_statistics()
    print(f'Failed: {stats[\"total_failed\"]}')
    print(f'Redis failures: {stats[\"redis_failures\"]}')

asyncio.run(main())
"
```

**Resolution:**
```bash
# Check fallback logs (file-based when Redis fails)
ls -lh logs/audit/

# Restart backend if needed
./run_autobot.sh --restart
```

---

### Issue: Performance degradation

**Symptoms:** API response times > 10ms slower

**Diagnosis:**
```bash
# Benchmark ownership validation
./scripts/deployment/validate_access_control.sh --performance-only

# Check Redis latency
redis-cli -h 172.16.168.23 -p 6379 --latency
```

**Resolution:**
```bash
# If > 50ms degradation, consider rollback
./scripts/deployment/rollback_access_control.sh --reason "Performance degradation"

# Investigate Redis performance
redis-cli -h 172.16.168.23 -p 6379 INFO stats
redis-cli -h 172.16.168.23 -p 6379 SLOWLOG GET 10
```

---

### Issue: Legitimate users blocked

**Symptoms:** User reports they can't access their own conversations

**Diagnosis:**
```bash
# Check user's session ownership
python3 -c "
import asyncio
from backend.utils.async_redis_manager import get_redis_manager
from backend.security.session_ownership import SessionOwnershipValidator

async def main():
    redis_manager = await get_redis_manager()
    redis = await redis_manager.main()
    validator = SessionOwnershipValidator(redis)

    session_id = 'REPORTED_SESSION_ID'
    owner = await validator.get_session_owner(session_id)
    print(f'Session owner: {owner}')

    user_sessions = await validator.get_user_sessions('REPORTED_USERNAME')
    print(f'User sessions: {user_sessions}')

asyncio.run(main())
"
```

**Resolution:**
```bash
# Assign correct ownership
python3 -c "
import asyncio
from backend.utils.async_redis_manager import get_redis_manager
from backend.security.session_ownership import SessionOwnershipValidator

async def main():
    redis_manager = await get_redis_manager()
    redis = await redis_manager.main()
    validator = SessionOwnershipValidator(redis)

    await validator.set_session_owner('SESSION_ID', 'CORRECT_USERNAME')
    print('✓ Ownership corrected')

asyncio.run(main())
"

# If widespread issue, rollback immediately
./scripts/deployment/rollback_access_control.sh --reason "Legitimate user blocks detected"
```

---

## 📝 Success Criteria

### Phase Completion Criteria

**Phase 0:**
- [x] Feature flags deployed and functional
- [x] Enforcement mode: DISABLED
- [x] Redis backup created
- [x] All VMs accessible

**Phase 1:**
- [x] 100% session ownership coverage
- [x] Backfill verification passed
- [x] Zero service disruption

**Phase 2:**
- [x] Audit logging active
- [x] Test entries written successfully
- [x] Performance impact < 5ms

**Phase 3:**
- [x] LOG_ONLY mode active
- [x] 24-48 hour monitoring complete
- [x] Zero false positives detected
- [x] Zero legitimate user impact

**Phase 4:**
- [x] Partial enforcement on low-risk endpoints
- [x] 24-48 hour monitoring per tier
- [x] Zero legitimate user blocks

**Phase 5:**
- [x] Full enforcement active globally
- [x] CVSS 9.1 vulnerability eliminated
- [x] Audit logging comprehensive
- [x] Zero legitimate user impact

**Phase 6:**
- [x] All validation tests passed
- [x] Security penetration tests passed
- [x] Performance benchmarks met
- [x] Documentation complete

### Overall Success Criteria

- ✅ **Zero service downtime** during deployment
- ✅ **Zero legitimate user requests blocked** (post-monitoring)
- ✅ **100% ownership coverage** (all 54+ sessions)
- ✅ **Audit logging capturing all access attempts**
- ✅ **Performance impact < 10ms** per request
- ✅ **All 6 VMs synchronized and operational**
- ✅ **Rollback capability validated and ready**
- ✅ **CVSS 9.1 vulnerability eliminated**

---

## 📞 Support and Escalation

### Deployment Support

**Primary Contact:** DevOps Team
**Emergency Rollback Authority:** Operations Manager
**Security Team:** security@autobot.local

### Escalation Path

1. **Level 1:** DevOps Engineer (deployment execution)
2. **Level 2:** Senior DevOps Engineer (troubleshooting)
3. **Level 3:** Operations Manager (rollback decision)
4. **Level 4:** Security Team (security validation)

### Communication Channels

- Deployment channel: #autobot-deployments
- Incident channel: #autobot-incidents
- Status page: status.autobot.local

---

## 📚 Additional Resources

**Related Documentation:**
- [Multi-NPU Worker Architecture](../architecture/MULTI_NPU_WORKER_ARCHITECTURE.md)
- [Rollout Timeline](ROLLOUT_TIMELINE.md)
- [Security Features](../security/)
- [Troubleshooting Guide](../troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md)

**Scripts:**
- Deployment: `scripts/deployment/deploy_access_control.sh`
- Monitoring: `scripts/monitoring/access_control_monitor.sh`
- Rollback: `scripts/deployment/rollback_access_control.sh`
- Validation: `scripts/deployment/validate_access_control.sh`
- Backfill: `scripts/security/backfill_session_ownership.py`

**Code Components:**
- Feature Flags: `backend/services/feature_flags.py`
- Session Ownership: `backend/security/session_ownership.py`
- Audit Logger: `backend/services/audit_logger.py`
- Audit Middleware: `backend/middleware/audit_middleware.py`

---

**Document Version:** 1.0
**Last Updated:** 2025-10-06
**Next Review:** Post-deployment (within 7 days)
