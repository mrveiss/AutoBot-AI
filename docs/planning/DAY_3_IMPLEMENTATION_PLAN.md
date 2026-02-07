# Day 3 Implementation Plan - Service Key Distribution

**Date**: 2025-10-06
**Phase**: Week 1 → Week 2 Transition
**Objective**: Distribute service authentication keys to all 6 VMs
**Policy Compliance**: 0/10 violations (maintain full compliance)

---

## Executive Summary

Day 3 focuses on distributing the 6 pre-generated service API keys to their respective VMs and configuring each service to use HMAC-SHA256 authentication for service-to-service calls. This is a **configuration deployment only** - no code changes required.

**Current Status**:
- ✅ All 6 service keys generated and stored in Redis (172.16.168.23:6379)
- ✅ Ansible playbook created and ready
- ✅ Logging middleware deployed and collecting data
- ⏳ Service keys NOT YET distributed to VMs

**Day 3 Outcome**:
- Service keys deployed to all 6 VMs
- Services configured to include auth headers in API calls
- Continued logging mode (enforcement on Day 4)

---

## Current Service Auth Status Analysis

### Logging Mode Observations (Last 2 hours)

**Total Requests Logged**: 592
**All requests**: Frontend → Backend API calls (expected pattern)

**Top Endpoints Accessed**:
1. `/api/system/health` - 107 requests (health monitoring)
2. `/api/chats/*` - 101 requests (chat operations)
3. `/api/monitoring/*` - 34 requests (service monitoring)
4. `/chat/direct/*` - 20 requests (direct chat)
5. `/api/terminal/*` - 17 requests (terminal sessions)
6. `/api/frontend-config` - 16 requests (frontend config)
7. `/api/settings/*` - 11 requests (settings)

**Request Sources**:
- 100% from Frontend VM (172.16.168.21) - browser/user requests
- 0% service-to-service calls (services not configured yet)

**Authentication Pattern**:
```
Missing Headers: 100% (expected - frontend doesn't send service auth)
Invalid Signature: 0%
Timestamp Issues: 0%
Unknown Service: 0%
```

**Analysis**: ✅ **HEALTHY BASELINE**
- All requests are legitimate frontend → backend calls
- No service-to-service calls happening yet (expected)
- Logging middleware working correctly
- Ready for Day 3 deployment

---

## Service Key Inventory

All 6 service keys generated and stored in Redis at `172.16.168.23:6379`:

| Service ID | VM | IP Address | Key Location | Purpose |
|------------|-----|-----------|-------------|---------|
| **main-backend** | Main (WSL) | 172.16.168.20 | `service:key:main-backend` | Backend API calls to other services |
| **frontend** | VM1 | 172.16.168.21 | `service:key:frontend` | Frontend server-side API calls |
| **npu-worker** | VM2 | 172.16.168.22 | `service:key:npu-worker` | NPU worker calls to backend |
| **redis-stack** | VM3 | 172.16.168.23 | `service:key:redis-stack` | Redis Stack admin operations |
| **ai-stack** | VM4 | 172.16.168.24 | `service:key:ai-stack` | AI/ML service API calls |
| **browser-service** | VM5 | 172.16.168.25 | `service:key:browser-service` | Browser automation API calls |

**Key Properties**:
- **Format**: 256-bit (64 hex characters)
- **Algorithm**: HMAC-SHA256 for request signing
- **Expiration**: 90 days (automatic rotation planned)
- **Storage**: Redis with TTL tracking

---

## Day 3 Implementation Tasks

### Phase 1: Pre-Deployment Verification (30 minutes)

**Task 3.1: Verify Service Keys in Redis**
```bash
# Connect to Redis and verify all 6 keys exist
redis-cli -h 172.16.168.23 -p 6379

# Check each service key
EXISTS service:key:main-backend
EXISTS service:key:frontend
EXISTS service:key:npu-worker
EXISTS service:key:redis-stack
EXISTS service:key:ai-stack
EXISTS service:key:browser-service

# Verify TTL (should be ~90 days = ~7,776,000 seconds)
TTL service:key:main-backend
```

**Expected Output**: All keys exist with ~90-day TTL

**Task 3.2: Verify Ansible Inventory**
```bash
# Check Ansible can reach all VMs
ansible all -i ansible/inventory/production.yml -m ping

# Verify SSH access
ansible all -i ansible/inventory/production.yml \
  -m shell -a "echo 'Connection test successful'"
```

**Expected Output**: All 6 VMs respond successfully

**Task 3.3: Backup Current Configuration**
```bash
# Create backup directory
mkdir -p backups/service-auth-day3

# Backup existing configs (if any)
ansible all -i ansible/inventory/production.yml \
  -m shell -a "test -d /etc/autobot && tar czf /tmp/autobot-backup.tar.gz /etc/autobot || echo 'No config'"

# Retrieve backups
ansible all -i ansible/inventory/production.yml \
  -m fetch -a "src=/tmp/autobot-backup.tar.gz dest=backups/service-auth-day3/"
```

