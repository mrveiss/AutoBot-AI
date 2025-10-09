# Week 3 Task 3.6 - Service Authentication Enforcement Mode Deployment

**Status**: 🎯 READY TO BEGIN
**Prerequisites**: ✅ ALL MET
**Estimated Time**: 4-6 hours (gradual rollout)
**Risk Level**: LOW (gradual approach with quick rollback)

---

## Prerequisites Status - All Met ✅

### ✅ Infrastructure Deployed (Day 3 - Complete)

- Service keys: 6/6 deployed to Redis + files
- Environment configs: 6/6 VMs configured
- Backend middleware: Active (logging mode)
- Service HTTP client: Tested and working
- Monitoring baseline: Established (70 hours)

### ✅ Monitoring Complete (Phase 5 - Complete)

- Monitoring duration: 70 hours (exceeded 24-hour minimum)
- Invalid signatures: 0 (healthy)
- Timestamp violations: 0 (healthy)
- Service auth success: 100% (1/1 requests)
- Clock drift: 7 seconds (< 300s threshold)

### ✅ System Stability Verified

- Backend uptime: 100%
- Redis connectivity: 100%
- VM connectivity: 100%
- Service keys TTL: 85+ days remaining
- No authentication errors from legitimate services

---

## Deployment Overview

### Phase 1: Remote Service Updates (2-3 hours)

**Objective**: Deploy ServiceHTTPClient to all remote services

**Services to Update**:
1. NPU Worker (172.16.168.22:8081)
2. AI Stack (172.16.168.24:8080)
3. Browser Service (172.16.168.25:3000)

**Tasks**:
- Add ServiceHTTPClient to service codebase
- Update service initialization to use authenticated client
- Configure environment to load service credentials
- Test authenticated requests to backend
- Verify no regression in functionality

### Phase 2: Endpoint Configuration (1 hour)

**Objective**: Configure service auth exemptions for frontend

**Tasks**:
- Identify all frontend-accessible endpoints
- Configure exemption list in middleware
- Document endpoint access patterns
- Update middleware to enforce selectively

### Phase 3: Gradual Enforcement (1-2 hours)

**Objective**: Activate enforcement mode incrementally

**Strategy**:
- Start with internal service-to-service endpoints only
- Monitor for 30 minutes per increment
- Expand to additional endpoints gradually
- Full enforcement after successful incremental rollout

### Phase 4: Monitoring & Validation (30 minutes)

**Objective**: Verify enforcement mode working correctly

**Tasks**:
- Monitor authentication logs for failures
- Verify legitimate services not blocked
- Check frontend functionality unchanged
- Validate performance impact minimal

---

## Phase 1: Remote Service Updates

### 1.1 NPU Worker Service (172.16.168.22:8081)

#### Current State

**Location**: `/home/autobot/npu-worker/`
**Service Type**: FastAPI application
**Backend Calls**: Yes (sends inference results)

#### Required Changes

**File**: `npu-worker/utils/backend_client.py` (new file)

```python
"""Backend HTTP Client for NPU Worker"""

import os
from backend.utils.service_client import create_service_client_from_env

# Global client instance
_backend_client = None

def get_backend_client():
    """Get authenticated backend HTTP client."""
    global _backend_client
    if _backend_client is None:
        _backend_client = create_service_client_from_env()
    return _backend_client

async def send_inference_result(task_id: str, result: dict):
    """Send inference result to backend with authentication."""
    client = get_backend_client()
    backend_url = os.getenv("BACKEND_HOST", "172.16.168.20")
    backend_port = os.getenv("BACKEND_PORT", "8001")

    response = await client.post(
        f"http://{backend_url}:{backend_port}/api/npu/results/{task_id}",
        json=result
    )
    return response
```

**Environment Already Configured**:
- `/etc/autobot/.env` has `SERVICE_ID=npu-worker`
- `/etc/autobot/service-keys/npu-worker.env` has service key

