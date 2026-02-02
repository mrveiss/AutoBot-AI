# Phase 3: Service Discovery & Agent Config Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create client libraries for service discovery and migrate agent LLM config from local files to SLM.

**Architecture:** Backend Python client and frontend TypeScript functions query SLM for service URLs and agent configs. Local config serves as temporary fallback during migration. Cache reduces network load (60s TTL for services, 300s for agents).

**Tech Stack:** Python (aiohttp), TypeScript, Vue 3, FastAPI, SQLAlchemy

---

## Task 1: Add ServiceDiscoveryCache to Python SLM Client

**Files:**
- Modify: `backend/services/slm_client.py:51-60`
- Test: `backend/tests/test_slm_client.py` (create if not exists)

**Step 1: Write the failing test**

Create test file at `backend/tests/test_slm_client.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM client service discovery."""

import time
import pytest

from backend.services.slm_client import ServiceDiscoveryCache


class TestServiceDiscoveryCache:
    """Test ServiceDiscoveryCache class."""

    def test_cache_miss_returns_none(self):
        """Cache returns None for unknown service."""
        cache = ServiceDiscoveryCache(ttl_seconds=60)
        assert cache.get("unknown-service") is None

    def test_cache_hit_returns_url(self):
        """Cache returns URL for known service."""
        cache = ServiceDiscoveryCache(ttl_seconds=60)
        cache.set("redis", {"url": "http://172.16.168.23:6379", "healthy": True})
        result = cache.get("redis")
        assert result == "http://172.16.168.23:6379"

    def test_cache_expires_after_ttl(self):
        """Cache entry expires after TTL."""
        cache = ServiceDiscoveryCache(ttl_seconds=1)
        cache.set("redis", {"url": "http://172.16.168.23:6379", "healthy": True})
        time.sleep(1.1)
        assert cache.get("redis") is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/AutoBot && python -m pytest backend/tests/test_slm_client.py -v`
Expected: FAIL with "ImportError: cannot import name 'ServiceDiscoveryCache'"

**Step 3: Write minimal implementation**

Add to `backend/services/slm_client.py` after line 60 (after `CacheEntry` class):

```python
class ServiceDiscoveryCache:
    """Cache for discovered service URLs with TTL."""

    def __init__(self, ttl_seconds: int = 60):
        """
        Initialize service discovery cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 60)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds

    def get(self, service_name: str) -> Optional[str]:
        """
        Get cached URL for service.

        Args:
            service_name: Service identifier

        Returns:
            Cached URL or None if not found/expired
        """
        entry = self._cache.get(service_name)
        if entry and not entry.is_expired():
            logger.debug("Service discovery cache hit for %s", service_name)
            return entry.config.get("url")
        elif entry:
            logger.debug("Service discovery cache expired for %s", service_name)
            del self._cache[service_name]
        return None

    def set(self, service_name: str, discovery_data: dict) -> None:
        """
        Store discovery data in cache.

        Args:
            service_name: Service identifier
            discovery_data: Dict with url, healthy, etc.
        """
        expires_at = time.time() + self._ttl
        self._cache[service_name] = CacheEntry(
            config=discovery_data, expires_at=expires_at
        )
        logger.debug(
            "Cached service discovery for %s (TTL: %ds)", service_name, self._ttl
        )

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()
        logger.debug("Cleared service discovery cache")
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/AutoBot && python -m pytest backend/tests/test_slm_client.py::TestServiceDiscoveryCache -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/services/slm_client.py backend/tests/test_slm_client.py
git commit -m "feat(slm-client): add ServiceDiscoveryCache class (#760)"
```

---

## Task 2: Add discover_service() Function to Python SLM Client

**Files:**
- Modify: `backend/services/slm_client.py`
- Test: `backend/tests/test_slm_client.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_slm_client.py`:

