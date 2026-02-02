# Config Registry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a Redis-backed Config Registry to consolidate duplicate `_get_ssot_config()` and `generate_request_id()` functions across the codebase.

**Architecture:** Lazy-loading singleton that defers Redis connection until first access, caches locally with 60s TTL, and falls back gracefully through Redis → Environment Variables → Hardcoded Defaults.

**Tech Stack:** Python 3.10+, Redis (via `src.utils.redis_client`), threading for thread-safety, pytest for testing.

**Related:** Issue #751, Design doc: `docs/plans/2026-02-02-config-registry-consolidation-design.md`

---

## Task 1: Create ConfigRegistry Core with Tests

**Files:**
- Create: `src/config/registry.py`
- Create: `tests/unit/test_config_registry.py`

### Step 1: Write failing test for basic get with default

```python
# tests/unit/test_config_registry.py
#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for ConfigRegistry."""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestConfigRegistryBasic:
    """Basic ConfigRegistry functionality tests."""

    def test_get_returns_default_when_no_value(self):
        """Test that get() returns default when key not found anywhere."""
        from src.config.registry import ConfigRegistry

        # Clear any cached state
        ConfigRegistry.clear_cache()

        # Mock Redis to return None
        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                result = ConfigRegistry.get("nonexistent.key", default="fallback")
                assert result == "fallback"
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/test_config_registry.py::TestConfigRegistryBasic::test_get_returns_default_when_no_value -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.config.registry'"

### Step 3: Write minimal registry implementation

```python
# src/config/registry.py
#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Config Registry - Centralized Configuration Access
===================================================

Redis-backed configuration registry with lazy loading and graceful fallbacks.
Eliminates duplicate _get_ssot_config() functions across the codebase.

ARCHITECTURE:
- Lazy Redis connection (only when first accessed)
- Local cache with TTL (default 60s)
- Three-tier fallback: Redis → Environment → Default

USAGE:
    from src.config.registry import ConfigRegistry

    # Get single value with fallback
    redis_host = ConfigRegistry.get("redis.host", "172.16.168.23")

    # Get section as dict
    redis_config = ConfigRegistry.get_section("redis")

