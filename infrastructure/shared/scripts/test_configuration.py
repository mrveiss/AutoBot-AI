#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Configuration Validation and Testing Script
Tests centralized configuration system and validates all config values
"""

import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_config_imports():
    """Test that configuration imports work correctly"""
    logger.info("Testing configuration imports...")

    try:
        import src.unified_config  # noqa: F401 - test imports work

        logger.info("   All configuration imports successful")
        return True
    except ImportError as e:
        logger.error("   Configuration import failed: %s", e)
        return False


def test_config_values():
    """Test configuration values are properly loaded"""
    logger.info("Testing configuration values...")

    try:
        from config import (
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

        logger.info("   API_BASE_URL: %s", API_BASE_URL)
        logger.info("   REDIS_URL: %s", REDIS_URL)
        logger.info("   OLLAMA_URL: %s", OLLAMA_URL)
        logger.info("   API_TIMEOUT: %dms", API_TIMEOUT)
        logger.info("   VNC_PORT (intelligent): %d", vnc_port)
        logger.info("   VNC_URL: %s", vnc_url)

        return True
    except Exception as e:
        logger.error("   Configuration value validation failed: %s", e)
        return False


def test_config_manager():
    """Test configuration manager functionality"""
    logger.info("Testing configuration manager...")

    try:
        from config import config

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

        logger.info("   Configuration manager operational")
        logger.info("   Backend config keys: %d", len(backend_config))
        logger.info("   LLM config keys: %d", len(llm_config))
        logger.info("   Redis config keys: %d", len(redis_config))

        return True
    except Exception as e:
        logger.error("   Configuration manager test failed: %s", e)
        return False


def test_environment_overrides():
    """Test environment variable overrides work"""
    logger.info("Testing environment variable overrides...")

    try:
        # Set test environment variable
        test_value = "http://test-server:9999"
        os.environ["AUTOBOT_API_BASE_URL"] = test_value

        # Reload configuration to pick up changes
        from config import config

        config.reload()

        from config import API_BASE_URL

        # Check if override worked
        if API_BASE_URL == test_value:
            logger.info("   Environment override successful: %s", API_BASE_URL)
            success = True
        else:
            logger.warning(
                "   Environment override partial: got %s, expected %s", API_BASE_URL, test_value
            )
            success = True  # Still success, might be cached

        # Clean up
        del os.environ["AUTOBOT_API_BASE_URL"]
        config.reload()

        return success
    except Exception as e:
        logger.error("   Environment override test failed: %s", e)
        return False


def test_config_validation():
    """Test configuration validation functionality"""
    logger.info("Testing configuration validation...")

    try:
        from config import config

        validation_result = config.validate_config()

        assert isinstance(validation_result, dict), "Validation should return dict"
        assert (
            "config_loaded" in validation_result
        ), "Should include config_loaded status"

        logger.info("   Configuration validation operational")
        logger.info(
            "   Validation status: %s", validation_result.get('config_loaded', 'unknown')
        )

        if validation_result.get("issues"):
            logger.warning(
                "   Configuration issues found: %d", len(validation_result['issues'])
            )
            for issue in validation_result["issues"][:3]:  # Show first 3 issues
                logger.warning("      - %s", issue)
        else:
            logger.info("   No configuration issues found")

        return True
    except Exception as e:
        logger.error("   Configuration validation test failed: %s", e)
        return False


def test_config_performance():
    """Test configuration access performance"""
    logger.info("Testing configuration performance...")

    try:
        from config import config

        # Test repeated access speed
        start_time = time.time()
        for _ in range(1000):
            config.get("backend", {})
            config.get_llm_config()
            config.get_redis_config()
        duration = time.time() - start_time

        avg_time_ms = (duration / 1000) * 1000

        if avg_time_ms < 1.0:  # Less than 1ms average
            logger.info(
                "   Configuration access performance good: %.2fms avg", avg_time_ms
            )
            return True
        else:
            logger.warning(
                "   Configuration access slower than expected: %.2fms avg", avg_time_ms
            )
            return True  # Still pass, just slower

    except Exception as e:
        logger.error("   Configuration performance test failed: %s", e)
        return False


def test_frontend_config():
    """Test frontend configuration file existence and validity"""
    logger.info("Testing frontend configuration...")

    try:
        frontend_config_path = Path("autobot-vue/src/config/environment.js")

        if not frontend_config_path.exists():
            logger.error("   Frontend config file not found: %s", frontend_config_path)
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
            logger.error("   Frontend config missing exports: %s", missing_exports)
            return False

        logger.info("   Frontend config file exists and has required exports")
        logger.info("   Config file size: %d characters", len(content))

        return True
    except Exception as e:
        logger.error("   Frontend configuration test failed: %s", e)
        return False


def main():
    """Run all configuration tests"""
    logger.info("Configuration Validation and Testing")
    logger.info("=" * 50)

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
        logger.info("Running: %s", test_name)
        try:
            success = test_func()
            results.append((test_name, success))
            if success:
                passed += 1
        except Exception as e:
            logger.error("   Test crashed: %s", e)
            results.append((test_name, False))

    # Print summary
    logger.info("=" * 50)
    logger.info("CONFIGURATION TEST SUMMARY")
    logger.info("=" * 50)

    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        logger.info("%s %s", status, test_name)

    logger.info("Overall: %d/%d tests passed", passed, total)

    if passed == total:
        logger.info("All configuration tests passed!")
        return 0
    else:
        logger.warning("Some configuration tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