**Deployment Steps**:
1. Sync `backend/utils/service_client.py` to NPU worker
2. Create `npu-worker/utils/backend_client.py`
3. Update NPU worker to use `send_inference_result()`
4. Test authenticated request to backend
5. Restart NPU worker service

### 1.2 AI Stack Service (172.16.168.24:8080)

#### Current State

**Location**: `/home/autobot/ai-stack/`
**Service Type**: Ollama + custom API
**Backend Calls**: Minimal (status reporting)

#### Required Changes

**File**: `ai-stack/utils/backend_client.py` (new file)

```python
"""Backend HTTP Client for AI Stack"""

import os
from backend.utils.service_client import create_service_client_from_env

_backend_client = None

def get_backend_client():
    """Get authenticated backend HTTP client."""
    global _backend_client
    if _backend_client is None:
        _backend_client = create_service_client_from_env()
    return _backend_client

async def report_status(status: dict):
    """Report AI stack status to backend with authentication."""
    client = get_backend_client()
    backend_url = os.getenv("BACKEND_HOST", "172.16.168.20")
    backend_port = os.getenv("BACKEND_PORT", "8001")

    response = await client.post(
        f"http://{backend_url}:{backend_port}/api/ai-stack/status",
        json=status
    )
    return response
```

**Environment Already Configured**:
- `/etc/autobot/.env` has `SERVICE_ID=ai-stack`
- `/etc/autobot/service-keys/ai-stack.env` has service key

### 1.3 Browser Service (172.16.168.25:3000)

#### Current State

**Location**: `/home/autobot/browser-service/`
**Service Type**: Playwright automation
**Backend Calls**: Yes (automation results, screenshots)

#### Required Changes

**File**: `browser-service/utils/backend_client.py` (new file)

```python
"""Backend HTTP Client for Browser Service"""

import os
from backend.utils.service_client import create_service_client_from_env

_backend_client = None

def get_backend_client():
    """Get authenticated backend HTTP client."""
    global _backend_client
    if _backend_client is None:
        _backend_client = create_service_client_from_env()
    return _backend_client

async def send_automation_result(task_id: str, result: dict):
    """Send automation result to backend with authentication."""
    client = get_backend_client()
    backend_url = os.getenv("BACKEND_HOST", "172.16.168.20")
    backend_port = os.getenv("BACKEND_PORT", "8001")

    response = await client.post(
        f"http://{backend_url}:{backend_port}/api/browser/results/{task_id}",
        json=result
    )
    return response

async def upload_screenshot(screenshot_data: bytes):
    """Upload screenshot to backend with authentication."""
    client = get_backend_client()
    backend_url = os.getenv("BACKEND_HOST", "172.16.168.20")
    backend_port = os.getenv("BACKEND_PORT", "8001")

    response = await client.post(
        f"http://{backend_url}:{backend_port}/api/browser/screenshots",
        files={"screenshot": screenshot_data}
    )
    return response
```

**Environment Already Configured**:
- `/etc/autobot/.env` has `SERVICE_ID=browser-service`
- `/etc/autobot/service-keys/browser-service.env` has service key

---

## Phase 2: Endpoint Configuration

### 2.1 Identify Frontend-Accessible Endpoints

Based on baseline monitoring, these endpoints receive frontend traffic:

```python
FRONTEND_ENDPOINTS = [
    "/api/chats",
    "/api/chats/*",
    "/api/system/health",
    "/api/monitoring/services/health",
    "/api/settings",
    "/api/settings/*",
    "/api/knowledge",
    "/api/knowledge/*",
    "/api/terminal",
    "/api/terminal/*",
    # Add additional frontend paths as discovered
]
```

### 2.2 Configure Middleware Exemptions

**File**: `backend/middleware/service_auth_enforcement.py` (update)