Issue: #751 - Consolidate Common Utilities
"""

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Redis key prefix for all config values
REDIS_CONFIG_PREFIX = "autobot:config:"


class ConfigRegistry:
    """
    Centralized configuration registry with Redis backing.

    Thread-safe singleton that provides:
    - Lazy Redis connection (deferred until first access)
    - Local caching with configurable TTL
    - Graceful fallback chain: Redis → Env → Default
    """

    _redis_client = None
    _cache: Dict[str, Any] = {}
    _cache_timestamps: Dict[str, float] = {}
    _lock = threading.RLock()
    _ttl_seconds = 60
    _initialized = False

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Get configuration value with fallback chain.

        Args:
            key: Config key in dot notation (e.g., "redis.host")
            default: Default value if not found anywhere

        Returns:
            Configuration value from Redis, env, or default
        """
        try:
            # Check local cache first
            with cls._lock:
                if cls._is_cache_valid(key):
                    return cls._cache[key]

            # Try Redis
            value = cls._fetch_from_redis(key)
            if value is not None:
                cls._update_cache(key, value)
                return value

            # Try environment variable (AUTOBOT_REDIS_HOST format)
            env_key = f"AUTOBOT_{key.upper().replace('.', '_')}"
            env_value = os.getenv(env_key)
            if env_value is not None:
                cls._update_cache(key, env_value)
                return env_value

            # Return default (don't cache defaults)
            return default

        except Exception as e:
            logger.warning("Config lookup failed for %s: %s", key, e)
            return default

    @classmethod
    def _is_cache_valid(cls, key: str) -> bool:
        """Check if cached value exists and is not expired."""
        if key not in cls._cache:
            return False
        if key not in cls._cache_timestamps:
            return False
        age = time.time() - cls._cache_timestamps[key]
        return age < cls._ttl_seconds

    @classmethod
    def _update_cache(cls, key: str, value: Any) -> None:
        """Update cache with new value and timestamp."""
        with cls._lock:
            cls._cache[key] = value
            cls._cache_timestamps[key] = time.time()

    @classmethod
    def _fetch_from_redis(cls, key: str) -> Optional[str]:
        """Fetch value from Redis. Returns None if not found or error."""
        try:
            redis_client = cls._get_redis()
            if redis_client is None:
                return None
            redis_key = f"{REDIS_CONFIG_PREFIX}{key}"
            value = redis_client.get(redis_key)
            if value is not None:
                return value.decode("utf-8") if isinstance(value, bytes) else value
            return None
        except Exception as e:
            logger.debug("Redis fetch failed for %s: %s", key, e)
            return None

    @classmethod
    def _get_redis(cls):
        """Lazy Redis connection - only when first needed."""
        if cls._redis_client is None:
            try:
                from src.utils.redis_client import get_redis_client

                cls._redis_client = get_redis_client(database="main")
            except Exception as e:
                logger.debug("Redis connection failed: %s", e)
                return None
        return cls._redis_client

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached values. Useful for testing."""
        with cls._lock:
            cls._cache.clear()
            cls._cache_timestamps.clear()
            cls._redis_client = None
```

### Step 4: Run test to verify it passes

Run: `pytest tests/unit/test_config_registry.py::TestConfigRegistryBasic::test_get_returns_default_when_no_value -v`
Expected: PASS

### Step 5: Commit

```bash
git add src/config/registry.py tests/unit/test_config_registry.py
git commit -m "feat(config): add ConfigRegistry core with basic get (#751)"
```

---

## Task 2: Add Environment Variable Fallback Tests

**Files:**
- Modify: `tests/unit/test_config_registry.py`

### Step 1: Write failing test for env var fallback

```python
# Add to tests/unit/test_config_registry.py

    def test_get_falls_back_to_env_var(self):
        """Test that get() falls back to environment variable."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(os.environ, {"AUTOBOT_REDIS_HOST": "10.0.0.99"}, clear=True):
                result = ConfigRegistry.get("redis.host", default="172.16.168.23")
                assert result == "10.0.0.99"

    def test_env_var_key_conversion(self):
        """Test that dot notation converts to underscore for env vars."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(os.environ, {"AUTOBOT_BACKEND_API_PORT": "9000"}, clear=True):
                result = ConfigRegistry.get("backend.api.port", default="8001")
                assert result == "9000"
```

### Step 2: Run test to verify it passes

Run: `pytest tests/unit/test_config_registry.py -v -k "env"`
Expected: PASS (implementation already handles this)

### Step 3: Commit

```bash
git add tests/unit/test_config_registry.py
git commit -m "test(config): add env var fallback tests for ConfigRegistry (#751)"
```

---

## Task 3: Add Caching Tests

**Files:**
- Modify: `tests/unit/test_config_registry.py`

### Step 1: Write failing test for cache behavior

```python
# Add to tests/unit/test_config_registry.py

class TestConfigRegistryCaching:
    """ConfigRegistry caching behavior tests."""

    def test_cached_value_returned_without_redis_call(self):
        """Test that cached values don't trigger Redis fetch."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        mock_fetch = MagicMock(return_value="cached_value")
        with patch.object(ConfigRegistry, "_fetch_from_redis", mock_fetch):
            # First call should fetch from Redis
            result1 = ConfigRegistry.get("test.key")
            assert result1 == "cached_value"
            assert mock_fetch.call_count == 1

            # Second call should use cache
            result2 = ConfigRegistry.get("test.key")
            assert result2 == "cached_value"
            assert mock_fetch.call_count == 1  # Still 1, not 2

    def test_cache_expires_after_ttl(self):
        """Test that cache expires after TTL seconds."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()
        original_ttl = ConfigRegistry._ttl_seconds
        ConfigRegistry._ttl_seconds = 0.1  # 100ms for testing

        try:
            mock_fetch = MagicMock(return_value="value")
            with patch.object(ConfigRegistry, "_fetch_from_redis", mock_fetch):
                ConfigRegistry.get("expiring.key")
                assert mock_fetch.call_count == 1

                # Wait for expiration
                time.sleep(0.15)

                ConfigRegistry.get("expiring.key")
                assert mock_fetch.call_count == 2  # Cache expired, fetched again
        finally:
            ConfigRegistry._ttl_seconds = original_ttl

    def test_clear_cache_removes_all_values(self):
        """Test that clear_cache removes all cached values."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value="val"):
            ConfigRegistry.get("key1")
            ConfigRegistry.get("key2")

        assert "key1" in ConfigRegistry._cache
        assert "key2" in ConfigRegistry._cache

        ConfigRegistry.clear_cache()

        assert "key1" not in ConfigRegistry._cache
        assert "key2" not in ConfigRegistry._cache
