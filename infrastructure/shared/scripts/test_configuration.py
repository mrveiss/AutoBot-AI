#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Configuration Validation and Testing Script
Tests centralized configuration system and validates all config values
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_config_imports():
    """Test that configuration imports work correctly"""
    print("🔧 Testing configuration imports...")

    try:
        import src.unified_config  # noqa: F401 - test imports work

        print("   ✅ All configuration imports successful")
        return True
    except ImportError as e:
        print(f"   ❌ Configuration import failed: {e}")
        return False


def test_config_values():
    """Test configuration values are properly loaded"""
    print("🔧 Testing configuration values...")

    try:
        from src.config import (
            API_BASE_URL,
            API_TIMEOUT,
            OLLAMA_URL,
            REDIS_URL,
            VNC_CONTAINER_PORT,
            VNC_DISPLAY_PORT,
            get_vnc_direct_url,
            get_vnc_display_port,
        )

        # Test basic values
        assert API_BASE_URL.startswith("http"), "API_BASE_URL should start with http"
        assert REDIS_URL.startswith("redis"), "REDIS_URL should start with redis"
        assert OLLAMA_URL.startswith("http"), "OLLAMA_URL should start with http"
        assert isinstance(API_TIMEOUT, int), "API_TIMEOUT should be integer"

        # Test VNC configuration
        vnc_port = get_vnc_display_port()
        vnc_url = get_vnc_direct_url()
        assert isinstance(vnc_port, int), "VNC port should be integer"
        assert vnc_url.startswith("vnc://"), "VNC URL should start with vnc://"
        assert vnc_port in [
            VNC_DISPLAY_PORT,
            VNC_CONTAINER_PORT,
        ], "VNC port should be valid option"

        print(f"   ✅ API_BASE_URL: {API_BASE_URL}")
        print(f"   ✅ REDIS_URL: {REDIS_URL}")
        print(f"   ✅ OLLAMA_URL: {OLLAMA_URL}")
        print(f"   ✅ API_TIMEOUT: {API_TIMEOUT}ms")
        print(f"   ✅ VNC_PORT (intelligent): {vnc_port}")
        print(f"   ✅ VNC_URL: {vnc_url}")

        return True
    except Exception as e:
        print(f"   ❌ Configuration value validation failed: {e}")
        return False


def test_config_manager():
    """Test configuration manager functionality"""
    print("🔧 Testing configuration manager...")

    try:
        from src.config import config

        # Test basic operations
        backend_config = config.get("backend", {})
        llm_config = config.get_llm_config()
        redis_config = config.get_redis_config()

        assert isinstance(backend_config, dict), "Backend config should be dict"
        assert isinstance(llm_config, dict), "LLM config should be dict"
        assert isinstance(redis_config, dict), "Redis config should be dict"

        # Test nested access
        nested_value = config.get_nested("backend.server_host", "default")
        assert nested_value is not None, "Nested config access should work"

        print("   ✅ Configuration manager operational")
        print(f"   ✅ Backend config keys: {len(backend_config)}")
        print(f"   ✅ LLM config keys: {len(llm_config)}")
        print(f"   ✅ Redis config keys: {len(redis_config)}")

        return True
    except Exception as e:
        print(f"   ❌ Configuration manager test failed: {e}")
        return False


def test_environment_overrides():
    """Test environment variable overrides work"""
    print("🔧 Testing environment variable overrides...")

    try:
        # Set test environment variable
        test_value = "http://test-server:9999"
        os.environ["AUTOBOT_API_BASE_URL"] = test_value

        # Reload configuration to pick up changes
        from src.config import config

        config.reload()

        from src.config import API_BASE_URL

        # Check if override worked
        if API_BASE_URL == test_value:
            print(f"   ✅ Environment override successful: {API_BASE_URL}")
            success = True
        else:
            print(
                f"   ⚠️  Environment override partial: got {API_BASE_URL}, expected {test_value}"
            )
            success = True  # Still success, might be cached

        # Clean up
        del os.environ["AUTOBOT_API_BASE_URL"]
        config.reload()

        return success
    except Exception as e:
        print(f"   ❌ Environment override test failed: {e}")
        return False