```python
"""Service Authentication Enforcement Middleware"""

from typing import List
from fastapi import Request, HTTPException
from backend.security.service_auth import ServiceAuthManager
import structlog

logger = structlog.get_logger()

# Endpoints that don't require service authentication
EXEMPT_PATHS: List[str] = [
    "/api/chats",
    "/api/system/health",
    "/api/monitoring",
    "/api/settings",
    "/api/knowledge",
    "/api/terminal",
    "/docs",
    "/openapi.json",
]

# Endpoints that REQUIRE service authentication
SERVICE_ONLY_PATHS: List[str] = [
    "/api/npu",
    "/api/ai-stack",
    "/api/browser",
    "/api/internal",
]

def is_path_exempt(path: str) -> bool:
    """Check if path is exempt from service authentication."""
    for exempt in EXEMPT_PATHS:
        if path.startswith(exempt):
            return True
    return False

def requires_service_auth(path: str) -> bool:
    """Check if path requires service authentication."""
    for service_path in SERVICE_ONLY_PATHS:
        if path.startswith(service_path):
            return True
    return False

async def enforce_service_auth(request: Request, call_next):
    """Enforce service authentication on required endpoints."""
    path = request.url.path

    # Skip exempt paths
    if is_path_exempt(path):
        return await call_next(request)

    # Enforce on service-only paths
    if requires_service_auth(path):
        # Validate authentication
        auth_manager = ServiceAuthManager(redis_client=...)

        try:
            service_info = await auth_manager.validate_signature(request)
            request.state.service_id = service_info["service_id"]
            logger.info("Service authenticated", service_id=service_info["service_id"], path=path)
        except HTTPException as e:
            logger.error("Service auth failed", path=path, error=str(e))
            raise  # Block request in enforcement mode

    return await call_next(request)
```

### 2.3 Update Middleware Registration

**File**: `backend/app_factory.py` (update)

```python
# Add enforcement middleware after logging middleware
if os.getenv("SERVICE_AUTH_ENFORCEMENT_MODE", "false").lower() == "true":
    from backend.middleware.service_auth_enforcement import enforce_service_auth
    app.middleware("http")(enforce_service_auth)
    logger.info("✅ Service Authentication ENFORCEMENT MODE enabled")
else:
    logger.info("ℹ️  Service Authentication in LOGGING MODE (enforcement disabled)")
```

---

## Phase 3: Gradual Enforcement Rollout

### 3.1 Enforcement Strategy

**Incremental Approach**:
1. Start with `/api/npu/*` endpoints only (30-minute test)
2. Add `/api/browser/*` endpoints (30-minute test)
3. Add `/api/ai-stack/*` endpoints (30-minute test)
4. Add `/api/internal/*` endpoints (30-minute test)
5. Full enforcement on all service-to-service paths

**Per-Increment Monitoring**:
```bash
# Check for authentication failures
grep "Service auth failed" logs/backend.log | tail -50

# Check for 401 errors
grep "401" logs/backend.log | grep -v "logging only" | tail -20

# Verify services still functioning
curl http://172.16.168.22:8081/health  # NPU Worker
curl http://172.16.168.24:8080/health  # AI Stack
curl http://172.16.168.25:3000/health  # Browser
```

### 3.2 Enforcement Activation

**Step 1**: Enable for service-only endpoints

```bash
# Update .env
echo "SERVICE_AUTH_ENFORCEMENT_MODE=true" >> .env

# Restart backend
bash run_autobot.sh --restart
```

**Step 2**: Monitor for 30 minutes

```bash
# Watch logs in real-time
tail -f logs/backend.log | grep "service"

# Check enforcement working
curl -X POST http://172.16.168.20:8001/api/npu/test
# Should return 401 Unauthorized (no auth headers)
```

**Step 3**: Verify authenticated requests work

```bash
# Test NPU worker authenticated request
env SERVICE_ID=npu-worker SERVICE_KEY_FILE=/etc/autobot/service-keys/npu-worker.env \
  python3 test_npu_client.py
# Should return 200 OK
```

### 3.3 Rollback Procedure (If Issues Detected)

**Quick Rollback** (< 2 minutes):
```bash
# Disable enforcement
sed -i 's/SERVICE_AUTH_ENFORCEMENT_MODE=true/SERVICE_AUTH_ENFORCEMENT_MODE=false/' .env

# Restart backend
bash run_autobot.sh --restart

# System returns to logging mode
```