```

### Step 2: Add time import to test file

Add `import time` to the imports at the top of the test file.

### Step 3: Run tests to verify they pass

Run: `pytest tests/unit/test_config_registry.py::TestConfigRegistryCaching -v`
Expected: PASS

### Step 4: Commit

```bash
git add tests/unit/test_config_registry.py
git commit -m "test(config): add caching behavior tests for ConfigRegistry (#751)"
```

---

## Task 4: Add get_section and set Methods

**Files:**
- Modify: `src/config/registry.py`
- Modify: `tests/unit/test_config_registry.py`

### Step 1: Write failing test for get_section

```python
# Add to tests/unit/test_config_registry.py

class TestConfigRegistrySections:
    """ConfigRegistry section operations tests."""

    def test_get_section_returns_dict(self):
        """Test that get_section returns a dictionary of matching keys."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        # Pre-populate cache with section values
        ConfigRegistry._cache = {
            "redis.host": "172.16.168.23",
            "redis.port": "6379",
            "redis.database": "0",
            "backend.port": "8001",
        }
        ConfigRegistry._cache_timestamps = {
            k: time.time() for k in ConfigRegistry._cache
        }

        result = ConfigRegistry.get_section("redis")
        assert result == {
            "host": "172.16.168.23",
            "port": "6379",
            "database": "0",
        }
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/test_config_registry.py::TestConfigRegistrySections::test_get_section_returns_dict -v`
Expected: FAIL with "AttributeError: type object 'ConfigRegistry' has no attribute 'get_section'"

### Step 3: Add get_section to registry.py

```python
# Add to src/config/registry.py ConfigRegistry class

    @classmethod
    def get_section(cls, prefix: str) -> Dict[str, Any]:
        """
        Get all config values matching a prefix as a dictionary.

        Args:
            prefix: Key prefix (e.g., "redis" returns all "redis.*" keys)

        Returns:
            Dictionary with keys stripped of prefix
        """
        result = {}
        prefix_dot = f"{prefix}."

        with cls._lock:
            for key, value in cls._cache.items():
                if key.startswith(prefix_dot):
                    short_key = key[len(prefix_dot):]
                    result[short_key] = value

        return result

    @classmethod
    def set(cls, key: str, value: Any) -> bool:
        """
        Set configuration value in Redis and local cache.

        Args:
            key: Config key in dot notation
            value: Value to store

        Returns:
            True if successfully stored in Redis, False otherwise
        """
        try:
            redis_client = cls._get_redis()
            if redis_client is not None:
                redis_key = f"{REDIS_CONFIG_PREFIX}{key}"
                redis_client.set(redis_key, str(value))

            cls._update_cache(key, value)
            return True
        except Exception as e:
            logger.warning("Config set failed for %s: %s", key, e)
            cls._update_cache(key, value)  # Still cache locally
            return False

    @classmethod
    def refresh(cls, key: str) -> Any:
        """
        Force refresh a key from Redis, bypassing cache.

        Args:
            key: Config key to refresh

        Returns:
            Fresh value from Redis or None
        """
        with cls._lock:
            if key in cls._cache:
                del cls._cache[key]
            if key in cls._cache_timestamps:
                del cls._cache_timestamps[key]

        return cls.get(key)
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/unit/test_config_registry.py::TestConfigRegistrySections -v`
Expected: PASS

### Step 5: Commit

```bash
git add src/config/registry.py tests/unit/test_config_registry.py
git commit -m "feat(config): add get_section, set, refresh to ConfigRegistry (#751)"
```

---

## Task 5: Create Registry Defaults Module

**Files:**
- Create: `src/config/registry_defaults.py`
- Modify: `src/config/registry.py`
- Modify: `tests/unit/test_config_registry.py`

### Step 1: Write failing test for defaults integration

```python
# Add to tests/unit/test_config_registry.py

class TestConfigRegistryDefaults:
    """ConfigRegistry defaults integration tests."""

    def test_get_uses_registry_defaults(self):
        """Test that get() uses registry defaults when no value found."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                # Should get default from registry_defaults
                result = ConfigRegistry.get("redis.host")
                assert result == "172.16.168.23"
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/test_config_registry.py::TestConfigRegistryDefaults -v`
Expected: FAIL (returns None instead of default)

### Step 3: Create registry_defaults.py

```python
# src/config/registry_defaults.py
#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Registry Defaults - Hardcoded Fallback Values
==============================================

