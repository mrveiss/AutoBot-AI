# Phase 3: Service Discovery & Agent Config Migration Design (Issue #760)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create client libraries for service discovery and migrate agent LLM config from local files to SLM.

**Architecture:** Backend and frontend query SLM for service URLs and agent LLM configs. Local config serves as temporary fallback during migration, then gets phased out.

**Tech Stack:** Python (aiohttp), TypeScript, Vue 3, FastAPI

---

## 1. Service Discovery Client

### 1.1 Python Client (Backend)

Add to existing `backend/services/slm_client.py`:

```python
class ServiceDiscoveryCache:
    """Cache for discovered service URLs with TTL."""

    def __init__(self, ttl_seconds: int = 60):
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds

    def get(self, service_name: str) -> Optional[str]:
        entry = self._cache.get(service_name)
        if entry and not entry.is_expired():
            return entry.config.get("url")
        return None

    def set(self, service_name: str, discovery_data: dict):
        self._cache[service_name] = CacheEntry(
            config=discovery_data,
            expires_at=time.time() + self._ttl
        )


# Service name to env var mapping
ENV_VAR_MAP = {
    "autobot-backend": "AUTOBOT_BACKEND_URL",
    "redis": "REDIS_URL",
    "ollama": "OLLAMA_URL",
    "slm-server": "SLM_URL",
    "npu-worker": "NPU_WORKER_URL",
    "ai-stack": "AI_STACK_URL",
    "browser-service": "BROWSER_SERVICE_URL",
}


async def discover_service(service_name: str) -> str:
    """Discover service URL with fallback to env vars."""
    # 1. Check cache
    cached = _discovery_cache.get(service_name)
    if cached:
        return cached

    # 2. Try SLM
    url = await _fetch_from_slm(service_name)
    if url:
        _discovery_cache.set(service_name, {"url": url})
        return url

    # 3. Env var fallback
    env_url = _get_env_fallback(service_name)
    if env_url:
        return env_url

    # 4. Error - not configured
    raise ServiceNotConfiguredError(
        f"Service '{service_name}' not found in SLM or environment"
    )
```

### 1.2 TypeScript Client (Frontend)

Add to `autobot-vue/src/config/ssot-config.ts`:

```typescript
interface DiscoveredService {
  url: string;
  healthy: boolean;
  host: string;
  port?: number;
}

const discoveryCache = new Map<string, { data: DiscoveredService; expiresAt: number }>();
const CACHE_TTL_MS = 60000;

export async function discoverService(
  serviceName: string,
  authToken: string
): Promise<string> {
  // 1. Check cache
  const cached = discoveryCache.get(serviceName);
  if (cached && Date.now() < cached.expiresAt) {
    return cached.data.url;
  }

  // 2. Try SLM
  try {
    const response = await fetch(
      `${getConfig().slmUrl}/api/discover/${serviceName}`,
      { headers: { Authorization: `Bearer ${authToken}` } }
    );
    if (response.ok) {
      const data: DiscoveredService = await response.json();
      discoveryCache.set(serviceName, {
        data,
        expiresAt: Date.now() + CACHE_TTL_MS
      });
      return data.url;
    }
  } catch (err) {
    console.warn(`SLM discovery failed for ${serviceName}:`, err);
  }

  // 3. Env var fallback (via existing getServiceUrl)
  const envUrl = getServiceUrl(serviceName);
  if (envUrl) return envUrl;

  // 4. Error
  throw new Error(`Service '${serviceName}' not configured`);
}
```

---

## 2. Agent LLM Config Migration

### 2.1 Current System (Local)

- 29 agents defined in `backend/api/agent_config.py`
- Stored in `unified_config_manager` (local YAML)
- Tiered models: TIER_1 through TIER_4

### 2.2 Target System (SLM)

- Agents stored in SLM `agents` table (Phase 2)
- Per-agent: provider, endpoint, model, API key (encrypted), timeout, temperature
- WebSocket push for real-time config changes

### 2.3 Migration Strategy

1. **Seed Script**: Create `slm-server/migrations/seed_agents.py`
   - Read `DEFAULT_AGENT_CONFIGS` from backend
   - Insert into SLM `agents` table
   - Map tiered models to LLM config

2. **Update Backend API**: Modify `backend/api/agent_config.py`
   - Replace `unified_config_manager` calls with SLM client
   - Use `get_agent_config(agent_id)` from `slm_client.py`
   - Keep local as temporary fallback

3. **Fallback Chain**:
   ```
   SLM Agent Config (primary)
       ↓ not found
   Local Config (temporary fallback)
       ↓ not found
   DEFAULT_AGENT_CONFIGS (hardcoded defaults)
   ```

### 2.4 Agent Model Mapping

| Local Tier | Default Model | SLM Provider |
|------------|---------------|--------------|
| TIER_1 | llama3.2:1b | ollama |
| TIER_2 | llama3.2:3b | ollama |
| TIER_3 | mistral:7b-instruct | ollama |
| TIER_4 | mistral:7b-instruct | ollama |

---

## 3. Fallback Chain Summary

### Service Discovery
```
Cache (60s TTL)
    ↓ miss
SLM /api/discover/{service_name}
    ↓ unavailable
Environment variable
    ↓ not set
Error (service must be configured)
```

### Agent LLM Config
```
SLM Agent Cache (300s TTL)
    ↓ miss
SLM /api/agents/{agent_id}/llm
    ↓ unavailable
Local unified_config_manager (temporary)
    ↓ not found
DEFAULT_AGENT_CONFIGS (seed data)
```

---

## 4. Phase 3 Scope

### In Scope
- [x] Resolve merge conflicts in slm-server
- [ ] Add service discovery to Python SLM client
- [ ] Create agent seed migration script
- [ ] Update `backend/api/agent_config.py` to use SLM
- [ ] Add TypeScript discovery functions
- [ ] Create Vue composable for reactive discovery
- [ ] Update GitHub issue with progress

### NOT in Scope
- Full migration of all code to use discovery (Phase 4)
- Frontend UI for agent management (future)
- Removing local config entirely (after stabilization)

---

## 5. Files to Modify

| File | Changes |
|------|---------|
| `backend/services/slm_client.py` | Add `ServiceDiscoveryCache`, `discover_service()` |
| `slm-server/migrations/seed_agents.py` | New: Seed agents from DEFAULT_AGENT_CONFIGS |
| `backend/api/agent_config.py` | Use SLM client instead of unified_config_manager |
| `autobot-vue/src/config/ssot-config.ts` | Add `discoverService()` |
| `autobot-vue/src/composables/useServiceDiscovery.ts` | New: Vue composable |

---

## 6. Testing

- Unit tests for cache TTL behavior
- Integration test: SLM down → fallback to env vars
- Integration test: SLM up → returns discovered URL
- Verify agent config fetch from SLM works
- Verify WebSocket push updates cache