---

### Phase 2: Service Key Distribution (1 hour)

**Task 3.4: Create Service Key Configuration Files**

Each VM gets a `.env` file with its service credentials:

```bash
# Generate config files locally first
python3 scripts/generate_service_keys.py --export-configs
```

This creates:
```
/tmp/service-keys/
├── main-backend.env
├── frontend.env
├── npu-worker.env
├── redis-stack.env
├── ai-stack.env
└── browser-service.env
```

**File Format** (`main-backend.env` example):
```bash
# AutoBot Service Authentication Configuration
# Generated: 2025-10-06
# Service: main-backend

SERVICE_ID=main-backend
SERVICE_KEY=<256-bit hex key>
REDIS_HOST=172.16.168.23
REDIS_PORT=6379
AUTH_TIMESTAMP_WINDOW=300
```

**Task 3.5: Deploy Keys via Ansible**
```bash
# Deploy service keys to all VMs
ansible-playbook -i ansible/inventory/production.yml \
  ansible/playbooks/deploy-service-auth.yml \
  --extra-vars "phase=key_distribution"
```

**What this does**:
1. Creates `/etc/autobot/service-keys/` directory on each VM
2. Copies appropriate `.env` file to each VM
3. Sets permissions to `0600` (owner read/write only)
4. Verifies file contents

**Task 3.6: Verify Key Deployment**
```bash
# Check files exist on all VMs
ansible all -i ansible/inventory/production.yml \
  -m shell -a "ls -l /etc/autobot/service-keys/*.env"

# Verify permissions (should be 0600)
ansible all -i ansible/inventory/production.yml \
  -m shell -a "stat -c '%a %n' /etc/autobot/service-keys/*.env"

# Verify SERVICE_ID matches hostname
ansible all -i ansible/inventory/production.yml \
  -m shell -a "grep SERVICE_ID /etc/autobot/service-keys/*.env"
```

---

### Phase 3: Service Configuration Update (1 hour)

**Task 3.7: Update Service Startup Scripts**

Each service needs to load authentication credentials on startup.

**Main Backend** (172.16.168.20):
```bash
# Edit backend startup to load service keys
cat >> /home/autobot/backend/.env << 'EOF'

# Service Authentication
SERVICE_ID=main-backend
SERVICE_KEY_FILE=/etc/autobot/service-keys/main-backend.env
EOF
```

**Frontend** (172.16.168.21):
```bash
# Frontend needs to send auth headers for server-side API calls
cat >> /home/autobot/autobot-user-frontend/.env << 'EOF'

# Service Authentication (server-side only)
VITE_SERVICE_ID=frontend
VITE_SERVICE_KEY_FILE=/etc/autobot/service-keys/frontend.env
EOF
```

**NPU Worker** (172.16.168.22):
```bash
cat >> /home/autobot/npu-worker/.env << 'EOF'

# Service Authentication
SERVICE_ID=npu-worker
SERVICE_KEY_FILE=/etc/autobot/service-keys/npu-worker.env
EOF
```

**AI Stack** (172.16.168.24):
```bash
cat >> /home/autobot/ai-stack/.env << 'EOF'

# Service Authentication
SERVICE_ID=ai-stack
SERVICE_KEY_FILE=/etc/autobot/service-keys/ai-stack.env
EOF
```

**Browser Service** (172.16.168.25):
```bash
cat >> /home/autobot/browser-service/.env << 'EOF'

# Service Authentication
SERVICE_ID=browser-service
SERVICE_KEY_FILE=/etc/autobot/service-keys/browser-service.env
EOF
```

**Task 3.8: Deploy Configuration Updates**
```bash
# Deploy updated .env files to all VMs
ansible-playbook -i ansible/inventory/production.yml \
  ansible/playbooks/deploy-service-auth.yml \
  --extra-vars "phase=config_update"
```

---

### Phase 4: Service Restart & Verification (30 minutes)

**Task 3.9: Restart Services with New Configuration**

**IMPORTANT**: Use rolling restart to maintain availability

```bash
# Restart order (dependencies first):
# 1. Redis (no restart needed - already configured)
# 2. Backend (main service)
# 3. Frontend, NPU, Browser, AI (in parallel)

# Restart backend
ssh autobot@172.16.168.20 "cd /home/autobot && bash run_autobot.sh --restart"

# Wait 30 seconds for backend to be ready
sleep 30

# Restart all other services in parallel
ansible frontend,npu-worker,ai-stack,browser-service \
  -i ansible/inventory/production.yml \
  -m shell -a "cd /home/autobot && bash restart-service.sh"
```