Default values used when config is not found in Redis or environment.
These match the values from the distributed VM architecture.

Issue: #751 - Consolidate Common Utilities
"""

# VM IP addresses (6-VM distributed architecture)
REGISTRY_DEFAULTS = {
    # VM IPs
    "vm.main": "172.16.168.20",
    "vm.frontend": "172.16.168.21",
    "vm.npu": "172.16.168.22",
    "vm.redis": "172.16.168.23",
    "vm.aistack": "172.16.168.24",
    "vm.browser": "172.16.168.25",
    "vm.ollama": "127.0.0.1",
    # Convenience aliases
    "redis.host": "172.16.168.23",
    "redis.port": "6379",
    "backend.host": "172.16.168.20",
    "backend.port": "8001",
    "frontend.host": "172.16.168.21",
    "frontend.port": "5173",
    "npu.host": "172.16.168.22",
    "npu.port": "8081",
    "aistack.host": "172.16.168.24",
    "aistack.port": "8080",
    "browser.host": "172.16.168.25",
    "browser.port": "3000",
    # LLM defaults
    "llm.default_model": "mistral:7b-instruct",
    "llm.embedding_model": "nomic-embed-text:latest",
    # Timeouts
    "timeout.http": "30",
    "timeout.redis": "5",
    "timeout.llm": "120",
}


def get_default(key: str) -> str | None:
    """Get default value for a config key."""
    return REGISTRY_DEFAULTS.get(key)
```

### Step 4: Update registry.py to use defaults

```python
# Modify the get() method in src/config/registry.py to check defaults before returning caller's default

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Get configuration value with fallback chain.

        Fallback order: Cache → Redis → Environment → Registry Defaults → Caller Default

        Args:
            key: Config key in dot notation (e.g., "redis.host")
            default: Default value if not found anywhere

        Returns:
            Configuration value from the fallback chain
        """
        try:
            # Check local cache first
            with cls._lock:
                if cls._is_cache_valid(key):
                    return cls._cache[key]

            # Try Redis
            value = cls._fetch_from_redis(key)
            if value is not None:
                cls._update_cache(key, value)
                return value

            # Try environment variable (AUTOBOT_REDIS_HOST format)
            env_key = f"AUTOBOT_{key.upper().replace('.', '_')}"
            env_value = os.getenv(env_key)
            if env_value is not None:
                cls._update_cache(key, env_value)
                return env_value

            # Try registry defaults
            from src.config.registry_defaults import get_default

            registry_default = get_default(key)
            if registry_default is not None:
                return registry_default

            # Return caller's default
            return default

        except Exception as e:
            logger.warning("Config lookup failed for %s: %s", key, e)
            return default