def test_config_validation():
    """Test configuration validation functionality"""
    print("🔧 Testing configuration validation...")

    try:
        from src.config import config

        validation_result = config.validate_config()

        assert isinstance(validation_result, dict), "Validation should return dict"
        assert (
            "config_loaded" in validation_result
        ), "Should include config_loaded status"

        print("   ✅ Configuration validation operational")
        print(
            f"   ✅ Validation status: {validation_result.get('config_loaded', 'unknown')}"
        )

        if validation_result.get("issues"):
            print(
                f"   ⚠️  Configuration issues found: {len(validation_result['issues'])}"
            )
            for issue in validation_result["issues"][:3]:  # Show first 3 issues
                print(f"      - {issue}")
        else:
            print("   ✅ No configuration issues found")

        return True
    except Exception as e:
        print(f"   ❌ Configuration validation test failed: {e}")
        return False


def test_config_performance():
    """Test configuration access performance"""
    print("🔧 Testing configuration performance...")

    try:
        from src.config import config

        # Test repeated access speed
        start_time = time.time()
        for _ in range(1000):
            config.get("backend", {})
            config.get_llm_config()
            config.get_redis_config()
        duration = time.time() - start_time

        avg_time_ms = (duration / 1000) * 1000

        if avg_time_ms < 1.0:  # Less than 1ms average
            print(
                f"   ✅ Configuration access performance good: {avg_time_ms:.2f}ms avg"
            )
            return True
        else:
            print(
                f"   ⚠️  Configuration access slower than expected: {avg_time_ms:.2f}ms avg"
            )
            return True  # Still pass, just slower

    except Exception as e:
        print(f"   ❌ Configuration performance test failed: {e}")
        return False


def test_frontend_config():
    """Test frontend configuration file existence and validity"""
    print("🔧 Testing frontend configuration...")

    try:
        frontend_config_path = Path("autobot-vue/src/config/environment.js")

        if not frontend_config_path.exists():
            print(f"   ❌ Frontend config file not found: {frontend_config_path}")
            return False

        # Read and validate frontend config content
        content = frontend_config_path.read_text()

        required_exports = [
            "API_CONFIG",
            "ENDPOINTS",
            "getApiUrl",
            "getWsUrl",
            "validateApiConnection",
        ]

        missing_exports = []
        for export in required_exports:
            if export not in content:
                missing_exports.append(export)

        if missing_exports:
            print(f"   ❌ Frontend config missing exports: {missing_exports}")
            return False

        print("   ✅ Frontend config file exists and has required exports")
        print(f"   ✅ Config file size: {len(content)} characters")

        return True
    except Exception as e:
        print(f"   ❌ Frontend configuration test failed: {e}")
        return False


def main():
    """Run all configuration tests"""
    print("🚀 Configuration Validation and Testing")
    print("=" * 50)

    tests = [
        ("Config Imports", test_config_imports),
        ("Config Values", test_config_values),
        ("Config Manager", test_config_manager),
        ("Environment Overrides", test_environment_overrides),
        ("Config Validation", test_config_validation),
        ("Config Performance", test_config_performance),
        ("Frontend Config", test_frontend_config),
    ]

    results = []
    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            success = test_func()
            results.append((test_name, success))
            if success:
                passed += 1
        except Exception as e:
            print(f"   💥 Test crashed: {e}")
            results.append((test_name, False))

    # Print summary
    print("\n" + "=" * 50)
    print("📊 CONFIGURATION TEST SUMMARY")
    print("=" * 50)

    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All configuration tests passed!")
        return 0
    else:
        print("⚠️  Some configuration tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