---

## Phase 4: Monitoring & Validation

### 4.1 Success Metrics

After full enforcement, verify:

- ✅ All service-to-service requests authenticated successfully
- ✅ Frontend requests still working (exempt endpoints)
- ✅ No 401 errors from legitimate services
- ✅ Performance impact < 5% increase in response time
- ✅ System stability maintained

### 4.2 Monitoring Commands

```bash
# Authentication success rate (should be 100%)
grep "Service authenticated" logs/backend.log | wc -l

# Authentication failures (should be 0 from legitimate services)
grep "Service auth failed" logs/backend.log | grep -v "Missing headers" | wc -l

# 401 errors (should only be from unauthorized sources)
grep "401 Unauthorized" logs/backend.log | tail -20

# Service health checks
for vm in 22 24 25; do
  echo "VM $vm:"
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.$vm "curl -s localhost:8080/health 2>/dev/null || echo 'failed'"
done
```

---

## Timeline & Milestones

### Week 3 Task 3.6 Timeline

| Phase | Duration | Start | End | Status |
|-------|----------|-------|-----|--------|
| Phase 1: Service Updates | 2-3 hours | TBD | TBD | ⏳ Pending |
| Phase 2: Endpoint Config | 1 hour | TBD | TBD | ⏳ Pending |
| Phase 3: Gradual Enforcement | 1-2 hours | TBD | TBD | ⏳ Pending |
| Phase 4: Monitoring | 30 min | TBD | TBD | ⏳ Pending |
| **Total** | **4-6 hours** | - | - | - |

### Key Milestones

- ✅ Day 3 Deployment Complete (2025-10-06)
- ✅ 24-Hour Monitoring Complete (2025-10-07)
- ✅ Baseline Analysis Complete (2025-10-09)
- ⏳ Remote Services Updated (TBD)
- ⏳ Enforcement Mode Active (TBD)
- ⏳ Week 3 Complete (TBD)

---

## Risk Assessment

### Deployment Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Service blocking | LOW | HIGH | Gradual rollout, quick rollback |
| Clock drift | LOW | MEDIUM | Monitoring in place, 7s current drift |
| Service key expiry | LOW | HIGH | 85+ days remaining, alerts set |
| Performance degradation | LOW | LOW | HMAC validation is fast (<1ms) |

### Risk Mitigations in Place

1. **Gradual Rollout**: Incremental activation per endpoint group
2. **Quick Rollback**: < 2 minute rollback to logging mode
3. **Comprehensive Monitoring**: Real-time log monitoring during rollout
4. **Baseline Established**: Known good state to compare against
5. **Service Client Tested**: Authenticated requests verified working

---

## Success Criteria

### Enforcement Mode Operational

- [ ] All remote services use ServiceHTTPClient
- [ ] Endpoint exemptions configured correctly
- [ ] Service-to-service auth enforced on internal endpoints
- [ ] Frontend functionality unchanged
- [ ] Zero authentication failures from legitimate services
- [ ] Performance impact < 5%
- [ ] Monitoring shows 100% authentication success

### Week 3 Task 3.6 Complete

- [ ] Enforcement mode active and stable
- [ ] 24-hour monitoring after enforcement shows no issues
- [ ] Documentation updated
- [ ] Team trained on new authentication requirements
- [ ] Rollback procedures tested and documented

---

## Next Steps

1. **Begin Phase 1**: Update NPU Worker with ServiceHTTPClient
2. **Test Incrementally**: Verify each service works before moving to next
3. **Configure Exemptions**: Set up endpoint exemptions for frontend
4. **Activate Enforcement**: Gradual rollout per plan above
5. **Monitor & Validate**: 24-hour monitoring after full enforcement

---

**Plan Status**: 🎯 READY TO EXECUTE
**Prerequisites**: ✅ ALL MET
**Risk Level**: LOW (gradual approach with safety nets)
**Estimated Completion**: 4-6 hours active work + 24 hours monitoring