```python
import os
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.slm_client import (
    ServiceDiscoveryCache,
    ServiceNotConfiguredError,
    discover_service,
    ENV_VAR_MAP,
)


class TestDiscoverService:
    """Test discover_service function."""

    @pytest.mark.asyncio
    async def test_discover_service_from_cache(self):
        """Returns URL from cache when available."""
        with patch("backend.services.slm_client._discovery_cache") as mock_cache:
            mock_cache.get.return_value = "http://172.16.168.23:6379"
            url = await discover_service("redis")
            assert url == "http://172.16.168.23:6379"
            mock_cache.get.assert_called_once_with("redis")

    @pytest.mark.asyncio
    async def test_discover_service_env_fallback(self):
        """Falls back to env var when SLM unavailable."""
        with patch("backend.services.slm_client._discovery_cache") as mock_cache:
            mock_cache.get.return_value = None
            with patch("backend.services.slm_client._fetch_from_slm", return_value=None):
                with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
                    url = await discover_service("redis")
                    assert url == "redis://localhost:6379"

    @pytest.mark.asyncio
    async def test_discover_service_raises_when_not_configured(self):
        """Raises error when service not configured anywhere."""
        with patch("backend.services.slm_client._discovery_cache") as mock_cache:
            mock_cache.get.return_value = None
            with patch("backend.services.slm_client._fetch_from_slm", return_value=None):
                with patch.dict(os.environ, {}, clear=True):
                    with pytest.raises(ServiceNotConfiguredError):
                        await discover_service("unknown-service")


class TestEnvVarMap:
    """Test ENV_VAR_MAP constant."""

    def test_env_var_map_contains_required_services(self):
        """ENV_VAR_MAP has all required service mappings."""
        required = ["redis", "ollama", "slm-server", "autobot-backend"]
        for service in required:
            assert service in ENV_VAR_MAP, f"Missing {service} in ENV_VAR_MAP"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/AutoBot && python -m pytest backend/tests/test_slm_client.py::TestDiscoverService -v`
Expected: FAIL with "ImportError: cannot import name 'discover_service'"

**Step 3: Write minimal implementation**

Add to `backend/services/slm_client.py` after `ServiceDiscoveryCache` class:

```python
class ServiceNotConfiguredError(Exception):
    """Raised when a service is not configured in SLM or environment."""

    pass


# Service name to environment variable mapping
ENV_VAR_MAP = {
    "autobot-backend": "AUTOBOT_BACKEND_URL",
    "redis": "REDIS_URL",
    "ollama": "OLLAMA_URL",
    "slm-server": "SLM_URL",
    "npu-worker": "NPU_WORKER_URL",
    "ai-stack": "AI_STACK_URL",
    "browser-service": "BROWSER_SERVICE_URL",
}

# Module-level service discovery cache
_discovery_cache = ServiceDiscoveryCache(ttl_seconds=60)


async def _fetch_from_slm(service_name: str) -> Optional[str]:
    """
    Fetch service URL from SLM discovery API.

    Args:
        service_name: Service identifier

    Returns:
        Service URL or None on failure
    """
    client = get_slm_client()
    if not client:
        logger.debug("SLM client not initialized, cannot discover %s", service_name)
        return None

    try:
        session = await client._get_session()
        url = f"{client.slm_url}/api/discover/{service_name}"

        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("url")
            elif response.status == 404:
                logger.debug("Service %s not found in SLM", service_name)
            else:
                logger.warning(
                    "SLM discovery failed for %s: HTTP %d",
                    service_name,
                    response.status,
                )
    except Exception as e:
        logger.warning("Error discovering service %s from SLM: %s", service_name, e)

    return None


def _get_env_fallback(service_name: str) -> Optional[str]:
    """
    Get service URL from environment variable.

    Args:
        service_name: Service identifier

    Returns:
        URL from environment or None
    """
    env_var = ENV_VAR_MAP.get(service_name)
    if env_var:
        return os.environ.get(env_var)
    return None


async def discover_service(service_name: str) -> str:
    """
    Discover service URL with fallback chain.

    Fallback order:
    1. Cache (60s TTL)
    2. SLM /api/discover/{service_name}
    3. Environment variable
    4. Error (service must be configured)

    Args:
        service_name: Service identifier

    Returns:
        Service URL

    Raises:
        ServiceNotConfiguredError: When service not found anywhere
    """
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
        logger.info(
            "Service %s discovered via env var fallback: %s",
            service_name,
            ENV_VAR_MAP.get(service_name),
        )
        return env_url

    # 4. Error - not configured
    raise ServiceNotConfiguredError(
        f"Service '{service_name}' not found in SLM or environment"
    )
```

