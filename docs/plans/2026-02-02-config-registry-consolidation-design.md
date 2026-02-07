# Config Registry Consolidation Design

> **Issue:** [#751 - Consolidate Common Utilities](https://github.com/mrveiss/AutoBot-AI/issues/751)
> **Date:** 2026-02-02
> **Status:** Approved

## Overview

Consolidate duplicate utility functions (`_get_ssot_config()` and `generate_request_id()`) using a Redis-backed Config Registry pattern optimized for AutoBot's distributed architecture.

## Problem Statement

From duplicate functions report:
- 6 identical `_get_ssot_config()` definitions across config/constants files
- 7 identical `generate_request_id()` definitions across backend API files
- ~260 lines of duplicated code
- Inconsistent config access patterns across VMs

## Solution: Redis-Backed Config Registry

### Core Architecture

A **lazy-loading singleton** that:
1. Defers Redis connection until first config access (solves circular imports)
2. Caches locally with TTL for performance
3. Falls back gracefully: Redis → Environment Variables → Hardcoded Defaults
4. Supports namespaced keys like `redis.host`, `backend.port`

### Interface

```python
# Reading config
ConfigRegistry.get("redis.host")                    # Single value
ConfigRegistry.get_section("redis")                 # Full section as dict
ConfigRegistry.get("redis.port", default=6379)      # With fallback

# Writing config (admin/startup only)
ConfigRegistry.set("redis.host", "172.16.168.23")
ConfigRegistry.set_section("redis", {"host": "...", "port": 6379})

# Cache management
ConfigRegistry.refresh("redis.host")                # Force re-fetch
ConfigRegistry.clear_cache()                        # Clear all cached
```

### Redis Storage Structure

```
autobot:config:redis.host     → "172.16.168.23"
autobot:config:redis.port     → "6379"
autobot:config:backend.port   → "8001"
autobot:config:*              → (namespace prefix for all config)
```

### Caching Strategy

| Scenario | Behavior |
|----------|----------|
| First access | Fetch from Redis → cache locally |
| Subsequent access | Return from local cache |
| Cache TTL expired (60s) | Re-fetch from Redis on next access |
| Redis unavailable | Use cached value if exists, else env/default |
| Explicit refresh | Bypass cache, fetch fresh |

### Three-Tier Fallback Chain

```
Redis (autobot:config:*)
    ↓ (if unavailable/missing)
Environment Variable (AUTOBOT_REDIS_HOST)
    ↓ (if not set)
Hardcoded Default (172.16.168.23)
```

### Key Naming Convention

| Config Key | Env Variable | Default |
|------------|--------------|---------|
| `redis.host` | `AUTOBOT_REDIS_HOST` | `172.16.168.23` |
| `redis.port` | `AUTOBOT_REDIS_PORT` | `6379` |
| `backend.port` | `AUTOBOT_BACKEND_PORT` | `8001` |

### Thread Safety

- `threading.RLock` for cache operations
- Single Redis connection pool shared across threads
- Async support via optional `aioredis` for async contexts

### Error Handling

Registry never raises exceptions - distributed systems must be resilient:

```python
@classmethod
def get(cls, key: str, default=None):
    try:
        # Try cache → Redis → env → default
        ...
    except Exception as e:
        logger.warning(f"Config lookup failed for {key}: {e}")
        return default  # Never raise, always return usable value
```

## Migration Plan

### Files to Create

| File | Purpose | Est. Lines |
|------|---------|------------|
| `src/config/registry.py` | Core ConfigRegistry class | ~150 |
| `src/config/registry_defaults.py` | Default values mapping | ~50 |

### Files to Modify - Remove `_get_ssot_config()`

| File | Change |
|------|--------|
| `src/constants/network_constants.py` | Replace with `ConfigRegistry.get()` |
| `src/constants/redis_constants.py` | Replace with `ConfigRegistry.get()` |
| `src/constants/model_constants.py` | Replace with `ConfigRegistry.get()` |
| `src/config/compat.py` | Replace with `ConfigRegistry.get()` |
| `src/config/manager.py` | Replace with `ConfigRegistry.get()` |
| `src/config/defaults.py` | Replace with `ConfigRegistry.get()` |

### Files to Modify - Remove `generate_request_id()`

| File | Change |
|------|--------|
| `autobot-user-backend/api/chat_improved.py` | Import from `src.utils.request_utils` |
| `autobot-user-backend/api/entity_extraction.py` | Import from `src.utils.request_utils` |
| `autobot-user-backend/api/memory.py` | Import from `src.utils.request_utils` |
| `autobot-user-backend/api/graph_rag.py` | Import from `src.utils.request_utils` |
| `autobot-user-backend/api/security_assessment.py` | Import from `src.utils.request_utils` |
| `backend/utils/chat_utils.py` | Import from `src.utils.request_utils` |

### Implementation Order

1. Create `registry.py` with full test coverage
2. Create `registry_defaults.py` with all default values
3. Migrate constants files (one at a time, test after each)
4. Migrate API files for `generate_request_id()`
5. Remove dead code (`_get_ssot_config` functions)
6. Update documentation

## Code Impact

| Change | Lines Removed | Lines Added |
|--------|---------------|-------------|
| Registry implementation | 0 | ~200 |
| Remove `_get_ssot_config` | ~180 | ~12 (imports) |
| Remove `generate_request_id` | ~80 | ~12 (imports) |
| **Net change** | **~260 removed** | **~224 added** |

**Primary benefit:** Maintainability - 1 place to update vs 13 scattered definitions.

## Benefits for Distributed Architecture

1. **Single source of truth across all VMs** - All 6 services read from same Redis config
2. **Runtime reconfiguration** - Update config in Redis without service restarts
3. **Uses existing infrastructure** - Leverages Redis at 172.16.168.23
4. **Deferred resolution** - Solves circular import problem elegantly
5. **Extensible** - Pattern extends naturally to service discovery

## Success Criteria

- [ ] Single source of truth for `generate_request_id` (imports from `request_utils.py`)
- [ ] Single source of truth for config access (via `ConfigRegistry`)
- [ ] No `_get_ssot_config()` function definitions remain
- [ ] All tests passing
- [ ] Config accessible across all VMs consistently

---

*Design approved: 2026-02-02*