```

### Step 5: Run tests to verify they pass

Run: `pytest tests/unit/test_config_registry.py::TestConfigRegistryDefaults -v`
Expected: PASS

### Step 6: Commit

```bash
git add src/config/registry.py src/config/registry_defaults.py tests/unit/test_config_registry.py
git commit -m "feat(config): add registry_defaults for hardcoded fallbacks (#751)"
```

---

## Task 6: Migrate network_constants.py

**Files:**
- Modify: `src/constants/network_constants.py`

### Step 1: Read current implementation

Run: Read `src/constants/network_constants.py` to understand current structure.

### Step 2: Replace _get_ssot_config with ConfigRegistry

Replace the `_get_ssot_config()` function and `_ssot` variable with ConfigRegistry imports.

Key changes:
- Remove `def _get_ssot_config()` function (~20 lines)
- Remove `_ssot = _get_ssot_config()` line
- Add `from src.config.registry import ConfigRegistry`
- Replace `_ssot.redis.host if _ssot else "172.16.168.23"` with `ConfigRegistry.get("redis.host", "172.16.168.23")`

### Step 3: Run existing tests to verify no regression

Run: `pytest tests/unit/test_ssot_config.py -v`
Expected: PASS

### Step 4: Commit

```bash
git add src/constants/network_constants.py
git commit -m "refactor(constants): migrate network_constants to ConfigRegistry (#751)"
```

---

## Task 7: Migrate redis_constants.py

**Files:**
- Modify: `src/constants/redis_constants.py`

### Step 1: Replace _get_ssot_config with ConfigRegistry

Same pattern as Task 6:
- Remove `def _get_ssot_config()` function
- Remove `_ssot = _get_ssot_config()` line
- Add ConfigRegistry import
- Update any usages

### Step 2: Run tests

Run: `pytest tests/ -k "redis" --ignore=tests/e2e -v`
Expected: PASS

### Step 3: Commit

```bash
git add src/constants/redis_constants.py
git commit -m "refactor(constants): migrate redis_constants to ConfigRegistry (#751)"
```

---

## Task 8: Migrate model_constants.py

**Files:**
- Modify: `src/constants/model_constants.py`

### Step 1: Replace _get_ssot_config with ConfigRegistry

Same pattern as Task 6.

### Step 2: Run tests

Run: `pytest tests/unit/ -v --ignore=tests/unit/test_config_registry.py`
Expected: PASS

### Step 3: Commit

```bash
git add src/constants/model_constants.py
git commit -m "refactor(constants): migrate model_constants to ConfigRegistry (#751)"
```

---

## Task 9: Migrate config/compat.py

**Files:**
- Modify: `src/config/compat.py`

### Step 1: Replace _get_ssot_config with ConfigRegistry

Same pattern.

### Step 2: Run tests

Run: `pytest tests/unit/test_config*.py -v`
Expected: PASS

### Step 3: Commit

```bash
git add src/config/compat.py
git commit -m "refactor(config): migrate compat.py to ConfigRegistry (#751)"
```

---

## Task 10: Migrate config/manager.py

**Files:**
- Modify: `src/config/manager.py`

### Step 1: Replace _get_ssot_config with ConfigRegistry

Same pattern.

### Step 2: Run tests

Run: `pytest tests/unit/test_config_manager.py -v`
Expected: PASS

### Step 3: Commit

```bash
git add src/config/manager.py
git commit -m "refactor(config): migrate manager.py to ConfigRegistry (#751)"
```

---

## Task 11: Migrate config/defaults.py

**Files:**
- Modify: `src/config/defaults.py`

### Step 1: Replace _get_ssot_config with ConfigRegistry

Same pattern.

### Step 2: Run tests

Run: `pytest tests/unit/ -v`
Expected: PASS

### Step 3: Commit

```bash
git add src/config/defaults.py
git commit -m "refactor(config): migrate defaults.py to ConfigRegistry (#751)"
```

---

## Task 12: Migrate generate_request_id in chat_improved.py

**Files:**
- Modify: `backend/api/chat_improved.py`

### Step 1: Replace local function with import

Remove:
```python
def generate_request_id() -> str:
    """Generate a unique request ID for tracking."""
    return str(uuid.uuid4())