Also add `import os` to imports at top of file.

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/AutoBot && python -m pytest backend/tests/test_slm_client.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add backend/services/slm_client.py backend/tests/test_slm_client.py
git commit -m "feat(slm-client): add discover_service() with fallback chain (#760)"
```

---

## Task 3: Create Agent Seed Migration Script

**Files:**
- Create: `slm-server/migrations/seed_agents.py`

**Step 1: Write the seed script**

Create `slm-server/migrations/seed_agents.py`:

```python
#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Seed Migration Script (Issue #760 Phase 3)

Seeds the SLM agents table with DEFAULT_AGENT_CONFIGS from the backend.
Run this once to populate SLM with existing agent configurations.

Usage:
    cd slm-server
    python migrations/seed_agents.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# Default Ollama endpoint
DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"


async def seed_agents():
    """Seed agents from backend DEFAULT_AGENT_CONFIGS."""
    # Import here to avoid circular imports
    from config import settings
    from models.database import Agent
    from services.database import db_service

    # Initialize database
    await db_service.initialize()

    try:
        # Import backend agent configs
        from backend.api.agent_config import DEFAULT_AGENT_CONFIGS
    except ImportError as e:
        logger.error("Failed to import backend agent configs: %s", e)
        logger.info("Make sure you're running from the AutoBot root directory")
        return False

    async with db_service.session() as db:
        created_count = 0
        skipped_count = 0

        for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
            # Check if agent already exists
            result = await db.execute(
                select(Agent).where(Agent.agent_id == agent_id)
            )
            if result.scalar_one_or_none():
                logger.debug("Agent %s already exists, skipping", agent_id)
                skipped_count += 1
                continue

            # Determine model from config
            default_model = config.get("default_model", "mistral:7b-instruct")

            # Create agent
            agent = Agent(
                agent_id=agent_id,
                name=config["name"],
                description=config.get("description", ""),
                llm_provider=config.get("provider", "ollama"),
                llm_endpoint=DEFAULT_OLLAMA_ENDPOINT,
                llm_model=default_model,
                llm_timeout=30,
                llm_temperature=0.7,
                llm_max_tokens=None,
                is_default=(agent_id == "orchestrator"),
                is_active=config.get("enabled", True),
            )
            db.add(agent)
            created_count += 1
            logger.info("Created agent: %s (%s)", agent_id, config["name"])

        await db.commit()
        logger.info(
            "Seed complete: %d created, %d skipped", created_count, skipped_count
        )

    await db_service.close()
    return True


if __name__ == "__main__":
    success = asyncio.run(seed_agents())
    sys.exit(0 if success else 1)
```

**Step 2: Test the script runs without errors**

Run: `cd /home/kali/Desktop/AutoBot/slm-server && python migrations/seed_agents.py`
Expected: Creates 29 agents in SLM database (or skips if already exist)

**Step 3: Commit**

```bash
git add slm-server/migrations/seed_agents.py
git commit -m "feat(slm): add agent seed migration script (#760)"
```

---

## Task 4: Update backend/api/agent_config.py to Use SLM Client

**Files:**
- Modify: `backend/api/agent_config.py`

**Step 1: Add SLM client import and helper function**

Add to imports at top of `backend/api/agent_config.py`:

```python
from backend.services.slm_client import get_slm_client
```

Add helper function after imports:

```python
async def _get_agent_config_from_slm(agent_id: str) -> Optional[dict]:
    """
    Fetch agent config from SLM.

    Args:
        agent_id: Agent identifier

    Returns:
        Config dict or None if not found
    """
    client = get_slm_client()
    if not client:
        return None

    try:
        config = await client.get_agent_config(agent_id)
        if config:
            return {
                "model": config.get("llm_model"),
                "provider": config.get("llm_provider"),
                "endpoint": config.get("llm_endpoint"),
                "timeout": config.get("llm_timeout"),
                "temperature": config.get("llm_temperature"),
            }
    except Exception as e:
        logger.warning("Failed to get agent %s from SLM: %s", agent_id, e)

    return None
```

**Step 2: Update list_agents endpoint to use SLM with fallback**

Modify the inner loop in `list_agents` to try SLM first:

```python
for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
    # Try SLM first, fallback to local config
    slm_config = await _get_agent_config_from_slm(agent_id)

    if slm_config:
        current_model = slm_config.get("model", config["default_model"])
        current_provider = slm_config.get("provider", config["provider"])
        enabled = True  # SLM agents are active by default
    else:
        # Fallback to local unified_config_manager
        current_model = unified_config_manager.get_nested(
            f"agents.{agent_id}.model", config["default_model"]
        )
        current_provider = unified_config_manager.get_nested(
            f"agents.{agent_id}.provider", config["provider"]
        )
        enabled = unified_config_manager.get_nested(
            f"agents.{agent_id}.enabled", config["enabled"]
        )

    # Rest of the agent_info dict remains the same, add:
    agent_info["config_source"] = "slm" if slm_config else "local"
