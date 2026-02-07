# Service Authentication Enforcement Rollout Plan

**GitHub Issue:** [#255](https://github.com/mrveiss/AutoBot-AI/issues/255)
**Document Version:** 1.0
**Date:** 2025-10-09
**Status:** 🟡 PENDING APPROVAL
**Security Level:** CRITICAL - CVSS 10.0 Vulnerability Closure

---

## 📋 Executive Summary

### Current State

**Deployment Status:** Day 3 Complete - 24-Hour Monitoring Period Active

- ✅ **Service keys deployed** to all 6 VMs (90-day TTL)
- ✅ **Logging middleware operational** (zero service disruption)
- ✅ **Enforcement middleware ready** (85 exempt + 16 service-only paths)
- ✅ **Main backend configured** with ServiceHTTPClient
- ❌ **Remote services NOT configured** (NPU Worker, AI Stack, Browser Service)

### Objective

Transition from **logging-only mode** to **active enforcement mode** to close CVSS 10.0 vulnerability:

> **Vulnerability:** Unauthenticated service-to-service communication allows complete backend API access without credentials, enabling lateral movement, data exfiltration, and service impersonation.

### Critical Blocker Identified

**Issue:** Remote services (VM 22, 24, 25) NOT configured with ServiceHTTPClient
**Impact:** Cannot enable enforcement without breaking these services
**Resolution:** Phase 1 (Service Client Migration) - 2-3 days

### Timeline Summary

| Phase | Duration | Status | Risk |
|-------|----------|--------|------|
| **Phase 1: Service Client Migration** | 2-3 days | 🟡 Pending | 🟢 Low |
| **Phase 2: Soft Enforcement** | 1-2 days | ⏸️ Blocked | 🟡 Medium |
| **Phase 3: Circuit Breaker** | 1 day | ⏸️ Blocked | 🟡 Medium |
| **Phase 4: Full Enforcement** | Ongoing | ⏸️ Blocked | 🟢 Low |

**Total Timeline:** 4-6 days from Phase 1 start to full enforcement

### Success Criteria

✅ **Zero service disruption** during entire rollout
✅ **All service-to-service calls authenticated** via HMAC-SHA256
✅ **Frontend access maintained** (85 exempt paths functional)
✅ **CVSS 10.0 vulnerability eliminated**
✅ **Fast rollback capability** maintained (< 2 minutes)

---

## 🏗️ Current Implementation State

### Enforcement Middleware Overview

**File:** `/home/kali/Desktop/AutoBot/backend/middleware/service_auth_enforcement.py`

**Capabilities:**
- Comprehensive endpoint categorization (85 exempt + 16 service-only)
- Environment toggle: `SERVICE_AUTH_ENFORCEMENT_MODE=true|false`
- Default-open policy (uncategorized paths allowed through)
- Sophisticated path matching with debug logging
- HMAC-SHA256 signature validation
- Replay attack protection (300-second timestamp window)

**Current Mode:** `SERVICE_AUTH_ENFORCEMENT_MODE=false` (disabled)

### Endpoint Categorization

#### Frontend-Accessible Paths (85 Total)

**No service authentication required** - accessible from browser:

```python
EXEMPT_PATHS = [
    # User-facing chat and conversation endpoints
    "/api/chat",
    "/api/chats",
    "/api/conversations",
    "/api/conversation_files",

    # Knowledge base user operations
    "/api/knowledge",
    "/api/knowledge_base",

    # Terminal access for users
    "/api/terminal",
    "/api/agent_terminal",

    # User settings and configuration
    "/api/settings",
    "/api/frontend_config",

    # System health and monitoring (public endpoints)
    "/api/system/health",
    "/api/monitoring/services/health",
    "/api/services/status",

    # User-facing file operations
    "/api/files",

    # LLM configuration and models
    "/api/llm",

    # Prompts management
    "/api/prompts",

    # Memory operations
    "/api/memory",

    # Monitoring dashboards
    "/api/monitoring",
    "/api/metrics",
    "/api/analytics",

    # WebSocket connections
    "/ws",

    # API documentation
    "/docs",
    "/openapi.json",
    "/redoc",

    # Development endpoints
    "/api/developer",
    "/api/validation_dashboard",

    # Real User Monitoring
    "/api/rum",

    # Infrastructure monitoring (visible to users)
    "/api/infrastructure",

    # Additional user-facing endpoints
    "/api/orchestration",
    "/api/workflow",
    "/api/embeddings",
    "/api/voice",
    "/api/multimodal",
]
```

**Rationale:** These endpoints are designed for browser-to-backend communication with user authentication (session tokens, JWT, etc.). Service authentication not applicable.

#### Service-Only Paths (16 Total)

**Service authentication REQUIRED** - internal service-to-service only:

```python
SERVICE_ONLY_PATHS = [
    # NPU Worker internal endpoints
    "/api/npu/results",
    "/api/npu/heartbeat",
    "/api/npu/status",
    "/api/npu/internal",

    # AI Stack internal endpoints
    "/api/ai-stack/results",
    "/api/ai-stack/heartbeat",
    "/api/ai-stack/models",
    "/api/ai-stack/internal",

    # Browser Service internal endpoints
    "/api/browser/results",
    "/api/browser/screenshots",
    "/api/browser/logs",
    "/api/browser/heartbeat",
    "/api/browser/internal",

    # Internal service communication
    "/api/internal",

    # Service registry (internal only)
    "/api/registry/internal",

    # Audit logging (internal only)
    "/api/audit/internal",
]
```

**Rationale:** These endpoints expose internal service operations, result retrieval, and administrative functions that MUST NOT be accessible without cryptographic authentication.

### Logging Middleware Status

**File:** `/home/kali/Desktop/AutoBot/backend/middleware/service_auth_logging.py`
**Status:** ✅ DEPLOYED (Day 3 complete)
**Mode:** Logging only - does NOT block requests

**Current Behavior:**
- Logs authentication attempts (success + failure)
- Allows ALL requests through regardless of authentication
- Provides baseline metrics for enforcement planning
- Zero impact on service availability

**Monitoring Period:** 24 hours (started 2025-10-06 12:30 PM)

### ServiceHTTPClient Implementation

**File:** `/home/kali/Desktop/AutoBot/backend/utils/service_client.py`
**Status:** ✅ FULLY IMPLEMENTED

**Capabilities:**
- Auto-signs all HTTP requests with HMAC-SHA256
- Environment-based credential loading (`SERVICE_ID` + `SERVICE_KEY_FILE`)
- Support for all HTTP methods (GET, POST, PUT, DELETE, PATCH)
- Configurable timeouts (default: 30s)
- Async/await support via httpx.AsyncClient
- Context manager support (async with)

**Example Usage:**
```python
# Method 1: Create from environment
client = create_service_client_from_env()
response = await client.get("http://172.16.168.24:8080/api/inference")

# Method 2: Explicit credentials
client = ServiceHTTPClient(service_id="main-backend", service_key="...")
response = await client.post("http://172.16.168.22:8081/api/process", json={...})
```

**Current Deployment:**
- ✅ Main Backend (VM 20): Configured and operational
- ❌ NPU Worker (VM 22): **NOT CONFIGURED**
- ❌ AI Stack (VM 24): **NOT CONFIGURED**
- ❌ Browser Service (VM 25): **NOT CONFIGURED**
- ❌ Frontend (VM 21): **NOT CONFIGURED** (may not need service auth)
- ❌ Redis (VM 23): **NOT CONFIGURED** (likely not needed)

### Service Key Deployment Status

**Storage:** Redis Stack (VM 23) + Local Files
**TTL:** ~89.5 days (from Day 3 deployment)

| Service | Redis Key | Local Key File | Status |
|---------|-----------|----------------|--------|
| Main Backend | `service:key:main-backend` | `~/.autobot/service-keys/main-backend.env` | ✅ Deployed |
| Frontend | `service:key:frontend` | `/etc/autobot/service-keys/frontend.env` | ✅ Deployed |
| NPU Worker | `service:key:npu-worker` | `/etc/autobot/service-keys/npu-worker.env` | ✅ Deployed |
| Redis Stack | `service:key:redis-stack` | `/etc/autobot/service-keys/redis-stack.env` | ✅ Deployed |
| AI Stack | `service:key:ai-stack` | `/etc/autobot/service-keys/ai-stack.env` | ✅ Deployed |
| Browser Service | `service:key:browser-service` | `/etc/autobot/service-keys/browser-service.env` | ✅ Deployed |

**Security:** All key files have 600 permissions (owner read/write only)

### Critical Gap Analysis

**Gap:** Remote services have service keys but NOT configured to use ServiceHTTPClient

**Impact:**
```
Current State:
- Remote services CAN receive authenticated requests (keys deployed)
- Remote services CANNOT send authenticated requests (no client configured)
- Enforcement mode would BREAK remote service → backend calls
```

**Example Broken Flow (if enforcement enabled now):**
```
NPU Worker → Backend (unauthenticated)
    ↓
Backend Enforcement Middleware
    ↓
Path: /api/npu/results (in SERVICE_ONLY_PATHS)
    ↓
Signature validation: MISSING HEADERS
    ↓
BLOCKED with 401 Unauthorized ❌
    ↓
NPU Worker fails to deliver results
```

**Resolution Required:** Phase 1 (Service Client Migration)

---

## 📦 Phase 1: Service Client Migration

**Objective:** Configure remote services to use ServiceHTTPClient for backend communication
**Duration:** 2-3 days
**Risk Level:** 🟢 Low (no breaking changes, additive configuration)
**Prerequisite:** Day 3 24-hour monitoring period complete

### Services Requiring Configuration

1. **NPU Worker (VM 22)** - Priority: HIGH
   - Makes result delivery calls to backend
   - Heartbeat and status reporting
   - Hardware acceleration result callbacks

2. **AI Stack (VM 24)** - Priority: HIGH
   - Inference result delivery
   - Model status reporting
   - Heartbeat and health checks

3. **Browser Service (VM 25)** - Priority: MEDIUM
   - Screenshot delivery
   - Automation result callbacks
   - Log and status reporting

4. **Frontend (VM 21)** - Priority: LOW (evaluation needed)
   - May not need service auth (browser-to-backend uses user auth)
   - Evaluate if any server-side API calls exist

5. **Redis (VM 23)** - Priority: NONE
   - Data store, not an API consumer
   - No configuration needed

### Phase 1 Implementation Steps

#### Step 1.1: Verify Day 3 Monitoring Complete

**Duration:** 5 minutes
**Prerequisites:** 24 hours elapsed since Day 3 deployment

```bash
# Check monitoring period elapsed
echo "Day 3 started: 2025-10-06 12:30 PM"
echo "Current time: $(date)"
echo "Hours elapsed: (calculate)"

# Verify system stability
curl -s http://172.16.168.20:8001/api/health | jq -r '.status'
# Expected: "healthy"

# Check service keys still present
redis-cli -h 172.16.168.23 -a "$REDIS_PASSWORD" KEYS "service:key:*" | wc -l
# Expected: 6

# Review authentication logs
grep "Service auth failed" logs/backend.log | tail -50
# Expected: Frontend warnings only (500-1000 total)
```

**Go/No-Go Criteria:**
- ✅ Backend uptime: 100% (no crashes during 24hr period)
- ✅ All 6 service keys present with TTL > 85 days
- ✅ Timestamp violations: 0
- ✅ Signature failures from legitimate services: 0
- ✅ Clock drift: < 100 seconds

**If ANY criterion fails:** Extend monitoring, resolve issues before proceeding

#### Step 1.2: Update NPU Worker Configuration

**Duration:** 30-45 minutes
**Target:** VM 22 (172.16.168.22)

**Actions:**

1. **Update NPU Worker code to use ServiceHTTPClient**

   Identify where NPU Worker makes backend API calls:
   ```bash
   # On NPU Worker (VM 22), find backend API calls
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.22
   grep -r "http://172.16.168.20:8001" /home/autobot/npu-worker/
   ```

   Example locations to update:
   - Result delivery: `npu_worker.py` or `result_sender.py`
   - Heartbeat: `health_reporter.py`
   - Status updates: `status_reporter.py`

2. **Install/copy ServiceHTTPClient to NPU Worker**

   Option A: Copy from main backend
   ```bash
   # On local machine
   scp -i ~/.ssh/autobot_key \
     backend/utils/service_client.py \
     backend/security/service_auth.py \
     autobot@172.16.168.22:/home/autobot/npu-worker/utils/
   ```

   Option B: Create shared library package (better long-term)
   ```bash
   # Create autobot-shared package with ServiceHTTPClient
   # Deploy to all VMs via pip install
   ```

3. **Update NPU Worker .env configuration**

   Verify `/etc/autobot/.env` on VM 22 has:
   ```env
   SERVICE_ID=npu-worker
   SERVICE_KEY_FILE=/etc/autobot/service-keys/npu-worker.env
   AUTH_TIMESTAMP_WINDOW=300
   BACKEND_HOST=172.16.168.20
   BACKEND_PORT=8001
   ```

4. **Update NPU Worker code to use authenticated client**

   Before:
   ```python
   import httpx

   async def send_results(results):
       async with httpx.AsyncClient() as client:
           response = await client.post(
               "http://172.16.168.20:8001/api/npu/results",
               json=results
           )
   ```

   After:
   ```python
   from utils.service_client import create_service_client_from_env

   async def send_results(results):
       client = create_service_client_from_env()
       response = await client.post(
           "http://172.16.168.20:8001/api/npu/results",
           json=results
       )
       await client.close()
   ```

5. **Restart NPU Worker service**

   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.22
   sudo systemctl restart npu-worker
   # OR
   pkill -f npu_worker && python -m npu_worker &
   ```

6. **Verify NPU Worker authenticated calls**

   Monitor backend logs for authenticated requests:
   ```bash
   # On main machine, watch for NPU Worker authenticated calls
   tail -f logs/backend.log | grep "npu-worker"

   # Should see:
   # "Service authenticated successfully" service_id=npu-worker
   ```

   Test NPU Worker functionality:
   ```bash
   # Trigger NPU processing task
   # Verify results delivered successfully with authentication
   ```

**Validation Checklist:**
- [ ] ServiceHTTPClient code deployed to NPU Worker
- [ ] .env configuration verified on VM 22
- [ ] NPU Worker code updated to use authenticated client
- [ ] NPU Worker service restarted successfully
- [ ] Backend logs show authenticated requests from npu-worker
- [ ] NPU Worker functionality verified (results delivered)

#### Step 1.3: Update AI Stack Configuration

**Duration:** 30-45 minutes
**Target:** VM 24 (172.16.168.24)

**Actions:** (Similar to Step 1.2)

1. **Identify backend API call locations in AI Stack**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.24
   grep -r "http://172.16.168.20:8001" /home/autobot/ai-stack/
   ```

2. **Deploy ServiceHTTPClient to AI Stack**
   ```bash
   scp -i ~/.ssh/autobot_key \
     backend/utils/service_client.py \
     backend/security/service_auth.py \
     autobot@172.16.168.24:/home/autobot/ai-stack/utils/
   ```

3. **Verify .env configuration on VM 24**
   ```env
   SERVICE_ID=ai-stack
   SERVICE_KEY_FILE=/etc/autobot/service-keys/ai-stack.env
   AUTH_TIMESTAMP_WINDOW=300
   BACKEND_HOST=172.16.168.20
   BACKEND_PORT=8001
   ```

4. **Update AI Stack code** (result delivery, heartbeat, model status)

5. **Restart AI Stack services**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.24
   sudo systemctl restart ai-stack
   ```

6. **Verify AI Stack authenticated calls**
   ```bash
   tail -f logs/backend.log | grep "ai-stack"
   # Should see: "Service authenticated successfully" service_id=ai-stack
   ```

**Validation Checklist:**
- [ ] ServiceHTTPClient code deployed to AI Stack
- [ ] .env configuration verified on VM 24
- [ ] AI Stack code updated to use authenticated client
- [ ] AI Stack services restarted successfully
- [ ] Backend logs show authenticated requests from ai-stack
- [ ] AI Stack functionality verified (inference results delivered)

#### Step 1.4: Update Browser Service Configuration

**Duration:** 30-45 minutes
**Target:** VM 25 (172.16.168.25)

**Actions:** (Similar to Steps 1.2 and 1.3)

1. **Identify backend API call locations in Browser Service**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.25
   grep -r "http://172.16.168.20:8001" /home/autobot/browser-service/
   ```

2. **Deploy ServiceHTTPClient to Browser Service**
   ```bash
   scp -i ~/.ssh/autobot_key \
     backend/utils/service_client.py \
     backend/security/service_auth.py \
     autobot@172.16.168.25:/home/autobot/browser-service/utils/
   ```

3. **Verify .env configuration on VM 25**
   ```env
   SERVICE_ID=browser-service
   SERVICE_KEY_FILE=/etc/autobot/service-keys/browser-service.env
   AUTH_TIMESTAMP_WINDOW=300
   BACKEND_HOST=172.16.168.20
   BACKEND_PORT=8001
   ```

4. **Update Browser Service code** (screenshot delivery, logs, automation results)

5. **Restart Browser Service**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.25
   sudo systemctl restart browser-service
   ```

6. **Verify Browser Service authenticated calls**
   ```bash
   tail -f logs/backend.log | grep "browser-service"
   # Should see: "Service authenticated successfully" service_id=browser-service
   ```

**Validation Checklist:**
- [ ] ServiceHTTPClient code deployed to Browser Service
- [ ] .env configuration verified on VM 25
- [ ] Browser Service code updated to use authenticated client
- [ ] Browser Service restarted successfully
- [ ] Backend logs show authenticated requests from browser-service
- [ ] Browser Service functionality verified (screenshots delivered)

#### Step 1.5: Evaluate Frontend Service Authentication Need

**Duration:** 15-30 minutes
**Target:** VM 21 (172.16.168.21)

**Evaluation Questions:**

1. **Does Frontend VM make server-side API calls to backend?**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21
   grep -r "http://172.16.168.20:8001" /home/autobot/autobot-user-frontend/
   ```

2. **Are these calls from browser or from server-side code?**
   - **Browser calls**: Use user authentication (session tokens), NOT service auth
   - **Server-side calls**: Would need service authentication

**Most Likely:** Frontend does NOT need service authentication
- Vue.js is client-side framework (runs in browser)
- Browser → Backend calls use user authentication
- No server-side API consumption expected

**Decision:**
- **If NO server-side API calls:** Skip configuration, mark as N/A
- **If server-side API calls exist:** Configure similar to Steps 1.2-1.4

#### Step 1.6: Phase 1 Validation & Testing

**Duration:** 1-2 hours
**Objective:** Comprehensive validation of all service client configurations

**Test Suite:**

1. **Service-to-Service Call Validation**
   ```bash
   # Test each service can authenticate with backend

   # NPU Worker test
   # Trigger NPU processing task → Verify results delivered with auth

   # AI Stack test
   # Trigger AI inference → Verify results delivered with auth

   # Browser Service test
   # Trigger screenshot capture → Verify screenshot delivered with auth
   ```

2. **Authentication Log Analysis**
   ```bash
   # Verify ALL service-to-service calls are now authenticated
   grep "Service authenticated successfully" logs/backend.log | tail -50

   # Should see entries for:
   # - service_id=npu-worker
   # - service_id=ai-stack
   # - service_id=browser-service

   # Verify NO authentication failures from configured services
   grep "Service auth failed" logs/backend.log | grep -v "missing"
   # Should only show frontend warnings (missing headers from browser)
   ```

3. **Functional Testing**
   ```bash
   # End-to-end workflow tests

   # Test 1: Chat with AI (involves AI Stack)
   curl -X POST http://172.16.168.20:8001/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "Hello", "session_id": "test"}'

   # Test 2: NPU processing task
   # (Trigger NPU workload, verify completion)

   # Test 3: Browser automation
   # (Trigger screenshot capture, verify delivery)
   ```

4. **Performance Validation**
   ```bash
   # Verify authentication overhead is minimal (< 10ms)
   # Compare pre-auth vs post-auth response times

   ab -n 100 -c 10 http://172.16.168.20:8001/api/health
   # Note: Average response time

   # Should be similar to pre-authentication baseline
   ```

**Phase 1 Go/No-Go Criteria:**

✅ **REQUIRED TO PROCEED TO PHASE 2:**
- [ ] NPU Worker: Authenticated calls successful, functionality verified
- [ ] AI Stack: Authenticated calls successful, functionality verified
- [ ] Browser Service: Authenticated calls successful, functionality verified
- [ ] Authentication logs: All service calls show valid signatures
- [ ] Functional tests: All end-to-end workflows passing
- [ ] Performance: Authentication overhead < 10ms per request
- [ ] Zero service disruptions during Phase 1 implementation

**If ANY criterion fails:** Debug and resolve before proceeding to Phase 2

### Phase 1 Rollback Procedure

**Scenario:** Service client configuration causes issues

**Quick Rollback (< 5 minutes per service):**

```bash
# Example: Rollback NPU Worker
ssh -i ~/.ssh/autobot_key autobot@172.16.168.22

# Revert code to previous version
cd /home/autobot/npu-worker
git checkout HEAD~1  # Or specific commit

# Restart service
sudo systemctl restart npu-worker

# Verify functionality restored
curl http://172.16.168.22:8081/health
```

**Service continues working with unauthenticated calls** (logging mode allows this)

---

## 🛡️ Phase 2: Soft Enforcement

**Objective:** Enable enforcement mode with safety mechanisms and override capabilities
**Duration:** 1-2 days
**Risk Level:** 🟡 Medium (enforcement active but with safety nets)
**Prerequisite:** Phase 1 complete with all validation criteria met

### Soft Enforcement Strategy

**Concept:** Enable `SERVICE_AUTH_ENFORCEMENT_MODE=true` with safety mechanisms:

1. **Override Token Support:** Emergency bypass for critical situations
2. **Gradual Path Activation:** Start with low-risk endpoints
3. **Enhanced Monitoring:** Real-time authentication metrics
4. **Fast Rollback Ready:** Single environment variable toggle

### Phase 2 Implementation Steps

#### Step 2.1: Prepare Soft Enforcement Infrastructure

**Duration:** 1-2 hours

**Actions:**

1. **Create override token system** (optional safety mechanism)

   Add to enforcement middleware:
   ```python
   # backend/middleware/service_auth_enforcement.py

   def has_override_token(request: Request) -> bool:
       """Check for emergency override token."""
       override_token = request.headers.get("X-Override-Token")
       expected_token = os.getenv("SERVICE_AUTH_OVERRIDE_TOKEN")

       if override_token and expected_token:
           return secrets.compare_digest(override_token, expected_token)
       return False

   async def enforce_service_auth(request: Request, call_next):
       # ... existing code ...

       # Check for override token (emergency bypass)
       if has_override_token(request):
           logger.warning(
               "⚠️ Override token used - bypassing auth",
               path=path,
               method=request.method,
               ip=request.client.host
           )
           return await call_next(request)

       # ... rest of enforcement logic ...
   ```

   Generate override token:
   ```bash
   # Generate random 256-bit override token
   python3 -c "import secrets; print(secrets.token_hex(32))"
   # Example: 7a9f3e8b2c1d4f6a8b9c2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b
   ```

   Store securely:
   ```bash
   # Add to .env (main backend only)
   echo "SERVICE_AUTH_OVERRIDE_TOKEN=7a9f3e8b2c1d4f6a8b9c2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b" >> .env

   # CRITICAL: Never commit to git, store in secure vault
   ```

2. **Set up enhanced monitoring dashboard**

   Create monitoring script:
   ```bash
   #!/bin/bash
   # scripts/monitoring/service-auth-enforcement-monitor.sh

   while true; do
       clear
       echo "=== Service Auth Enforcement Monitor ==="
       echo "Time: $(date)"
       echo

       # Enforcement status
       echo "Enforcement Mode: $(grep SERVICE_AUTH_ENFORCEMENT_MODE .env | cut -d= -f2)"
       echo

       # Authentication metrics (last 5 minutes)
       echo "Authentication Metrics (last 5 min):"
       cutoff=$(date -d '5 minutes ago' '+%Y-%m-%d %H:%M')

       success=$(grep "Service authenticated successfully" logs/backend.log | \
                 awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)
       failed=$(grep "Service authentication FAILED" logs/backend.log | \
                awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)
       blocked=$(grep "request BLOCKED" logs/backend.log | \
                 awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)

       echo "  Successful: $success"
       echo "  Failed: $failed"
       echo "  Blocked: $blocked"
       echo

       # Service health
       echo "Service Health:"
       curl -s http://172.16.168.20:8001/api/health | jq -r '.status' 2>/dev/null || echo "ERROR"

       sleep 10
   done
   ```

   Launch monitoring:
   ```bash
   chmod +x scripts/monitoring/service-auth-enforcement-monitor.sh
   ./scripts/monitoring/service-auth-enforcement-monitor.sh
   ```

3. **Prepare rollback procedure script**

   ```bash
   #!/bin/bash
   # scripts/rollback-enforcement.sh - Emergency rollback script

   echo "=== Emergency Enforcement Rollback ==="
   echo "This will disable enforcement mode immediately."
   read -p "Continue? (yes/no): " confirm

   if [ "$confirm" != "yes" ]; then
       echo "Rollback cancelled."
       exit 1
   fi

   # Disable enforcement
   sed -i 's/SERVICE_AUTH_ENFORCEMENT_MODE=true/SERVICE_AUTH_ENFORCEMENT_MODE=false/' .env

   # Restart backend (fast restart)
   echo "Restarting backend..."
   bash run_autobot.sh --restart

   # Verify rollback
   sleep 5
   status=$(curl -s http://172.16.168.20:8001/api/health | jq -r '.status')

   if [ "$status" = "healthy" ]; then
       echo "✅ Rollback successful - Enforcement mode disabled"
       echo "Current mode: $(grep SERVICE_AUTH_ENFORCEMENT_MODE .env)"
   else
       echo "❌ Rollback verification failed - Check backend manually"
   fi
   ```

#### Step 2.2: Enable Soft Enforcement Mode

**Duration:** 15-30 minutes

**Actions:**

1. **Update environment configuration**

   ```bash
   # Edit .env file
   vim /home/kali/Desktop/AutoBot/.env

   # Change:
   SERVICE_AUTH_ENFORCEMENT_MODE=false

   # To:
   SERVICE_AUTH_ENFORCEMENT_MODE=true
   ```

2. **Restart backend with enforcement enabled**

   ```bash
   # Fast restart (< 1 minute)
   bash run_autobot.sh --restart

   # Monitor startup
   tail -f logs/backend.log

   # Should see:
   # "✅ Service Authentication ENFORCEMENT MODE enabled"
   # "Frontend-accessible paths (first 10)"
   # "Service-only paths"
   ```

3. **Immediate health verification**

   ```bash
   # Backend health check
   curl -s http://172.16.168.20:8001/api/health | jq
   # Expected: {"status": "healthy", ...}

   # Frontend accessibility test (should still work)
   curl -s http://172.16.168.20:8001/api/settings | jq
   # Expected: 200 OK (exempt path)

   # Service-only path test (should require auth)
   curl -s http://172.16.168.20:8001/api/npu/internal
   # Expected: 401 Unauthorized (if called without auth)
   ```

**Immediate Rollback If:**
- Backend fails to start
- Health endpoint returns errors
- Frontend accessibility broken (exempt paths return 401)

#### Step 2.3: Gradual Validation & Monitoring

**Duration:** 1-2 days (continuous monitoring)

**Monitoring Schedule:**

| Time | Action | Focus |
|------|--------|-------|
| **First 15 minutes** | Intensive monitoring | Catch immediate issues |
| **First hour** | Active monitoring | Verify service functionality |
| **First 4 hours** | Regular checks (every 30 min) | Confirm stability |
| **First 24 hours** | Periodic checks (every 4 hours) | Long-term stability |
| **24-48 hours** | Daily checks | Prepare for Phase 3 |

**Monitoring Checklist (run every check):**

```bash
# 1. Backend health
curl -s http://172.16.168.20:8001/api/health | jq -r '.status'

# 2. Authentication metrics (last hour)
cutoff=$(date -d '1 hour ago' '+%Y-%m-%d %H:%M')

success=$(grep "Service authenticated successfully" logs/backend.log | \
          awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)
failed=$(grep "Service authentication FAILED" logs/backend.log | \
         awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)
blocked=$(grep "request BLOCKED" logs/backend.log | \
          awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)

echo "Auth Success: $success | Failed: $failed | Blocked: $blocked"

# 3. Service functionality tests
# - Trigger NPU task → Verify completion
# - Trigger AI inference → Verify completion
# - Trigger browser automation → Verify completion

# 4. Frontend accessibility
curl -s http://172.16.168.20:8001/api/settings > /dev/null
echo "Frontend access: $?"  # Should be 0 (success)
```

**Alert Thresholds:**

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| **Blocked Requests** | > 10/hour | > 50/hour | Investigate source, possible misconfiguration |
| **Failed Auth (Legitimate Services)** | > 5/hour | > 20/hour | Check service configurations |
| **Backend Errors** | > 10/hour | > 50/hour | Check logs, possible enforcement bug |
| **Frontend 401 Errors** | > 1/hour | > 10/hour | Exempt path configuration issue |

**Escalation Procedure:**

1. **Warning threshold reached:** Investigate within 1 hour
2. **Critical threshold reached:** Immediate investigation + prepare rollback
3. **Multiple critical alerts:** Execute rollback immediately

#### Step 2.4: Functional Validation Testing

**Duration:** 2-4 hours (spread across monitoring period)

**Test Suite:**

1. **Service-to-Service Authentication Tests**

   ```bash
   # Test 1: NPU Worker authenticated call
   # Trigger NPU processing task
   # Verify:
   # - Task completes successfully
   # - Backend logs show authenticated request from npu-worker
   # - No 401 errors in NPU Worker logs

   # Test 2: AI Stack authenticated call
   # Trigger AI inference request
   # Verify:
   # - Inference completes successfully
   # - Backend logs show authenticated request from ai-stack
   # - No 401 errors in AI Stack logs

   # Test 3: Browser Service authenticated call
   # Trigger screenshot capture
   # Verify:
   # - Screenshot delivered successfully
   # - Backend logs show authenticated request from browser-service
   # - No 401 errors in Browser Service logs
   ```

2. **Frontend Accessibility Tests**

   ```bash
   # Test all exempt paths are still accessible

   for path in "/api/chat" "/api/settings" "/api/knowledge" "/api/terminal"; do
       echo "Testing: $path"
       status=$(curl -s -o /dev/null -w '%{http_code}' \
                "http://172.16.168.20:8001$path")

       if [ "$status" != "200" ] && [ "$status" != "404" ]; then
           echo "❌ FAILED: $path returned $status (expected 200 or 404)"
       else
           echo "✅ PASSED: $path returned $status"
       fi
   done
   ```

3. **Unauthenticated Access Blocking Tests**

   ```bash
   # Test service-only paths are properly blocked

   for path in "/api/npu/internal" "/api/ai-stack/internal" "/api/browser/internal"; do
       echo "Testing: $path (should be blocked)"
       status=$(curl -s -o /dev/null -w '%{http_code}' \
                "http://172.16.168.20:8001$path")

       if [ "$status" = "401" ] || [ "$status" = "403" ]; then
           echo "✅ PASSED: $path properly blocked ($status)"
       else
           echo "❌ FAILED: $path not blocked (returned $status)"
       fi
   done
   ```

4. **Override Token Test** (if implemented)

   ```bash
   # Test emergency override mechanism

   curl -X GET "http://172.16.168.20:8001/api/npu/internal" \
        -H "X-Override-Token: YOUR_OVERRIDE_TOKEN" \
        -v

   # Should:
   # - Return 200 OK (bypassing auth)
   # - Log warning about override token usage

   # Check logs:
   grep "Override token used" logs/backend.log
   ```

**Phase 2 Go/No-Go Criteria:**

✅ **REQUIRED TO PROCEED TO PHASE 3:**
- [ ] Backend stable for 24+ hours with enforcement enabled
- [ ] All service-to-service calls authenticated successfully
- [ ] Zero authentication failures from configured services
- [ ] All frontend paths (85 exempt) remain accessible
- [ ] Service-only paths (16) properly blocked without auth
- [ ] Functional tests: 100% pass rate
- [ ] No critical alerts triggered
- [ ] Performance overhead within acceptable limits (< 10ms)

**If ANY criterion fails:** Extend Phase 2 monitoring, resolve issues

### Phase 2 Rollback Procedure

**Scenario:** Enforcement mode causes service disruptions

**Emergency Rollback (< 2 minutes):**

```bash
# Method 1: Automated script
bash scripts/rollback-enforcement.sh

# Method 2: Manual
sed -i 's/SERVICE_AUTH_ENFORCEMENT_MODE=true/SERVICE_AUTH_ENFORCEMENT_MODE=false/' .env
bash run_autobot.sh --restart

# Verify rollback
curl -s http://172.16.168.20:8001/api/health | jq -r '.status'
# Expected: "healthy"

# Confirm enforcement disabled
grep SERVICE_AUTH_ENFORCEMENT_MODE .env
# Expected: SERVICE_AUTH_ENFORCEMENT_MODE=false
```

**System immediately returns to logging-only mode** (no blocking)

---

## 🔄 Phase 3: Circuit Breaker Enforcement

**Objective:** Gradual enforcement ramp-up with automatic rollback on issues
**Duration:** 1 day (6-8 hours active ramping)
**Risk Level:** 🟡 Medium (progressive risk mitigation)
**Prerequisite:** Phase 2 complete with 24+ hours successful enforcement

### Circuit Breaker Strategy

**Concept:** Progressive enforcement percentage with automatic rollback triggers

**Ramp Schedule:**
- **10%:** First 1 hour - Minimal exposure
- **25%:** Next 1 hour - Early validation
- **50%:** Next 2 hours - Majority baseline
- **75%:** Next 2 hours - High confidence
- **100%:** Final state - Full enforcement

**Automatic Rollback Triggers:**
- Authentication failure rate > 5% for configured services
- Service downtime detected
- Error rate spike (> 2x baseline)
- Manual override triggered

### Phase 3 Implementation Steps

#### Step 3.1: Implement Circuit Breaker Logic

**Duration:** 2-3 hours

**Actions:**

1. **Add circuit breaker to enforcement middleware**

   ```python
   # backend/middleware/service_auth_enforcement.py

   import random

   def get_enforcement_percentage() -> int:
       """Get current enforcement percentage (0-100)."""
       return int(os.getenv("SERVICE_AUTH_ENFORCEMENT_PERCENTAGE", "100"))

   def should_enforce_request() -> bool:
       """
       Determine if this specific request should be enforced.

       Uses random sampling based on enforcement percentage.
       Example: 50% enforcement = 50% chance this request is enforced.
       """
       percentage = get_enforcement_percentage()

       if percentage >= 100:
           return True  # Full enforcement
       elif percentage <= 0:
           return False  # No enforcement
       else:
           # Random sampling for gradual ramp
           return random.randint(1, 100) <= percentage

   async def enforce_service_auth(request: Request, call_next):
       path = request.url.path

       # Check if path is exempt
       if is_path_exempt(path):
           return await call_next(request)

       # Check if path requires service auth
       if requires_service_auth(path):
           # Circuit breaker check
           if not should_enforce_request():
               logger.debug(
                   "Circuit breaker: Request allowed (sampling)",
                   path=path,
                   enforcement_pct=get_enforcement_percentage()
               )
               return await call_next(request)

           # Enforce authentication
           logger.info("Enforcing service authentication", path=path)
           # ... existing enforcement logic ...

       # Default: allow through
       return await call_next(request)
   ```

2. **Create circuit breaker control script**

   ```bash
   #!/bin/bash
   # scripts/circuit-breaker-ramp.sh

   set -e

   RAMP_SCHEDULE=(
       "10:60"   # 10% for 60 minutes
       "25:60"   # 25% for 60 minutes
       "50:120"  # 50% for 120 minutes
       "75:120"  # 75% for 120 minutes
       "100:0"   # 100% (final state)
   )

   echo "=== Service Auth Circuit Breaker Ramp ==="
   echo "Start time: $(date)"
   echo

   for stage in "${RAMP_SCHEDULE[@]}"; do
       pct=$(echo $stage | cut -d: -f1)
       duration=$(echo $stage | cut -d: -f2)

       echo "Setting enforcement to ${pct}%..."
       sed -i "s/SERVICE_AUTH_ENFORCEMENT_PERCENTAGE=.*/SERVICE_AUTH_ENFORCEMENT_PERCENTAGE=${pct}/" .env

       # Restart backend to apply
       echo "Restarting backend..."
       bash run_autobot.sh --restart > /dev/null 2>&1

       # Verify backend healthy
       sleep 5
       status=$(curl -s http://172.16.168.20:8001/api/health | jq -r '.status')

       if [ "$status" != "healthy" ]; then
           echo "❌ Backend health check failed at ${pct}% - Rolling back"
           bash scripts/rollback-enforcement.sh
           exit 1
       fi

       echo "✅ Enforcement at ${pct}% - Backend healthy"

       if [ "$duration" -gt 0 ]; then
           echo "Monitoring for ${duration} minutes..."

           # Monitor during ramp period
           end_time=$(($(date +%s) + duration * 60))

           while [ $(date +%s) -lt $end_time ]; do
               # Check for circuit breaker triggers
               failed=$(grep "Service authentication FAILED" logs/backend.log | tail -100 | grep -c "npu-worker\|ai-stack\|browser-service" || echo 0)

               if [ "$failed" -gt 10 ]; then
                   echo "❌ Circuit breaker triggered: Too many auth failures - Rolling back"
                   bash scripts/rollback-enforcement.sh
                   exit 1
               fi

               sleep 60  # Check every minute
           done
       fi

       echo "Stage ${pct}% complete."
       echo
   done

   echo "=== Circuit Breaker Ramp Complete ==="
   echo "Enforcement at 100% - Full production mode"
   echo "End time: $(date)"
   ```

3. **Create circuit breaker monitoring dashboard**

   ```bash
   #!/bin/bash
   # scripts/monitoring/circuit-breaker-monitor.sh

   while true; do
       clear
       echo "=== Circuit Breaker Enforcement Monitor ==="
       echo "Time: $(date)"

       # Current enforcement percentage
       pct=$(grep SERVICE_AUTH_ENFORCEMENT_PERCENTAGE .env | cut -d= -f2)
       echo "Enforcement: ${pct}%"
       echo

       # Metrics (last 5 minutes)
       cutoff=$(date -d '5 minutes ago' '+%Y-%m-%d %H:%M')

       total=$(grep "Enforcing service authentication\|allowed (sampling)" logs/backend.log | \
               awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)
       enforced=$(grep "Enforcing service authentication" logs/backend.log | \
                  awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)
       sampled=$(grep "allowed (sampling)" logs/backend.log | \
                 awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)
       failed=$(grep "Service authentication FAILED" logs/backend.log | \
                awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)

       echo "Requests (last 5 min):"
       echo "  Total service-only: $total"
       echo "  Enforced: $enforced"
       echo "  Sampled (allowed): $sampled"
       echo "  Failed auth: $failed"

       if [ "$total" -gt 0 ]; then
           actual_pct=$((enforced * 100 / total))
           echo "  Actual enforcement: ${actual_pct}% (target: ${pct}%)"
       fi

       echo
       echo "Service Health:"
       curl -s http://172.16.168.20:8001/api/health | jq -r '.status' 2>/dev/null || echo "ERROR"

       sleep 10
   done
   ```

#### Step 3.2: Execute Circuit Breaker Ramp

**Duration:** 6-8 hours (automated)

**Actions:**

1. **Prepare for ramp execution**

   ```bash
   # Verify Phase 2 complete
   echo "Phase 2 duration check:"
   echo "Enforcement enabled since: (check Day 3 + Phase 2 start)"
   echo "Current time: $(date)"

   # Verify all services still healthy
   curl -s http://172.16.168.20:8001/api/health | jq

   # Review recent authentication logs
   grep "Service authenticated successfully" logs/backend.log | tail -20
   # Should show: npu-worker, ai-stack, browser-service

   # Backup current configuration
   cp .env .env.backup.phase3
   ```

2. **Launch monitoring dashboard**

   ```bash
   # Terminal 1: Monitoring dashboard
   ./scripts/monitoring/circuit-breaker-monitor.sh
   ```

3. **Execute automated ramp**

   ```bash
   # Terminal 2: Ramp execution
   ./scripts/circuit-breaker-ramp.sh

   # Expected output:
   # Setting enforcement to 10%...
   # Restarting backend...
   # ✅ Enforcement at 10% - Backend healthy
   # Monitoring for 60 minutes...
   # (repeat for 25%, 50%, 75%, 100%)
   ```

4. **Monitor ramp progress**

   Watch monitoring dashboard for:
   - ✅ Actual enforcement percentage matching target
   - ✅ Authentication success rate > 95%
   - ✅ Zero service disruptions
   - ✅ Backend health: "healthy" throughout

**Manual Intervention Points:**

- **If authentication failures spike:** Pause ramp, investigate
- **If service downtime detected:** Automatic rollback triggers
- **If error rate increases:** Pause ramp, analyze logs

#### Step 3.3: Phase 3 Validation

**Duration:** 1-2 hours (after 100% reached)

**Validation Tests:**

1. **Verify 100% enforcement active**

   ```bash
   # Check configuration
   grep SERVICE_AUTH_ENFORCEMENT_PERCENTAGE .env
   # Expected: SERVICE_AUTH_ENFORCEMENT_PERCENTAGE=100

   # Verify no sampling in logs
   grep "allowed (sampling)" logs/backend.log | tail -10
   # Should be OLD entries only (from ramp period)
   ```

2. **Comprehensive functional testing**

   ```bash
   # Run full test suite
   # - NPU Worker: Trigger processing, verify completion
   # - AI Stack: Trigger inference, verify completion
   # - Browser Service: Trigger screenshot, verify completion
   # - Frontend: Access all exempt paths, verify 200 OK
   # - Unauthenticated calls: Verify all blocked
   ```

3. **Performance validation**

   ```bash
   # Load testing with authentication
   ab -n 1000 -c 50 http://172.16.168.20:8001/api/health

   # Compare to baseline (from Phase 2)
   # Authentication overhead should still be < 10ms
   ```

4. **Security validation**

   ```bash
   # Attempt unauthenticated access to service-only paths
   for path in "/api/npu/internal" "/api/ai-stack/internal" "/api/browser/internal"; do
       status=$(curl -s -o /dev/null -w '%{http_code}' \
                "http://172.16.168.20:8001$path")

       if [ "$status" = "401" ] || [ "$status" = "403" ]; then
           echo "✅ $path properly secured"
       else
           echo "❌ $path SECURITY ISSUE: returned $status"
       fi
   done
   ```

**Phase 3 Go/No-Go Criteria:**

✅ **REQUIRED TO PROCEED TO PHASE 4:**
- [ ] Circuit breaker ramp completed successfully (10% → 100%)
- [ ] Zero automatic rollbacks triggered during ramp
- [ ] 100% enforcement verified in configuration
- [ ] All service-to-service calls authenticated successfully
- [ ] Frontend accessibility maintained (85 exempt paths)
- [ ] Functional tests: 100% pass rate
- [ ] Performance within acceptable limits
- [ ] Security validation: All service-only paths properly blocked

**If ANY criterion fails:** Investigate, resolve, potentially re-run ramp

### Phase 3 Rollback Procedure

**Scenario 1: Circuit breaker auto-rollback triggered**

System automatically executes rollback script - no manual intervention needed.

**Scenario 2: Manual rollback during ramp**

```bash
# Stop ramp script (Ctrl+C)

# Execute rollback
bash scripts/rollback-enforcement.sh

# Verify system restored
curl -s http://172.16.168.20:8001/api/health | jq

# Review logs to identify issue
grep "ERROR\|FAILED" logs/backend.log | tail -50
```

---

## 🎯 Phase 4: Full Enforcement & Production Hardening

**Objective:** Remove safety mechanisms, production hardening, long-term monitoring
**Duration:** Ongoing (initial setup 2-3 hours)
**Risk Level:** 🟢 Low (proven stable through Phases 1-3)
**Prerequisite:** Phase 3 complete with 100% enforcement validated

### Full Enforcement Configuration

#### Step 4.1: Remove Safety Mechanisms

**Duration:** 30 minutes

**Actions:**

1. **Remove override token** (optional - may keep for emergencies)

   ```bash
   # Option A: Remove completely
   sed -i '/SERVICE_AUTH_OVERRIDE_TOKEN/d' .env

   # Option B: Keep but document as emergency-only
   # Add comment in .env:
   # # EMERGENCY ONLY: Override token for critical issues
   # SERVICE_AUTH_OVERRIDE_TOKEN=...
   ```

2. **Remove circuit breaker percentage**

   ```bash
   # Remove from .env (enforcement now always 100%)
   sed -i '/SERVICE_AUTH_ENFORCEMENT_PERCENTAGE/d' .env

   # Clean up circuit breaker code (optional)
   # Can keep dormant for future use if needed
   ```

3. **Restart backend with final configuration**

   ```bash
   bash run_autobot.sh --restart

   # Verify configuration
   curl -s http://172.16.168.20:8001/api/health | jq
   ```

#### Step 4.2: Production Hardening

**Duration:** 1-2 hours

**Security Hardening:**

1. **Implement rate limiting on authentication failures**

   ```python
   # backend/middleware/service_auth_enforcement.py

   # Add rate limiting for failed auth attempts
   from collections import defaultdict
   from datetime import datetime, timedelta

   # Track failed auth attempts per IP
   failed_auth_tracker = defaultdict(list)

   def is_rate_limited(ip: str, window_minutes: int = 5, max_attempts: int = 10) -> bool:
       """Check if IP is rate limited due to excessive auth failures."""
       now = datetime.now()
       cutoff = now - timedelta(minutes=window_minutes)

       # Clean old attempts
       failed_auth_tracker[ip] = [
           attempt for attempt in failed_auth_tracker[ip]
           if attempt > cutoff
       ]

       # Check if rate limited
       return len(failed_auth_tracker[ip]) >= max_attempts

   def record_failed_auth(ip: str):
       """Record failed authentication attempt."""
       failed_auth_tracker[ip].append(datetime.now())

   async def enforce_service_auth(request: Request, call_next):
       # ... existing code ...

       # Check rate limiting before authentication
       client_ip = request.client.host
       if is_rate_limited(client_ip):
           logger.warning(
               "Rate limit exceeded for IP",
               ip=client_ip,
               path=path
           )
           raise HTTPException(
               status_code=429,
               detail="Too many authentication failures. Try again later."
           )

       # ... authentication logic ...

       # On auth failure:
       except HTTPException as e:
           record_failed_auth(client_ip)
           raise
   ```

2. **Add request signing for internal endpoints**

   Ensure ALL internal endpoints validate request signatures, not just headers.

3. **Implement service key rotation schedule**

   ```bash
   # Add to cron or systemd timer
   # Rotate service keys every 90 days (before TTL expires)

   # /etc/cron.d/autobot-key-rotation
   # Run key rotation script 7 days before expiration
   0 0 * * * autobot /home/autobot/scripts/rotate-service-keys.sh
   ```

4. **Enable audit logging for all authentication events**

   ```python
   # backend/middleware/service_auth_enforcement.py

   from backend.services.audit_logger import AuditLogger

   async def enforce_service_auth(request: Request, call_next):
       # ... existing code ...

       # Audit successful authentication
       if service_info:
           await AuditLogger.log_event(
               operation="service.authentication",
               result="success",
               service_id=service_info["service_id"],
               path=path,
               method=request.method,
               ip=request.client.host
           )

       # Audit failed authentication
       except HTTPException as e:
           await AuditLogger.log_event(
               operation="service.authentication",
               result="denied",
               path=path,
               method=request.method,
               ip=request.client.host,
               reason=str(e.detail)
           )
           raise
   ```

**Performance Optimization:**

1. **Implement signature caching** (reduce Redis lookups)

   ```python
   # Cache service keys for 5 minutes to reduce Redis load
   from functools import lru_cache

   @lru_cache(maxsize=128)
   def get_service_key_cached(service_id: str) -> str:
       """Get service key with caching."""
       # ... fetch from Redis ...
   ```

2. **Optimize path matching** (pre-compile regex patterns)

3. **Connection pooling verification**

   Ensure Redis connection pools optimized for authentication load.

#### Step 4.3: Long-Term Monitoring Setup

**Duration:** 1 hour

**Monitoring Infrastructure:**

1. **Prometheus metrics endpoint**

   ```python
   # autobot-user-backend/api/metrics.py

   from prometheus_client import Counter, Histogram, Gauge

   # Service auth metrics
   auth_attempts = Counter(
       'service_auth_attempts_total',
       'Total service authentication attempts',
       ['service_id', 'result']
   )

   auth_duration = Histogram(
       'service_auth_duration_seconds',
       'Service authentication duration',
       buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1]
   )

   active_services = Gauge(
       'service_auth_active_services',
       'Number of active authenticated services'
   )
   ```

2. **Grafana dashboard configuration**

   Create dashboard tracking:
   - Authentication success/failure rates
   - Authentication latency (p50, p95, p99)
   - Active authenticated services count
   - Rate limiting events
   - Service key TTL remaining

3. **Alert configuration**

   ```yaml
   # alertmanager/service-auth-alerts.yml

   groups:
     - name: service_authentication
       interval: 30s
       rules:
         - alert: HighAuthFailureRate
           expr: rate(service_auth_attempts_total{result="failed"}[5m]) > 0.05
           for: 5m
           labels:
             severity: warning
           annotations:
             summary: "High service authentication failure rate"

         - alert: ServiceKeyExpiringSoon
           expr: service_key_ttl_days < 30
           for: 1h
           labels:
             severity: warning
           annotations:
             summary: "Service key expiring in < 30 days"

         - alert: AuthenticationLatencyHigh
           expr: histogram_quantile(0.95, service_auth_duration_seconds) > 0.050
           for: 10m
           labels:
             severity: warning
           annotations:
             summary: "Service authentication p95 latency > 50ms"
   ```

4. **Daily monitoring report script**

   ```bash
   #!/bin/bash
   # scripts/monitoring/daily-service-auth-report.sh

   echo "=== Daily Service Auth Report ==="
   echo "Date: $(date)"
   echo

   # Authentication metrics (last 24 hours)
   cutoff=$(date -d '24 hours ago' '+%Y-%m-%d %H:%M')

   success=$(grep "Service authenticated successfully" logs/backend.log | \
             awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)
   failed=$(grep "Service authentication FAILED" logs/backend.log | \
            awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)
   rate_limited=$(grep "Rate limit exceeded" logs/backend.log | \
                  awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)

   echo "Authentication Events (24h):"
   echo "  Successful: $success"
   echo "  Failed: $failed"
   echo "  Rate Limited: $rate_limited"
   echo

   # Service activity
   echo "Active Services (24h):"
   grep "Service authenticated successfully" logs/backend.log | \
     awk -v c="$cutoff" '$1" "$2 >= c' | \
     grep -o 'service_id=[^ ]*' | sort | uniq -c
   echo

   # Service key status
   echo "Service Key Status:"
   for key in main-backend frontend npu-worker redis-stack ai-stack browser-service; do
       ttl=$(redis-cli -h 172.16.168.23 -a "$REDIS_PASSWORD" TTL "service:key:$key" 2>/dev/null)
       days=$((ttl / 86400))
       echo "  $key: $days days remaining"
   done
   echo

   # System health
   echo "Backend Health:"
   curl -s http://172.16.168.20:8001/api/health | jq -r '.status'

   echo
   echo "=== Report Complete ==="
   ```

   Schedule daily execution:
   ```bash
   # Add to crontab
   0 8 * * * /home/kali/Desktop/AutoBot/scripts/monitoring/daily-service-auth-report.sh | mail -s "AutoBot Service Auth Daily Report" admin@autobot.local
   ```

### Phase 4 Success Criteria

✅ **Production Deployment Complete When:**
- [ ] All safety mechanisms removed or documented as emergency-only
- [ ] Production hardening complete (rate limiting, audit logging, etc.)
- [ ] Long-term monitoring operational (Prometheus, Grafana, alerts)
- [ ] Daily monitoring reports automated
- [ ] Service key rotation scheduled
- [ ] Documentation updated with production configuration
- [ ] Team trained on monitoring and incident response

---

## 🔙 Rollback Procedures

### Emergency Rollback (< 2 Minutes)

**Scenario:** Critical production issue requires immediate rollback

**Procedure:**

```bash
#!/bin/bash
# EMERGENCY ROLLBACK - Execute immediately on critical issues

echo "=== EMERGENCY SERVICE AUTH ROLLBACK ==="
echo "Timestamp: $(date)"

# Step 1: Disable enforcement (fastest action)
sed -i 's/SERVICE_AUTH_ENFORCEMENT_MODE=true/SERVICE_AUTH_ENFORCEMENT_MODE=false/' .env

# Step 2: Fast backend restart
pkill -f "uvicorn.*backend"
sleep 2
cd /home/kali/Desktop/AutoBot
nohup python -m uvicorn backend.app_factory:app --host 0.0.0.0 --port 8001 > logs/backend.log 2>&1 &

# Step 3: Wait for startup
sleep 5

# Step 4: Verify rollback
status=$(curl -s http://172.16.168.20:8001/api/health | jq -r '.status' 2>/dev/null)

if [ "$status" = "healthy" ]; then
    echo "✅ EMERGENCY ROLLBACK SUCCESSFUL"
    echo "Enforcement mode: DISABLED"
    echo "Services restored to logging-only mode"
else
    echo "❌ ROLLBACK VERIFICATION FAILED"
    echo "Manual intervention required immediately"
    echo "Backend status: $status"
fi

# Step 5: Notify team
echo "Rollback executed at $(date)" | mail -s "CRITICAL: AutoBot Service Auth Emergency Rollback" admin@autobot.local

echo "=== Rollback Complete ==="
```

**Save as:** `/home/kali/Desktop/AutoBot/scripts/EMERGENCY-ROLLBACK.sh`
**Permissions:** `chmod +x scripts/EMERGENCY-ROLLBACK.sh`

**Execution:** `bash scripts/EMERGENCY-ROLLBACK.sh`

**Expected Duration:** 30-60 seconds total
- Disable enforcement: 1 second
- Backend restart: 30-40 seconds
- Verification: 5-10 seconds

### Standard Rollback (Planned)

**Scenario:** Non-emergency rollback during maintenance window

**Procedure:**

```bash
#!/bin/bash
# STANDARD ROLLBACK - Planned maintenance rollback

echo "=== Standard Service Auth Rollback ==="
read -p "Confirm standard rollback? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Rollback cancelled"
    exit 1
fi

# Step 1: Backup current configuration
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
cp logs/backend.log logs/backend.log.backup.$(date +%Y%m%d_%H%M%S)

# Step 2: Disable enforcement
sed -i 's/SERVICE_AUTH_ENFORCEMENT_MODE=true/SERVICE_AUTH_ENFORCEMENT_MODE=false/' .env

# Step 3: Standard restart
bash run_autobot.sh --restart

# Step 4: Comprehensive verification
sleep 10

# Backend health
health=$(curl -s http://172.16.168.20:8001/api/health | jq -r '.status')
echo "Backend health: $health"

# Service connectivity
for service in npu-worker ai-stack browser-service; do
    echo "Testing $service connectivity..."
    # Trigger test for each service
done

# Frontend accessibility
for path in "/api/chat" "/api/settings" "/api/knowledge"; do
    status=$(curl -s -o /dev/null -w '%{http_code}' "http://172.16.168.20:8001$path")
    echo "Frontend path $path: $status"
done

# Step 5: Document rollback
cat >> logs/rollback-log.txt <<EOF
=== Rollback Executed ===
Date: $(date)
Type: Standard (planned)
Previous Mode: Enforcement enabled
New Mode: Logging only
Reason: $1
Executed By: $(whoami)
Verification: $health
========================
EOF

echo "✅ Standard rollback complete"
echo "Configuration backed up"
echo "System restored to logging-only mode"
```

**Usage:** `bash scripts/standard-rollback.sh "Reason for rollback"`

### Rollback Decision Criteria

**Execute Emergency Rollback When:**

| Severity | Metric | Threshold | Action |
|----------|--------|-----------|--------|
| **P0 - Critical** | Backend downtime | > 1 minute | IMMEDIATE emergency rollback |
| **P0 - Critical** | Frontend inaccessible | > 5 exempt paths returning 401 | IMMEDIATE emergency rollback |
| **P0 - Critical** | Service failures | > 50% of service calls failing | IMMEDIATE emergency rollback |
| **P1 - High** | Authentication failures | > 20% failure rate for 10 minutes | Emergency rollback within 5 minutes |
| **P1 - High** | Error rate spike | > 5x baseline for 10 minutes | Emergency rollback within 5 minutes |
| **P2 - Medium** | Performance degradation | > 100ms auth latency for 30 minutes | Plan standard rollback |
| **P2 - Medium** | Intermittent failures | < 5% failure rate but persistent | Plan standard rollback |

**Execute Standard Rollback When:**
- Non-critical issues during maintenance window
- Testing rollback procedures
- Preparing for system upgrades
- Compliance or audit requirements

### Post-Rollback Actions

**After Emergency Rollback:**

1. **Immediate (within 1 hour):**
   - Incident report documenting issue and rollback
   - Root cause analysis initiated
   - Team notification sent

2. **Short-term (within 24 hours):**
   - Complete root cause analysis
   - Develop fix for identified issue
   - Test fix in staging environment
   - Plan re-deployment timeline

3. **Before Re-Deployment:**
   - Fix validated and tested
   - Rollback procedure verified working
   - Team trained on new monitoring procedures
   - Enhanced monitoring in place

**After Standard Rollback:**

1. Document reason for rollback
2. Identify improvements needed
3. Update deployment procedures
4. Schedule re-deployment when ready

---

## 📊 Monitoring & Validation

### Key Performance Indicators (KPIs)

**Authentication Metrics:**

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| **Auth Success Rate** | > 99% | < 98% | < 95% |
| **Auth Latency (p95)** | < 10ms | > 25ms | > 50ms |
| **Failed Auth Rate** | < 1% | > 2% | > 5% |
| **Rate Limit Events** | 0/hour | > 5/hour | > 20/hour |

**Service Health:**

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| **Backend Uptime** | 100% | < 99.9% | < 99.5% |
| **Service Availability** | 100% | < 99.9% | < 99% |
| **Error Rate** | < 0.1% | > 0.5% | > 1% |
| **Request Latency (p95)** | < 100ms | > 250ms | > 500ms |

**Security Metrics:**

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| **Unauthorized Access Attempts** | 0/hour | > 10/hour | > 50/hour |
| **Invalid Signatures** | 0/hour | > 5/hour | > 20/hour |
| **Timestamp Violations** | 0/hour | > 1/hour | > 10/hour |
| **Service Key TTL** | > 30 days | < 30 days | < 14 days |

### Monitoring Commands Reference

**Quick Health Check:**
```bash
curl -s http://172.16.168.20:8001/api/health | jq
```

**Authentication Metrics (Last Hour):**
```bash
cutoff=$(date -d '1 hour ago' '+%Y-%m-%d %H:%M')

echo "Successful: $(grep 'Service authenticated successfully' logs/backend.log | awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)"
echo "Failed: $(grep 'Service authentication FAILED' logs/backend.log | awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)"
echo "Blocked: $(grep 'request BLOCKED' logs/backend.log | awk -v c="$cutoff" '$1" "$2 >= c' | wc -l)"
```

**Service Activity:**
```bash
grep "Service authenticated successfully" logs/backend.log | \
  tail -100 | \
  grep -o 'service_id=[^ ]*' | \
  sort | uniq -c
```

**Service Key Status:**
```bash
for key in main-backend frontend npu-worker redis-stack ai-stack browser-service; do
  ttl=$(redis-cli -h 172.16.168.23 -a "$REDIS_PASSWORD" TTL "service:key:$key" 2>/dev/null)
  days=$((ttl / 86400))
  echo "$key: $days days"
done
```

**Clock Synchronization:**
```bash
for vm in 20 21 22 23 24 25; do
  echo -n "VM $vm: "
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.$vm "date '+%s'" 2>/dev/null
done
```

### Validation Test Suite

**Comprehensive Validation Script:**

```bash
#!/bin/bash
# scripts/validation/comprehensive-service-auth-test.sh

echo "=== Comprehensive Service Auth Validation ==="
echo "Timestamp: $(date)"
echo

# Test 1: Backend Health
echo "[Test 1] Backend Health Check"
health=$(curl -s http://172.16.168.20:8001/api/health | jq -r '.status')
if [ "$health" = "healthy" ]; then
    echo "✅ PASSED: Backend is healthy"
else
    echo "❌ FAILED: Backend health check failed ($health)"
fi
echo

# Test 2: Frontend Accessibility (Exempt Paths)
echo "[Test 2] Frontend Accessibility Test"
passed=0
failed=0

for path in "/api/chat" "/api/settings" "/api/knowledge" "/api/terminal"; do
    status=$(curl -s -o /dev/null -w '%{http_code}' "http://172.16.168.20:8001$path")
    if [ "$status" = "200" ] || [ "$status" = "404" ]; then
        echo "✅ $path: $status"
        ((passed++))
    else
        echo "❌ $path: $status (expected 200 or 404)"
        ((failed++))
    fi
done

echo "Frontend accessibility: $passed passed, $failed failed"
echo

# Test 3: Service-Only Path Blocking
echo "[Test 3] Service-Only Path Blocking Test"
passed=0
failed=0

for path in "/api/npu/internal" "/api/ai-stack/internal" "/api/browser/internal"; do
    status=$(curl -s -o /dev/null -w '%{http_code}' "http://172.16.168.20:8001$path")
    if [ "$status" = "401" ] || [ "$status" = "403" ]; then
        echo "✅ $path: Blocked ($status)"
        ((passed++))
    else
        echo "❌ $path: NOT blocked ($status)"
        ((failed++))
    fi
done

echo "Service-only blocking: $passed passed, $failed failed"
echo

# Test 4: Service Authentication Verification
echo "[Test 4] Service Authentication Verification"

# Check recent authenticated calls from each service
for service in npu-worker ai-stack browser-service; do
    count=$(grep "Service authenticated successfully" logs/backend.log | \
            grep "service_id=$service" | tail -10 | wc -l)

    if [ "$count" -gt 0 ]; then
        echo "✅ $service: $count recent authenticated calls"
    else
        echo "⚠️ $service: No recent authenticated calls (may be normal if idle)"
    fi
done
echo

# Test 5: Service Key Status
echo "[Test 5] Service Key Status"

all_keys_ok=true
for key in main-backend frontend npu-worker redis-stack ai-stack browser-service; do
    ttl=$(redis-cli -h 172.16.168.23 -a "$REDIS_PASSWORD" TTL "service:key:$key" 2>/dev/null)

    if [ "$ttl" -gt 2592000 ]; then  # > 30 days
        days=$((ttl / 86400))
        echo "✅ $key: $days days remaining"
    elif [ "$ttl" -gt 0 ]; then
        days=$((ttl / 86400))
        echo "⚠️ $key: $days days remaining (renewal recommended)"
        all_keys_ok=false
    else
        echo "❌ $key: EXPIRED or missing"
        all_keys_ok=false
    fi
done
echo

# Test 6: Clock Synchronization
echo "[Test 6] Clock Synchronization Test"

times=()
for vm in 20 21 22 23 24 25; do
    t=$(ssh -i ~/.ssh/autobot_key autobot@172.16.168.$vm "date '+%s'" 2>/dev/null || echo "0")
    times+=($t)
done

max=${times[0]}
min=${times[0]}
for t in "${times[@]}"; do
    ((t > max)) && max=$t
    ((t < min && t > 0)) && min=$t
done

drift=$((max - min))

if [ "$drift" -lt 100 ]; then
    echo "✅ Clock drift: ${drift}s (< 100s threshold)"
elif [ "$drift" -lt 300 ]; then
    echo "⚠️ Clock drift: ${drift}s (approaching 300s limit)"
else
    echo "❌ Clock drift: ${drift}s (exceeds 300s limit)"
fi
echo

# Summary
echo "=== Validation Summary ==="
echo "Overall Status: All critical tests must pass"
echo
echo "Next Steps:"
echo "- If all tests passed: System is operating correctly"
echo "- If any tests failed: Investigate and resolve issues"
echo "- Monitor logs for authentication patterns"
echo
echo "=== Validation Complete ==="
```

**Usage:** `bash scripts/validation/comprehensive-service-auth-test.sh`

---

## ⚠️ Risk Matrix & Mitigation

### Risk Assessment

| Risk | Probability | Impact | Severity | Mitigation |
|------|-------------|--------|----------|------------|
| **Service disruption during rollout** | Low | High | 🟡 Medium | Phased rollout, comprehensive testing, fast rollback |
| **Authentication overhead impacts performance** | Low | Medium | 🟢 Low | < 10ms overhead validated, monitoring in place |
| **Service key compromise** | Very Low | Critical | 🟡 Medium | Secure storage (600 perms), rotation schedule, audit logging |
| **Clock drift causes timestamp failures** | Low | Medium | 🟢 Low | NTP sync monitoring, 300s window tolerance |
| **Misconfigured service breaks** | Medium | High | 🟡 Medium | Comprehensive validation before each phase, rollback ready |
| **Frontend access accidentally blocked** | Low | High | 🟡 Medium | 85 exempt paths defined, extensive testing |
| **Internal endpoint exposed without auth** | Low | Critical | 🟡 Medium | 16 service-only paths defined, security validation |
| **Rollback procedure fails** | Very Low | Critical | 🟡 Medium | Tested rollback procedures, multiple rollback methods |

### Mitigation Strategies

**For Service Disruption:**
- ✅ Phased rollout (4 phases over 4-6 days)
- ✅ Comprehensive testing at each phase
- ✅ Fast rollback capability (< 2 minutes)
- ✅ 24-hour monitoring periods between phases
- ✅ Automated health checks and circuit breakers

**For Performance Impact:**
- ✅ Signature caching to reduce computation
- ✅ Connection pooling for Redis lookups
- ✅ Performance validation at each phase
- ✅ < 10ms overhead target enforced

**For Security:**
- ✅ Service keys stored with 600 permissions
- ✅ 90-day key rotation schedule
- ✅ Audit logging for all auth events
- ✅ Rate limiting on auth failures
- ✅ Comprehensive endpoint categorization

**For Configuration:**
- ✅ Validation scripts for each service
- ✅ Go/No-Go criteria at each phase
- ✅ Comprehensive documentation
- ✅ Team training on procedures

---

## 📅 Implementation Timeline

### Day-by-Day Execution Schedule

**Prerequisite:** Day 3 24-hour monitoring period complete

#### Day 1-3: Phase 1 (Service Client Migration)

**Day 1:**
- Hour 1-2: Verify Day 3 monitoring complete, review metrics
- Hour 3-5: Update NPU Worker configuration (Step 1.2)
- Hour 6-8: Update AI Stack configuration (Step 1.3)

**Day 2:**
- Hour 1-3: Update Browser Service configuration (Step 1.4)
- Hour 4-5: Evaluate Frontend service auth need (Step 1.5)
- Hour 6-8: Phase 1 validation testing (Step 1.6)

**Day 3:**
- Hour 1-4: Extended Phase 1 validation and monitoring
- Hour 5-6: Phase 1 completion review
- Hour 7-8: Prepare for Phase 2 (soft enforcement infrastructure)

**Phase 1 Gate:** All validation criteria met, Go/No-Go decision

#### Day 4-5: Phase 2 (Soft Enforcement)

**Day 4:**
- Hour 1-3: Prepare soft enforcement infrastructure (Step 2.1)
- Hour 4: Enable soft enforcement mode (Step 2.2)
- Hour 5-8: Intensive monitoring (first 4 hours)

**Day 5:**
- Hour 1-24: Continuous monitoring and validation (Step 2.3)
- Hour 12-16: Functional validation testing (Step 2.4)

**Phase 2 Gate:** 24+ hours stable enforcement, all criteria met

#### Day 6: Phase 3 (Circuit Breaker)

**Day 6:**
- Hour 1-3: Implement circuit breaker logic (Step 3.1)
- Hour 4-10: Execute circuit breaker ramp (Step 3.2)
  - Hour 4: 10% enforcement (60 min)
  - Hour 5: 25% enforcement (60 min)
  - Hour 6-7: 50% enforcement (120 min)
  - Hour 8-9: 75% enforcement (120 min)
  - Hour 10: 100% enforcement reached
- Hour 11-12: Phase 3 validation (Step 3.3)

**Phase 3 Gate:** 100% enforcement validated, all criteria met

#### Day 7+: Phase 4 (Full Enforcement & Production)

**Day 7:**
- Hour 1-2: Remove safety mechanisms (Step 4.1)
- Hour 3-5: Production hardening (Step 4.2)
- Hour 6-8: Long-term monitoring setup (Step 4.3)

**Ongoing:**
- Daily monitoring reports
- Weekly service key TTL checks
- Monthly rollback procedure drills
- Quarterly security audits

### Critical Path Analysis

**Minimum Timeline:** 6 days (if all phases pass first time)
**Realistic Timeline:** 7-10 days (accounting for validation extensions)
**Maximum Timeline:** 14 days (if multiple iterations needed)

**Critical Path:**
1. Day 3 monitoring completion (prerequisite)
2. Phase 1 service client migration (2-3 days)
3. Phase 2 soft enforcement validation (1-2 days)
4. Phase 3 circuit breaker ramp (1 day)
5. Phase 4 production hardening (1 day)

**Parallel Activities:**
- Monitoring infrastructure setup (during Phase 1)
- Documentation updates (throughout rollout)
- Team training (during Phase 2)

---

## 🎓 Team Training & Documentation

### Required Training

**Before Rollout:**

1. **Security Team:**
   - Service authentication architecture
   - HMAC-SHA256 signature validation
   - Endpoint categorization strategy
   - Security validation procedures

2. **Operations Team:**
   - Phased rollout procedures
   - Monitoring requirements
   - Rollback procedures (emergency + standard)
   - Incident response protocols

3. **Development Team:**
   - ServiceHTTPClient usage
   - Authentication header requirements
   - Debugging authentication failures
   - Service key rotation procedures

### Documentation Updates Required

**During Rollout:**

1. Update `/home/kali/Desktop/AutoBot/docs/security/SERVICE_AUTH_ENFORCEMENT_ROLLOUT_PLAN.md` (this document)
2. Update `docs/deployment/SERVICE_AUTHENTICATION.md` with final configuration
3. Update `docs/api/SERVICE_TO_SERVICE_API.md` with authentication requirements
4. Update `docs/troubleshooting/SERVICE_AUTH_ISSUES.md` with common problems
5. Update `CLAUDE.md` with final architecture notes

**Post-Rollout:**

1. Create `docs/operations/SERVICE_AUTH_RUNBOOK.md` for daily operations
2. Create `docs/security/SERVICE_AUTH_INCIDENT_RESPONSE.md` for incident handling
3. Update `docs/developer/PHASE_5_DEVELOPER_SETUP.md` with service auth setup
4. Document lessons learned in `docs/retrospectives/SERVICE_AUTH_ROLLOUT.md`

---

## 📞 Support & Escalation

### Incident Response

**P0 - Critical (Immediate Response):**
- Backend down > 1 minute
- Frontend completely inaccessible
- > 50% service failures

**Actions:**
1. Execute emergency rollback immediately
2. Notify all stakeholders
3. Begin incident investigation
4. Document timeline and actions

**P1 - High (Response within 5 minutes):**
- Authentication failures > 20%
- Error rate spike > 5x baseline
- Service degradation

**Actions:**
1. Assess severity
2. Prepare rollback if worsening
3. Investigate root cause
4. Escalate if needed

**P2 - Medium (Response within 1 hour):**
- Intermittent failures < 5%
- Performance degradation
- Non-critical warnings

**Actions:**
1. Monitor trends
2. Investigate during business hours
3. Plan fixes for next maintenance window

### Contact Information

**Escalation Path:**

1. **Level 1:** Operations Team (monitoring, basic troubleshooting)
2. **Level 2:** Development Team (code-level debugging)
3. **Level 3:** Architecture Team (design decisions, major changes)
4. **Level 4:** Executive Team (business impact decisions)

### Emergency Contacts

**Critical Issues:** Execute emergency rollback first, notify after

---

## ✅ Pre-Flight Checklist

**Before Starting Phase 1:**

- [ ] Day 3 24-hour monitoring period complete (>= 24 hours elapsed)
- [ ] All 6 service keys present in Redis (TTL > 85 days)
- [ ] Backend uptime 100% during monitoring period
- [ ] Zero timestamp violations in logs
- [ ] Zero signature failures from legitimate services
- [ ] Clock drift < 100 seconds across all VMs
- [ ] Rollback scripts tested and ready
- [ ] Monitoring infrastructure operational
- [ ] Team trained on procedures
- [ ] Documentation reviewed and approved
- [ ] Stakeholders notified of rollout schedule

**If ANY item not checked:** Resolve before proceeding

---

## 📚 Appendices

### Appendix A: Complete Endpoint Lists

**85 Frontend-Accessible Paths (EXEMPT):**

See "Endpoint Categorization" section for complete list.

**16 Service-Only Paths (REQUIRE AUTH):**

See "Endpoint Categorization" section for complete list.

### Appendix B: Configuration Examples

**Service .env Configuration:**
```env
SERVICE_ID=npu-worker
SERVICE_KEY_FILE=/etc/autobot/service-keys/npu-worker.env
AUTH_TIMESTAMP_WINDOW=300
BACKEND_HOST=172.16.168.20
BACKEND_PORT=8001
```

**Service Key File Format:**
```env
SERVICE_KEY=ca164d91b9ae28ff1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f
```

### Appendix C: Useful Commands

**Service Auth Status:**
```bash
# Check enforcement mode
grep SERVICE_AUTH_ENFORCEMENT_MODE .env

# View recent auth activity
tail -100 logs/backend.log | grep "service"

# Count auth events (last hour)
grep "Service authenticated successfully" logs/backend.log | \
  awk -v cutoff="$(date -d '1 hour ago' '+%Y-%m-%d %H:%M')" '$1" "$2 >= cutoff' | wc -l
```

**Service Key Management:**
```bash
# Check service key TTL
redis-cli -h 172.16.168.23 -a "$REDIS_PASSWORD" TTL "service:key:main-backend"

# List all service keys
redis-cli -h 172.16.168.23 -a "$REDIS_PASSWORD" KEYS "service:key:*"

# View service key value (for verification only)
redis-cli -h 172.16.168.23 -a "$REDIS_PASSWORD" GET "service:key:main-backend"
```

**Clock Synchronization:**
```bash
# Force NTP sync on VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.22 "sudo ntpdate -u pool.ntp.org"

# Check time across all VMs
for vm in 20 21 22 23 24 25; do
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.$vm "echo \"VM $vm: \$(date)\""
done
```

### Appendix D: Troubleshooting Guide

**Issue: Service authentication failing**

Check:
1. Service key present in Redis: `redis-cli GET "service:key:<service-id>"`
2. Service key file readable: `cat /etc/autobot/service-keys/<service>.env`
3. Environment variables set: `echo $SERVICE_ID; echo $SERVICE_KEY_FILE`
4. Clock synchronization: Check time drift across VMs
5. Backend logs: `grep "signature validation" logs/backend.log`

**Issue: Frontend returning 401 errors**

Check:
1. Path is in EXEMPT_PATHS list
2. Enforcement middleware configuration
3. Backend logs: `grep "exempt path" logs/backend.log`

**Issue: Service-only path not blocked**

Check:
1. Path is in SERVICE_ONLY_PATHS list
2. Enforcement mode enabled: `grep SERVICE_AUTH_ENFORCEMENT_MODE .env`
3. Middleware active: `grep "ENFORCEMENT MODE enabled" logs/backend.log`

---

## 📝 Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-09 | Claude (Sonnet 4.5) | Initial comprehensive rollout plan created |

---

## 🎯 Summary & Quick Reference

### Quick Start Checklist

**Ready to Deploy? Verify:**
- ✅ Day 3 monitoring complete
- ✅ All prerequisites met
- ✅ Team trained
- ✅ Rollback tested
- ✅ Monitoring operational

**Rollout Sequence:**
1. Phase 1: Configure remote services (2-3 days)
2. Phase 2: Enable soft enforcement (1-2 days)
3. Phase 3: Circuit breaker ramp (1 day)
4. Phase 4: Production hardening (ongoing)

**Emergency Contact:**
- Execute `bash scripts/EMERGENCY-ROLLBACK.sh`
- Notify team after rollback complete

### Success Metrics

**Deployment successful when:**
- ✅ Zero service disruptions
- ✅ All service-to-service calls authenticated
- ✅ Frontend access maintained
- ✅ CVSS 10.0 vulnerability eliminated
- ✅ Performance within targets (< 10ms overhead)

---

**Document Status:** 🟡 PENDING APPROVAL
**Next Action:** Phase 1 execution (after Day 3 monitoring complete)
**Estimated Completion:** 4-6 days from Phase 1 start

**Questions or concerns? Review this plan with team before proceeding.**

---