**Task 3.10: Verify Services Loaded Credentials**
```bash
# Check backend logs for service auth initialization
ssh autobot@172.16.168.20 \
  "grep 'Service credentials loaded' /home/autobot/logs/backend.log"

# Check all services loaded their keys
ansible all -i ansible/inventory/production.yml \
  -m shell -a "grep 'SERVICE_ID=' /proc/\$(pgrep -f 'python.*main')/environ | tr '\\0' '\\n'"
```

**Task 3.11: Test Service-to-Service Authentication**

**Test 1: Backend → Redis Health Check**
```bash
# Backend should now send auth headers to Redis API
curl -v http://172.16.168.20:8001/api/redis/health
```

**Expected Log** (backend.log):
```
✅ Service authentication successful service_id=main-backend method=GET path=/api/redis/health
```

**Test 2: NPU Worker → Backend Registration**
```bash
# NPU worker should authenticate when registering
ssh autobot@172.16.168.22 \
  "curl -X POST http://172.16.168.20:8001/api/npu/register"
```

**Expected Log** (backend.log):
```
✅ Service authentication successful service_id=npu-worker method=POST path=/api/npu/register
```

**Test 3: Frontend SSR → Backend API**
```bash
# Frontend server-side rendering should authenticate
curl http://172.16.168.21:5173/
# This triggers frontend → backend API call with auth
```

**Expected Log** (backend.log):
```
✅ Service authentication successful service_id=frontend method=GET path=/api/frontend-config
```

---

### Phase 5: Monitoring & Validation (Continuous)

**Task 3.12: Enable Enhanced Logging**
```bash
# Increase log level for service auth temporarily
ansible all -i ansible/inventory/production.yml \
  -m shell -a "export LOG_LEVEL=DEBUG && systemctl reload autobot-*"
```

**Task 3.13: Monitor Authentication Patterns (24 hours)**

**Run monitoring script every hour**:
```bash
# Automated monitoring (add to cron)
echo "0 * * * * /home/autobot/scripts/monitor-service-auth.sh > /tmp/auth-report-\$(date +\%Y\%m\%d-\%H).md 2>&1" | crontab -
```

**Manual monitoring**:
```bash
# Generate real-time report
bash scripts/monitor-service-auth.sh
# Select: Option 1 (Generate analysis report)

# Watch for successful authentications
tail -f logs/backend.log | grep "Service authentication successful"

# Watch for failures
tail -f logs/backend.log | grep "Service auth failed"
```

**Expected Success Pattern After Day 3**:
```
✅ Service authentication successful service_id=frontend method=GET
✅ Service authentication successful service_id=npu-worker method=POST
✅ Service authentication successful service_id=main-backend method=GET
⚠️  Service auth failed (logging only - request allowed) [Frontend browser requests - expected]
```

**Task 3.14: Analyze Authentication Success Rate**

**Success Criteria**:
- Service-to-service calls: **100% authenticated**
- Frontend browser calls: **0% authenticated** (expected - not service calls)
- No invalid signatures
- No timestamp issues

**Validation Query**:
```bash
# Count successful service auth
grep "Service authentication successful" logs/backend.log | wc -l

# Count failures by type
grep "Missing authentication headers" logs/backend.log | grep -v "frontend browser" | wc -l
grep "Invalid signature" logs/backend.log | wc -l
grep "Timestamp outside" logs/backend.log | wc -l
```

---

## Rollback Plan

If Day 3 deployment causes issues:

**Quick Rollback** (< 5 minutes):
```bash
# Stop all services
ansible all -i ansible/inventory/production.yml \
  -m shell -a "systemctl stop autobot-*"

# Remove service key files
ansible all -i ansible/inventory/production.yml \
  -m shell -a "rm -rf /etc/autobot/service-keys/"

# Restore backup configurations
ansible all -i ansible/inventory/production.yml \
  -m shell -a "cd /tmp && tar xzf autobot-backup.tar.gz -C /"

# Restart services
ansible all -i ansible/inventory/production.yml \
  -m shell -a "systemctl start autobot-*"
```

**Validation After Rollback**:
```bash
# Verify services running
ansible all -i ansible/inventory/production.yml -m shell -a "systemctl status autobot-*"

# Check frontend accessible
curl http://172.16.168.21:5173

# Check backend accessible
curl http://172.16.168.20:8001/api/health
```

---

## Risk Assessment

### Risk #1: Clock Skew Between VMs
**Probability**: Low (10%)
**Impact**: High (authentication failures)

**Mitigation**:
```bash
# Verify NTP sync on all VMs before deployment
ansible all -i ansible/inventory/production.yml \
  -m shell -a "timedatectl status | grep 'synchronized'"

# If not synchronized, enable NTP
ansible all -i ansible/inventory/production.yml \
  -m shell -a "timedatectl set-ntp true"
```