```

**Step 3: Run tests to verify nothing broke**

Run: `cd /home/kali/Desktop/AutoBot && python -m pytest backend/tests/ -v -k agent`
Expected: PASS

**Step 4: Commit**

```bash
git add backend/api/agent_config.py
git commit -m "feat(agent-config): use SLM client with local fallback (#760)"
```

---

## Task 5: Add discoverService() to TypeScript SSOT Config

**Files:**
- Modify: `autobot-vue/src/config/ssot-config.ts`

**Step 1: Add TypeScript interfaces and cache**

Add after line 253 (after `AutoBotConfig` interface):

```typescript
// =============================================================================
// Service Discovery Types (Issue #760 Phase 3)
// =============================================================================

/**
 * Discovered service information from SLM.
 */
export interface DiscoveredService {
  service_name: string;
  url: string;
  host: string;
  port?: number;
  protocol: string;
  healthy: boolean;
  node_id: string;
}

/**
 * Cache entry for discovered services.
 */
interface DiscoveryCacheEntry {
  data: DiscoveredService;
  expiresAt: number;
}

/** Service discovery cache */
const discoveryCache = new Map<string, DiscoveryCacheEntry>();
const DISCOVERY_CACHE_TTL_MS = 60000; // 60 seconds
```

**Step 2: Add discoverService function**

Add after the cache declarations:

```typescript
/**
 * Discover a service by name with fallback chain.
 *
 * Fallback order:
 * 1. Cache (60s TTL)
 * 2. SLM /api/discover/{serviceName}
 * 3. Environment-based getServiceUrl()
 * 4. Error
 *
 * @param serviceName - Service identifier (e.g., 'redis', 'ollama')
 * @param authToken - JWT token for SLM authentication
 * @returns Service URL
 * @throws Error if service not configured anywhere
 */
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
    const slmUrl = getConfig().slmUrl;
    const response = await fetch(`${slmUrl}/api/discover/${serviceName}`, {
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
    });

    if (response.ok) {
      const data: DiscoveredService = await response.json();
      discoveryCache.set(serviceName, {
        data,
        expiresAt: Date.now() + DISCOVERY_CACHE_TTL_MS,
      });
      return data.url;
    }

    if (response.status !== 404) {
      console.warn(`SLM discovery failed for ${serviceName}: ${response.status}`);
    }
  } catch (err) {
    console.warn(`SLM discovery error for ${serviceName}:`, err);
  }

  // 3. Env var fallback (via existing getServiceUrl)
  const envUrl = getServiceUrl(serviceName);
  if (envUrl) {
    console.info(`Service ${serviceName} discovered via env fallback`);
    return envUrl;
  }

  // 4. Error
  throw new Error(`Service '${serviceName}' not configured in SLM or environment`);
}

/**
 * Clear the service discovery cache.
 * Useful when services are known to have changed.
 */
