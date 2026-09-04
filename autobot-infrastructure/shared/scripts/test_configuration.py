#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Configuration Validation and Testing Script
Tests centralized configuration system and validates all config values

#15189: ``test_config_values``, ``test_config_manager`` and
``test_config_validation`` each wrapped their assertions in
``try: ... except Exception: return False``. ``except Exception`` catches
``AssertionError``, so every assertion in those three was inert — the function
returned on both branches and reported the same verdict whichever way it went.
The wrappers are gone and the assertions now propagate.

The driver contract is unchanged, because ``main()`` below already wraps every
call in its own ``try/except`` and records a crash as a failed test. The only
difference is that a broken assertion is now one of the things it records,
instead of being converted to a quiet ``False`` at the point it fired — and the
traceback names the assertion rather than being discarded.

#15255: unwrapping the three handlers above did not just let assertions
propagate — it exposed that all three called an API the module under test had
already moved away from: ``config`` (``from config import config``) is the
SSOT ``autobot_shared.ssot_config`` singleton, not the runtime
``ConfigManager`` that ``.get``/``.get_llm_config``/``.get_redis_config``/
``.validate_config`` live on, and ``API_TIMEOUT``/``REDIS_URL``/
``VNC_DISPLAY_PORT``/``VNC_CONTAINER_PORT`` were never exported by ``config``
at all. Fixed against the current shape (``config_manager`` for the manager
methods, the SSOT singleton's own attributes for the infra values) rather
than re-exporting the retired names. ``test_environment_overrides`` and
``test_config_performance`` carried the same ``config``/``config_manager``
mix-up, hidden a different way: their own local ``try/except`` turned the
same ``AttributeError`` into ``return False``, which pytest never inspects
(only a raised exception fails a test), so they read as green under both
this driver's crash-catch and a direct ``pytest`` run. Both are fixed the
same way and no longer swallow a real config error.
"""

import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# #14518: the ``src.`` package prefix below is a pre-restructure path that no
# longer exists (src/unified_config.py was a re-export wrapper deleted by
# 441649af66 in favour of the ``config`` package, and src/ later became
# autobot-backend/). autobot-backend was also never on sys.path, so this
# script raised ModuleNotFoundError on its own import block. Add the
# directory the way the other operator entry points in this tree do (#14129).
_BACKEND_DIR = Path(__file__).resolve().parents[3] / "autobot-backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_config_imports():
    """Test that configuration imports work correctly"""
    logger.info("Testing configuration imports...")

    try:
        import config  # noqa: F401 - test imports work

        logger.info("   All configuration imports successful")
        return True
    except ImportError as e:
        logger.error("   Configuration import failed: %s", e)
        return False


def test_config_values():
    """Test configuration values are properly loaded.

    #15255: ``API_TIMEOUT``, ``REDIS_URL``, ``VNC_DISPLAY_PORT``,
    ``VNC_CONTAINER_PORT`` and ``get_vnc_display_port`` were never exported by
    ``config`` (autobot-backend/config/__init__.py) -- this raised
    ``ImportError`` before a single assertion ran. Infrastructure values
    (Redis URL, the legacy-ms API timeout) now live on the SSOT
    ``autobot_shared.ssot_config.config`` singleton, not on the ``config``
    package's compat constants. There is also only one VNC port surface left
    (``PLAYWRIGHT_VNC_PORT`` / ``get_vnc_direct_url``, an HTTP noVNC URL) --
    the old dual display/container port selection is gone, so the assertions
    below check what the current API actually provides instead of restoring
    the retired names.
    """
    logger.info("Testing configuration values...")

    from autobot_shared.ssot_config import config as ssot_config
    from config import API_BASE_URL, OLLAMA_URL, PLAYWRIGHT_VNC_PORT, get_vnc_direct_url

    # Test basic values
    assert API_BASE_URL.startswith("http"), "API_BASE_URL should start with http"
    assert ssot_config.redis_url.startswith("redis"), "redis_url should start with redis"
    assert OLLAMA_URL.startswith("http"), "OLLAMA_URL should start with http"
    assert isinstance(ssot_config.timeout.api, int), "timeout.api should be integer"

    # Test VNC configuration
    vnc_url = get_vnc_direct_url()
    assert isinstance(PLAYWRIGHT_VNC_PORT, int), "VNC port should be integer"
    assert vnc_url.startswith("http://"), "VNC URL should start with http://"
    assert f":{PLAYWRIGHT_VNC_PORT}/" in vnc_url, "VNC URL should embed the VNC port"

    logger.info("   API_BASE_URL: %s", API_BASE_URL)
    logger.info("   REDIS_URL: %s", ssot_config.redis_url)
    logger.info("   OLLAMA_URL: %s", OLLAMA_URL)
    logger.info("   API_TIMEOUT: %dms", ssot_config.timeout.api)
    logger.info("   VNC_PORT: %d", PLAYWRIGHT_VNC_PORT)
    logger.info("   VNC_URL: %s", vnc_url)

    return True


def test_config_manager():
    """Test configuration manager functionality.

    #15255: ``from config import config`` binds the SSOT
    ``autobot_shared.ssot_config`` singleton (a pydantic settings object),
    not the runtime ``ConfigManager`` -- it has no ``.get``/``.get_nested``/
    ``.get_llm_config``/``.get_redis_config``. Those methods are the
    ``ConfigManager`` singleton's job, reached via ``from config import
    config_manager`` (see e.g. ``agents/web_researcher.py``).
    """
    logger.info("Testing configuration manager...")

    from config import config_manager

    # Test basic operations
    backend_config = config_manager.get("backend", {})
    llm_config = config_manager.get_llm_config()
    redis_config = config_manager.get_redis_config()

    assert isinstance(backend_config, dict), "Backend config should be dict"
    assert isinstance(llm_config, dict), "LLM config should be dict"
    assert isinstance(redis_config, dict), "Redis config should be dict"

    # Test nested access
    nested_value = config_manager.get_nested("backend.server_host", "default")
    assert nested_value is not None, "Nested config access should work"

    logger.info("   Configuration manager operational")
    logger.info("   Backend config keys: %d", len(backend_config))
    logger.info("   LLM config keys: %d", len(llm_config))
    logger.info("   Redis config keys: %d", len(redis_config))

    return True


def test_environment_overrides():
    """Test environment variable overrides work.

    #15255-adjacent: same disease as ``test_config_manager`` (``config`` is
    the SSOT singleton, which has no ``.reload()`` -- that lives on
    ``autobot_shared.ssot_config.reload_config()``). Was invisible under
    pytest because the ``except Exception: return False`` here swallows the
    ``AttributeError`` into a return value pytest never inspects (only a
    raised exception fails a test). Env var is now restored in ``finally``
    so a failure here can't leak state into later tests.
    """
    logger.info("Testing environment variable overrides...")

    from autobot_shared.ssot_config import reload_config

    test_value = "http://test-server:9999"
    os.environ["AUTOBOT_API_BASE_URL"] = test_value
    try:
        # Reload configuration to pick up changes
        reload_config()

        from config import API_BASE_URL

        # Check if override worked
        if API_BASE_URL == test_value:
            logger.info("   Environment override successful: %s", API_BASE_URL)
        else:
            logger.warning(
                "   Environment override partial: got %s, expected %s",
                API_BASE_URL,
                test_value,
            )
        return True
    finally:
        os.environ.pop("AUTOBOT_API_BASE_URL", None)
        reload_config()


def test_config_validation():
    """Test configuration validation functionality.

    #15255: ``config.validate_config()`` fails the same way as
    ``test_config_manager`` -- ``validate_config`` is a ``ConfigManager``
    method (``config/validation.py``), not one the SSOT singleton has.
    """
    logger.info("Testing configuration validation...")

    from config import config_manager

    validation_result = config_manager.validate_config()

    assert isinstance(validation_result, dict), "Validation should return dict"
    assert "config_loaded" in validation_result, "Should include config_loaded status"

    logger.info("   Configuration validation operational")
    logger.info(
        "   Validation status: %s",
        validation_result.get("config_loaded", "unknown"),
    )

    if validation_result.get("issues"):
        logger.warning("   Configuration issues found: %d", len(validation_result["issues"]))
        for issue in validation_result["issues"][:3]:  # Show first 3 issues
            logger.warning("      - %s", issue)
    else:
        logger.info("   No configuration issues found")

    return True


def test_config_performance():
    """Test configuration access performance.

    #15255-adjacent: same ``config`` vs ``config_manager`` disease as
    ``test_config_manager``, invisible under pytest for the same
    return-value-not-inspected reason as ``test_environment_overrides``
    above. The outer ``try/except`` swallowed the real ``AttributeError``
    on every call; it is gone now that the call is correct.
    """
    logger.info("Testing configuration performance...")

    from config import config_manager

    # Test repeated access speed
    start_time = time.time()
    for _ in range(1000):
        config_manager.get("backend", {})
        config_manager.get_llm_config()
        config_manager.get_redis_config()
    duration = time.time() - start_time

    avg_time_ms = (duration / 1000) * 1000

    if avg_time_ms < 1.0:  # Less than 1ms average
        logger.info("   Configuration access performance good: %.2fms avg", avg_time_ms)
    else:
        logger.warning("   Configuration access slower than expected: %.2fms avg", avg_time_ms)

    return True


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