**Validation**:
```bash
# Check time difference between VMs (should be < 5 seconds)
ansible all -i ansible/inventory/production.yml \
  -m shell -a "date +%s" | grep -v "SUCCESS" | \
  awk '{print $1}' | sort -n | \
  awk 'NR==1{min=$1} END{print "Time diff: "(max-min)" seconds"; max=$1}'
```

### Risk #2: Network Partition During Deployment
**Probability**: Very Low (5%)
**Impact**: High (partial deployment)

**Mitigation**:
- Use Ansible transaction mode (all-or-nothing deployment)
- Test connectivity before each phase
- Have rollback script ready

### Risk #3: Service Key Corruption
**Probability**: Very Low (2%)
**Impact**: Critical (authentication completely broken)

**Mitigation**:
- Verify key integrity after deployment
- Keep backup in Redis (90-day TTL)
- Can regenerate keys if needed

---

## Success Criteria for Day 3

### Must Have (Blocking for Day 4)
- ✅ All 6 service keys deployed to correct VMs
- ✅ All services successfully load credentials on startup
- ✅ At least 1 successful service-to-service authenticated call
- ✅ No service crashes or startup failures
- ✅ Frontend remains accessible to users

### Should Have (Non-blocking)
- ✅ 100% service-to-service calls authenticated
- ✅ Monitoring reports show clean authentication patterns
- ✅ No invalid signature errors
- ✅ Clock sync within 5-second window across all VMs

### Nice to Have
- ✅ Automated monitoring via cron
- ✅ Real-time authentication dashboard
- ✅ Performance metrics (auth overhead < 5ms)

---

## Timeline - Day 3 Execution

**Total Estimated Time**: 3 hours

| Phase | Tasks | Time | Dependencies |
|-------|-------|------|--------------|
| **Phase 1** | Pre-deployment verification | 30 min | None |
| **Phase 2** | Service key distribution | 1 hour | Phase 1 complete |
| **Phase 3** | Service configuration update | 1 hour | Phase 2 complete |
| **Phase 4** | Service restart & verification | 30 min | Phase 3 complete |
| **Phase 5** | Monitoring setup | Ongoing | Phase 4 complete |

**Best Time to Execute**: Off-peak hours (early morning or late evening)
**Recommended**: Weekday morning (easier rollback if issues occur)

---

## Post-Day 3 Status

**Expected System State**:
- Logging middleware: Still active (not enforcement yet)
- Service keys: Deployed and loaded by all services
- Authentication: Service calls include proper HMAC signatures
- Frontend: Browser requests still missing headers (expected)
- Monitoring: Enhanced logging capturing all auth attempts

**Transition to Day 4**:
Once Day 3 shows 24 hours of clean service-to-service authentication with no failures, we proceed to Day 4 enforcement mode deployment.

---

## Appendix A: HMAC-SHA256 Signature Format

**Request Signing Process**:
```python
import hmac
import hashlib
import time

service_id = "main-backend"
service_key = "<256-bit hex key>"
method = "GET"
path = "/api/redis/health"
timestamp = int(time.time())

# Generate signature
message = f"{service_id}:{method}:{path}:{timestamp}"
signature = hmac.new(
    service_key.encode(),
    message.encode(),
    hashlib.sha256
).hexdigest()

# Add headers to request
headers = {
    "X-Service-ID": service_id,
    "X-Service-Signature": signature,
    "X-Service-Timestamp": str(timestamp)
}
```

**Backend Validation**:
1. Extract headers from request
2. Verify timestamp within 5-minute window
3. Retrieve service key from Redis
4. Recalculate expected signature
5. Constant-time comparison (prevents timing attacks)
6. Log result (success or failure)

---

## Appendix B: Troubleshooting Guide

### Issue: "Invalid signature" errors

**Diagnosis**:
```bash
# Check service key matches Redis
redis-cli -h 172.16.168.23 -p 6379 GET service:key:main-backend
cat /etc/autobot/service-keys/main-backend.env | grep SERVICE_KEY
```

**Fix**: Re-deploy correct key if mismatch detected

### Issue: "Timestamp outside allowed window"

**Diagnosis**:
```bash
# Check system time on all VMs
ansible all -i ansible/inventory/production.yml -m shell -a "date"
```

**Fix**: Enable NTP sync and restart chronyd

### Issue: Service won't start after key deployment

**Diagnosis**:
```bash
# Check service logs
journalctl -u autobot-backend -n 50

# Check .env file syntax
ansible all -i ansible/inventory/production.yml \
  -m shell -a "bash -n /home/autobot/backend/.env"
```

**Fix**: Correct .env syntax errors and restart

---

**Day 3 Plan Status**: ✅ Ready for execution
**Prerequisites**: ✅ All met (Week 1 complete, keys generated, logging active)
**Next Action**: Execute Phase 1 pre-deployment verification