export function clearDiscoveryCache(): void {
  discoveryCache.clear();
}
```

**Step 3: Test in browser console**

After syncing to frontend VM, test in browser console.

**Step 4: Commit**

```bash
git add autobot-vue/src/config/ssot-config.ts
git commit -m "feat(frontend): add discoverService() to SSOT config (#760)"
```

---

## Task 6: Create Vue Composable for Reactive Service Discovery

**Files:**
- Create: `autobot-vue/src/composables/useServiceDiscovery.ts`

**Step 1: Create the composable**

Create `autobot-vue/src/composables/useServiceDiscovery.ts`:

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Vue composable for reactive service discovery (Issue #760 Phase 3).
 *
 * Provides reactive access to discovered services with automatic refresh.
 *
 * Usage:
 *   const { discoverUrl, isLoading, error } = useServiceDiscovery();
 *   const redisUrl = await discoverUrl('redis');
 */

import { ref, computed } from 'vue';
import { discoverService, clearDiscoveryCache } from '@/config/ssot-config';
import { useAuthStore } from '@/stores/auth';

/**
 * Service discovery state for a single service.
 */
interface ServiceDiscoveryState {
  url: string | null;
  isLoading: boolean;
  error: string | null;
  lastFetched: number | null;
}

/**
 * Vue composable for service discovery.
 */
export function useServiceDiscovery() {
  const authStore = useAuthStore();
  const services = ref<Map<string, ServiceDiscoveryState>>(new Map());
  const isGlobalLoading = ref(false);
  const globalError = ref<string | null>(null);

  /**
   * Discover a service URL.
   */
  async function discoverUrl(
    serviceName: string,
    forceRefresh = false
  ): Promise<string> {
    // Check local state cache
    const existing = services.value.get(serviceName);
    if (
      !forceRefresh &&
      existing?.url &&
      existing.lastFetched &&
      Date.now() - existing.lastFetched < 60000
    ) {
      return existing.url;
    }

    // Update loading state
    services.value.set(serviceName, {
      url: existing?.url ?? null,
      isLoading: true,
      error: null,
      lastFetched: existing?.lastFetched ?? null,
    });

    try {
      const token = authStore.slmToken;
      if (!token) {
        throw new Error('Not authenticated to SLM');
      }

      if (forceRefresh) {
        clearDiscoveryCache();
      }

      const url = await discoverService(serviceName, token);

      services.value.set(serviceName, {
        url,
        isLoading: false,
        error: null,
        lastFetched: Date.now(),
      });

      return url;
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Discovery failed';
      services.value.set(serviceName, {
        url: existing?.url ?? null,
        isLoading: false,
        error: errorMsg,
        lastFetched: existing?.lastFetched ?? null,
      });
      throw err;
    }
  }

  /**
   * Get service state (reactive).
   */
  function getServiceState(serviceName: string): ServiceDiscoveryState | undefined {
    return services.value.get(serviceName);
  }

  /**
   * Check if any service is loading.
   */
  const isLoading = computed(() => {
    for (const state of services.value.values()) {
      if (state.isLoading) return true;
    }
    return isGlobalLoading.value;
  });

  /**
   * Clear all cached discoveries.
   */
  function clearAll(): void {
    services.value.clear();
    clearDiscoveryCache();
  }

  return {
    discoverUrl,
    getServiceState,
    isLoading,
    globalError,
    clearAll,
    services,
  };
}
```

**Step 2: Commit**

```bash
git add autobot-vue/src/composables/useServiceDiscovery.ts
git commit -m "feat(frontend): add useServiceDiscovery Vue composable (#760)"
```

---

## Task 7: Update GitHub Issue with Progress

**Files:**
- None (GitHub API)

**Step 1: Add progress comment to issue**

Run:
```bash
gh issue comment 760 --body "## Phase 3 Implementation Complete

### Completed Tasks:
- [x] Added ServiceDiscoveryCache to Python SLM client
- [x] Added discover_service() function with fallback chain
- [x] Created agent seed migration script
- [x] Updated backend/api/agent_config.py to use SLM client with local fallback
- [x] Added discoverService() to TypeScript SSOT config
- [x] Created useServiceDiscovery Vue composable

### Fallback Chain (No Hardcoded Defaults):
\`\`\`
Cache → SLM API → Environment Variables → Error
\`\`\`

### Next Steps (Phase 4):
- [ ] Migrate existing code to use discovery functions
- [ ] Add frontend UI for agent management
- [ ] Remove local config after stabilization"
```

---

## Summary

After completing all 7 tasks, Phase 3 deliverables include:

1. **Python SLM Client Extensions**:
   - `ServiceDiscoveryCache` class with 60s TTL
   - `discover_service()` async function
   - `ServiceNotConfiguredError` exception
   - `ENV_VAR_MAP` for fallback lookups

2. **Agent Migration Script**:
   - Seeds 29 agents from `DEFAULT_AGENT_CONFIGS` into SLM
   - Preserves tier-based model assignments
   - Safe to run multiple times (skips existing)

3. **Backend API Migration**:
   - `agent_config.py` now tries SLM first
   - Falls back to local `unified_config_manager`
   - Adds `config_source` field to responses

4. **TypeScript Discovery**:
   - `discoverService()` async function
   - `DiscoveredService` interface
   - Cache with 60s TTL

5. **Vue Composable**:
   - `useServiceDiscovery()` for reactive access
   - Integrates with auth store
   - Provides loading/error states
