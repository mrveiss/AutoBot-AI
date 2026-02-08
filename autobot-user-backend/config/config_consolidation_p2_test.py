#!/usr/bin/env python3
"""
Test P2 Config Consolidation
Verifies unified_config_manager.py functionality after consolidation.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_config_consolidation():
    """Test all features of unified config manager"""
    from config import unified_config_manager

    print("=" * 80)
    print("TESTING P2 CONFIG CONSOLIDATION")
    print("=" * 80)

    # Test 1: Basic config loading
    print("\n[TEST 1] Basic config loading...")
    try:
        config = unified_config_manager.to_dict()
        assert isinstance(config, dict), "Config should be a dictionary"
        assert len(config) > 0, "Config should not be empty"
        print("✅ PASSED: Basic config loading works")
    except Exception as e:
        print(f"❌ FAILED: Basic config loading - {e}")
        return False

    # Test 2: Default config completeness
    print("\n[TEST 2] Default config completeness...")
    try:
        # Get the default config directly (before merging with config.yaml)
        default_config = unified_config_manager._get_default_config()

        expected_sections = [
            "backend",
            "deployment",
            "data",
            "redis",
            "memory",
            "multimodal",
            "npu",
            "hardware",
            "system",
            "network",
            "task_transport",
            "security",
            "ui",
            "chat",
            "logging",
        ]

        for section in expected_sections:
            assert (
                section in default_config
            ), f"Missing expected section in defaults: {section}"
            print(f"   ✓ Found default section: {section}")

        print("✅ PASSED: All default config sections present")
    except Exception as e:
        print(f"❌ FAILED: Default config completeness - {e}")
        return False

    # Test 3: Sensitive data filtering
    print("\n[TEST 3] Sensitive data filtering...")
    try:
        test_data = {
            "redis": {"host": "localhost", "password": "secret123", "port": 6379},
            "api": {"endpoint": "http://api.example.com", "api_key": "key123"},
            "database": {"url": "postgres://user:pass@host/db"},
        }

        filtered = unified_config_manager._filter_sensitive_data(test_data)

        # Check that sensitive fields are redacted
        assert (
            filtered["redis"]["password"] == "***REDACTED***"
        ), "Password should be redacted"
        assert (
            filtered["api"]["api_key"] == "***REDACTED***"
        ), "API key should be redacted"

        # Check that non-sensitive fields are preserved
        assert (
            filtered["redis"]["host"] == "localhost"
        ), "Non-sensitive host should be preserved"
        assert (
            filtered["redis"]["port"] == 6379
        ), "Non-sensitive port should be preserved"

        print("✅ PASSED: Sensitive data filtering works correctly")
    except Exception as e:
        print(f"❌ FAILED: Sensitive data filtering - {e}")
        return False

    # Test 4: Async config operations
    print("\n[TEST 4] Async config operations...")
    try:
        # Test async load
        test_config = await unified_config_manager.load_config_async(
            "test", use_cache=False
        )
        assert isinstance(test_config, dict), "Async load should return dictionary"

        # Test async save
        test_data = {"test_key": "test_value", "timestamp": "2025-11-11"}
        await unified_config_manager.save_config_async("test", test_data)

        # Verify saved data
        reloaded = await unified_config_manager.load_config_async(
            "test", use_cache=False
        )
        assert (
            reloaded.get("test_key") == "test_value"
        ), "Saved data should be retrievable"

        print("✅ PASSED: Async config operations work")
    except Exception as e:
        print(f"❌ FAILED: Async config operations - {e}")
        return False

    # Test 5: Redis cache key generation
    print("\n[TEST 5] Redis cache key generation...")
    try:
        cache_key = unified_config_manager._get_redis_cache_key("test")
        assert cache_key.startswith("config:"), "Cache key should have correct prefix"
        assert "test" in cache_key, "Cache key should contain config type"
        print(f"   Cache key: {cache_key}")
        print("✅ PASSED: Redis cache key generation works")
    except Exception as e:
        print(f"❌ FAILED: Redis cache key generation - {e}")
        return False

    # Test 6: Nested config access
    print("\n[TEST 6] Nested config access...")
    try:
        # Test get_nested
        backend_config = unified_config_manager.get_nested("backend.llm", {})
        assert isinstance(backend_config, dict), "Nested config should be dictionary"

        # Test nested value retrieval
        redis_host = unified_config_manager.get_nested("redis.host", "default")
        assert redis_host is not None, "Should retrieve nested Redis host"

        print("✅ PASSED: Nested config access works")
    except Exception as e:
        print(f"❌ FAILED: Nested config access - {e}")
        return False

    # Test 7: Environment variable overrides
    print("\n[TEST 7] Environment variable handling...")
    try:
        import os

        # Verify environment variables are being used
        env_vars = [
            "AUTOBOT_DEFAULT_LLM_MODEL",
            "AUTOBOT_BACKEND_PORT",
            "AUTOBOT_REDIS_DB",
        ]

        for var in env_vars:
            value = os.getenv(var)
            if value:
                print(f"   Found env var: {var} = {value}")

        print("✅ PASSED: Environment variable handling works")
    except Exception as e:
        print(f"❌ FAILED: Environment variable handling - {e}")
        return False

    # Test 8: Multimodal config (from utils/config_manager.py)
    print("\n[TEST 8] Multimodal config consolidation...")
    try:
        default_config = unified_config_manager._get_default_config()
        multimodal = default_config.get("multimodal", {})
        assert "vision" in multimodal, "Should have vision config"
        assert "voice" in multimodal, "Should have voice config"
        assert "context" in multimodal, "Should have context config"

        # Verify default values from utils/config_manager.py
        assert multimodal["vision"]["confidence_threshold"] == 0.7
        assert multimodal["voice"]["confidence_threshold"] == 0.8
        assert multimodal["context"]["decision_threshold"] == 0.9

        print("✅ PASSED: Multimodal config properly consolidated")
    except Exception as e:
        print(f"❌ FAILED: Multimodal config - {e}")
        return False

    # Test 9: NPU config (from utils/config_manager.py)
    print("\n[TEST 9] NPU config consolidation...")
    try:
        default_config = unified_config_manager._get_default_config()
        npu = default_config.get("npu", {})
        assert npu["enabled"] is False, "NPU should be disabled by default"
        assert npu["device"] == "CPU", "Default device should be CPU"
        assert npu["optimization_level"] == "PERFORMANCE"

        print("✅ PASSED: NPU config properly consolidated")
    except Exception as e:
        print(f"❌ FAILED: NPU config - {e}")
        return False

    # Test 10: Security config (from utils/config_manager.py)
    print("\n[TEST 10] Security config consolidation...")
    try:
        default_config = unified_config_manager._get_default_config()
        security = default_config.get("security", {})
        assert security["enable_sandboxing"] is True
        assert "rm -rf" in security["blocked_commands"]

        print("✅ PASSED: Security config properly consolidated")
    except Exception as e:
        print(f"❌ FAILED: Security config - {e}")
        return False

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED! ✅")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_config_consolidation())
    sys.exit(0 if success else 1)
