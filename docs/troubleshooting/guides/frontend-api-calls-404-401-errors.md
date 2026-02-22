# Frontend API Calls Return 404/401 Errors

**Issue Number**: #810, #822
**Date Reported**: 2026-02-09
**Severity**: High
**Component**: Frontend / Backend API

---

## Symptoms

- Frontend shows "Network Error" or "Unauthorized" messages
- Browser DevTools shows 404 (Not Found) or 401 (Unauthorized) errors
- API calls fail despite backend service running
- Features appear broken or return empty data
- User authentication fails repeatedly

## Root Cause

**Multiple API connectivity issues**:
1. **API Client not installed**: `ApiPlugin` not registered in `main.ts`
2. **URL mismatches**: Frontend calls `/api/control/` but backend expects `/api/advanced-control/`
3. **Missing CORS**: Frontend VM not in backend's CORS origins list
4. **Dual implementations**: Both `.js` and `.ts` versions of API clients causing conflicts
5. **Router not registered**: Feature routers not mounted in `feature_routers.py`
6. **Wrong response handling**: API client expects `Response` objects but gets parsed JSON

## Quick Fix

```bash
# 1. Check if backend is running and accessible
curl https://172.16.168.20:8443/api/health

# 2. Check CORS configuration
grep -r "get_cors_origins" autobot-user-backend/

# 3. Verify API routes are registered
curl https://172.16.168.20:8443/docs | grep -i "advanced-control"

# 4. Check frontend API client configuration
grep -r "ApiClient" autobot-user-frontend/src/ | grep import
```

## Detailed Resolution Steps

### Step 1: Install API Plugin in Frontend

**File**: `autobot-user-frontend/src/main.ts`

```typescript
import { ApiPlugin } from '@/plugins/api'

const app = createApp(App)
app.use(ApiPlugin)  // Add this line
app.mount('#app')
```

### Step 2: Fix URL Mismatches

Common mismatches and their fixes:

| Component | Wrong URL | Correct URL |
|-----------|-----------|-------------|
| AdvancedControlApiClient | `/api/control/` | `/api/advanced-control/` |
| useWorkflowBuilder | `/api/workflow_automation/` | `/api/workflow-automation/` |
| usePerformanceMonitoring | `/api/performance/overview` | `/api/performance/` |

**Fix in API clients**:
```typescript
// autobot-user-frontend/src/api/AdvancedControlApiClient.ts
const BASE_URL = '/api/advanced-control'  // NOT /api/control

// autobot-user-frontend/src/composables/useWorkflowBuilder.ts
const API_URL = '/api/workflow-automation'  // NOT /api/workflow_automation
```

### Step 3: Add Frontend VM to CORS Origins

**File**: `autobot-user-backend/config.py`

```python
from autobot_shared.ssot_config import NetworkConstants

def get_cors_origins():
    """Get CORS origins from infrastructure config."""
    origins = []
    for host_config in NetworkConstants.get_host_configs():
        # Add HTTP and HTTPS for each host
        origins.append(f"http://{host_config['ip']}")
        origins.append(f"https://{host_config['ip']}")
    return origins
```

Ensure this includes `172.16.168.21` (Frontend VM).

### Step 4: Remove Duplicate JS/TS Files

```bash
# Find dual implementations
find autobot-user-frontend/src -name "*.js" -o -name "*.ts" | sort | uniq -d

# Remove .js versions if .ts exists
rm autobot-user-frontend/src/api/ApiClient.js
rm autobot-user-frontend/src/services/api.js

# Update imports to use .ts versions
grep -rl "from.*ApiClient.js" autobot-user-frontend/src/ | xargs sed -i 's/ApiClient\.js/ApiClient.ts/g'
```

### Step 5: Register Missing Routers

**File**: `autobot-user-backend/api/feature_routers.py`

```python
from api.endpoints import feature_flags

app.include_router(
    feature_flags.router,
    prefix="/admin/api/feature-flags",
    tags=["Feature Flags"]
)
```

### Step 6: Fix API Client Response Handling

**File**: `autobot-user-frontend/src/api/ApiClient.ts`

```typescript
async post<T>(endpoint: string, data: any): Promise<T> {
  const response = await fetch(`${this.baseURL}${endpoint}`, {
    method: 'POST',
    headers: this.getHeaders(),
    body: JSON.stringify(data)
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T
  }

  return await response.json()  // Return parsed JSON, not Response object
}
```

## Verification

```bash
# 1. Check API health
curl https://172.16.168.20:8443/api/health

# 2. Test specific endpoints
curl https://172.16.168.20:8443/api/advanced-control/status

# 3. Check CORS headers
curl -H "Origin: http://172.16.168.21" -I https://172.16.168.20:8443/api/health

# Should include:
# Access-Control-Allow-Origin: http://172.16.168.21

# 4. Verify routes in OpenAPI docs
curl https://172.16.168.20:8443/docs
```

**Success Indicators**:
- No 404 errors in browser console
- No 401 errors for authenticated requests
- CORS headers present in responses
- API calls return expected data
- No duplicate API client imports

## Prevention

1. **Use TypeScript exclusively** - delete all `.js` API clients
2. **Centralize API URLs** - use SSOT config for all endpoints
3. **Test API calls** after any backend routing changes:
   ```bash
   curl http://localhost:8001/api/<endpoint>
   ```
4. **Monitor CORS** - ensure all VMs in NetworkConstants are included
5. **Code review checklist**:
   - [ ] Router registered in `feature_routers.py`
   - [ ] Frontend URL matches backend route
   - [ ] CORS includes calling VM
   - [ ] No duplicate .js/.ts files

## Related Issues

- #811: WebSocket mixed content (wss:// not ws://)
- #815: Dynamic CORS from infrastructure machines
- #822: Endpoint URL mismatches

## References

- PR #810: API connectivity fixes
- Commit: `d4a8f9c2`
- File: `autobot-user-frontend/src/main.ts`
- File: `autobot-user-backend/config.py`