```

Add:
```python
from src.utils.request_utils import generate_request_id
```

Remove `import uuid` if no longer needed.

### Step 2: Run tests

Run: `pytest tests/ -k "chat" -v --ignore=tests/e2e`
Expected: PASS

### Step 3: Commit

```bash
git add backend/api/chat_improved.py
git commit -m "refactor(api): migrate chat_improved to use request_utils (#751)"
```

---

## Task 13: Migrate generate_request_id in entity_extraction.py

**Files:**
- Modify: `backend/api/entity_extraction.py`

### Step 1: Replace local function with import

Same pattern as Task 12.

### Step 2: Run tests

Run: `pytest tests/ -k "entity" -v`
Expected: PASS

### Step 3: Commit

```bash
git add backend/api/entity_extraction.py
git commit -m "refactor(api): migrate entity_extraction to use request_utils (#751)"
```

---

## Task 14: Migrate generate_request_id in memory.py

**Files:**
- Modify: `backend/api/memory.py`

### Step 1: Replace local function with import

Same pattern as Task 12.

### Step 2: Commit

```bash
git add backend/api/memory.py
git commit -m "refactor(api): migrate memory.py to use request_utils (#751)"
```

---

## Task 15: Migrate generate_request_id in graph_rag.py

**Files:**
- Modify: `backend/api/graph_rag.py`

### Step 1: Replace local function with import

Same pattern as Task 12.

### Step 2: Commit

```bash
git add backend/api/graph_rag.py
git commit -m "refactor(api): migrate graph_rag to use request_utils (#751)"
```

---

## Task 16: Migrate generate_request_id in security_assessment.py

**Files:**
- Modify: `backend/api/security_assessment.py`

### Step 1: Replace local function with import

Same pattern as Task 12.

### Step 2: Commit

```bash
git add backend/api/security_assessment.py
git commit -m "refactor(api): migrate security_assessment to use request_utils (#751)"
```

---

## Task 17: Migrate generate_request_id in chat_utils.py

**Files:**
- Modify: `backend/utils/chat_utils.py`

### Step 1: Replace local function with import

Same pattern as Task 12.

### Step 2: Run full test suite

Run: `pytest tests/unit/ tests/integration/ -v --ignore=tests/e2e`
Expected: PASS

### Step 3: Commit

```bash
git add backend/utils/chat_utils.py
git commit -m "refactor(utils): migrate chat_utils to use request_utils (#751)"
```

---

## Task 18: Final Verification and Cleanup

**Files:**
- None (verification only)

### Step 1: Verify no _get_ssot_config duplicates remain

Run: `grep -r "def _get_ssot_config" src/`
Expected: No matches

### Step 2: Verify no local generate_request_id definitions remain (except request_utils.py)

Run: `grep -r "def generate_request_id" backend/ src/ | grep -v request_utils.py`
Expected: No matches

### Step 3: Run full test suite

Run: `pytest tests/unit/ tests/integration/ -v`
Expected: All PASS

### Step 4: Final commit (if any cleanup needed)

```bash
git add -A
git commit -m "chore: cleanup after consolidation (#751)"
```

---

## Task 19: Update Documentation

**Files:**
- Modify: `docs/developer/SSOT_CONFIG_GUIDE.md` (if exists)

### Step 1: Add ConfigRegistry usage section

Document the new pattern:
```markdown
## ConfigRegistry (New Pattern)

For simple config access without full SSOT initialization:

```python
from src.config.registry import ConfigRegistry

redis_host = ConfigRegistry.get("redis.host", "172.16.168.23")
```
```

### Step 2: Commit

```bash
git add docs/
git commit -m "docs: add ConfigRegistry usage to developer guide (#751)"
```

---

## Summary

| Task | Description | Est. Changes |
|------|-------------|--------------|
| 1-5 | ConfigRegistry implementation + tests | +350 lines |
| 6-11 | Migrate _get_ssot_config (6 files) | -180, +12 lines |
| 12-17 | Migrate generate_request_id (6 files) | -80, +12 lines |
| 18 | Verification | 0 lines |
| 19 | Documentation | +20 lines |

**Total: ~260 lines removed, ~394 added = net +134 lines but 13→2 source locations**
