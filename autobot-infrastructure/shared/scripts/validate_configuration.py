#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Configuration Validation Script
Validates that all environment variables are properly configured
and that the configuration system is working correctly.
"""

import logging
import os
import sys
from pathlib import Path

# Configure logging for validation script
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Issue #380: Module-level constants for URL validation (performance optimization)
_HTTP_PROTOCOLS = ("http://", "https://")
_WS_PROTOCOLS = ("ws://", "wss://")

# A backend tool (#18288, #18289): it puts the backend and the repository root (for `autobot_shared`)
# on its own path, so it runs from any directory with no PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[3]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
project_root = Path(__file__).parent.parent  # shared/, where docker/compose lives


def test_default_configuration():
    """Test configuration with default values"""
    logger.info("Testing Default Configuration...")

    try:
        # `config` no longer exports the Redis and WebSocket values (#18289): they live in the
        # shared network constants, which the backend's own config builds on.
        from autobot_shared.network_constants import NetworkConstants, ServiceURLs
        from config import API_BASE_URL, BACKEND_PORT, HTTP_PROTOCOL, OLLAMA_PORT

        REDIS_PORT = NetworkConstants.REDIS_PORT
        REDIS_URL = ServiceURLs.REDIS_VM
        REDIS_PROTOCOL = REDIS_URL.split("://", 1)[0]
        WS_BASE_URL = NetworkConstants.get_websocket_url()
        WS_PROTOCOL = WS_BASE_URL.split("://", 1)[0]

        # Test URLs are properly formed (Issue #380: use module-level constants)
        assert API_BASE_URL.startswith(_HTTP_PROTOCOLS)
        assert REDIS_URL.startswith("redis://")
        assert WS_BASE_URL.startswith(_WS_PROTOCOLS)

        # Test ports are integers
        assert isinstance(BACKEND_PORT, int)
        assert isinstance(OLLAMA_PORT, int)
        assert isinstance(REDIS_PORT, int)

        # Test protocols are valid
        assert HTTP_PROTOCOL in {"http", "https"}
        assert WS_PROTOCOL in {"ws", "wss"}
        assert REDIS_PROTOCOL == "redis"

        logger.info("Default configuration validation passed")
        return True

    except Exception as e:
        logger.error("Default configuration validation failed: %s", e)
        return False


def _reload_config():
    """Re-read the backend's configuration so a changed environment shows (#18289).

    The values are computed when ``config.compat`` is imported, so reloading the ``config`` package
    alone returns the cached ones; the registry's own cache is cleared for the same reason.
    """
    import importlib

    import config
    import config.compat
    from config.registry import ConfigRegistry

    ConfigRegistry.clear_cache()
    importlib.reload(config.compat)
    return importlib.reload(config)


def test_custom_configuration():
    """Test configuration with custom environment variables"""
    logger.info("Testing Custom Configuration...")

    # The registry reads ``AUTOBOT_<KEY with dots as underscores>`` (config/registry.py): the older
    # AUTOBOT_BACKEND_PORT / AUTOBOT_OLLAMA_HOST names are not read any more, and the HTTP protocol
    # is a fixed ``http`` rather than a setting (#18289).
    test_env = {
        "AUTOBOT_PORT_BACKEND": "8002",
        "AUTOBOT_VM_OLLAMA": "192.168.1.100",
        "AUTOBOT_PORT_OLLAMA": "11435",
        "AUTOBOT_PORT_REDIS": "6380",
    }

    # Save original environment
    original_env = {}
    for key in test_env:
        original_env[key] = os.environ.get(key)
        os.environ[key] = test_env[key]

    try:
        from autobot_shared.network_constants import NetworkConstants

        config = _reload_config()

        # Verify custom values are applied
        assert config.HTTP_PROTOCOL == "http"
        assert config.BACKEND_PORT == 8002
        assert config.OLLAMA_PORT == 11435
        assert NetworkConstants.REDIS_PORT == 6380
        assert config.OLLAMA_HOST_IP == "192.168.1.100"
        assert config.API_BASE_URL.startswith("http://")
        assert f":{config.BACKEND_PORT}" in config.API_BASE_URL

        logger.info("Custom configuration validation passed")
        return True

    except Exception as e:
        logger.error("Custom configuration validation failed: %s", e)
        return False

    finally:
        # Restore original environment, and the configuration read from it
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        _reload_config()


def test_backend_configuration():
    """Test backend configuration service"""
    logger.info("Testing Backend Configuration Service...")

    try:
        from services.config_service import ConfigService

        config = ConfigService.get_full_config()

        # Verify required sections exist
        assert "backend" in config
        assert "memory" in config

        # Verify backend configuration
        backend_config = config["backend"]
        assert "api_endpoint" in backend_config
        assert "server_port" in backend_config

        # Verify memory/redis configuration
        memory_config = config["memory"]
        assert "redis" in memory_config

        logger.info("Backend configuration service validation passed")
        return True

    except Exception as e:
        logger.error("Backend configuration service validation failed: %s", e)
        return False


def test_docker_configuration():
    """Test Docker compose configuration"""
    logger.info("Testing Docker Configuration...")

    try:
        import subprocess

        # Test that environment variables are properly substituted
        test_env = {"AUTOBOT_BACKEND_PORT": "8002", "AUTOBOT_REDIS_PORT": "6380"}

        compose_file = project_root / "docker" / "compose" / "docker-compose.hybrid.yml"

        if compose_file.exists():
            # Test docker-compose config command
            result = subprocess.run(
                ["docker-compose", "-", str(compose_file), "config"],
                env={**os.environ, **test_env},
                capture_output=True,
                text=True,
                cwd=compose_file.parent,
            )

            if result.returncode == 0:
                # Check that custom ports are in the output
                config_output = result.stdout
                if '"6380"' in config_output:  # Custom Redis port
                    logger.info("Docker configuration validation passed")
                    return True
                else:
                    logger.warning("Docker configuration: Custom ports not detected")
                    return False
            else:
                logger.warning("Docker compose config failed: %s", result.stderr)
                return False
        else:
            logger.warning("Docker compose file not found, skipping Docker test")
            return True

    except Exception as e:
        logger.error("Docker configuration validation failed: %s", e)
        return False


def main():
    """Main validation function"""
    logger.info("AutoBot Configuration Validation")
    logger.info("=" * 50)

    tests = [
        test_default_configuration,
        test_custom_configuration,
        test_backend_configuration,
        test_docker_configuration,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1
        logger.info("")

    logger.info("=" * 50)
    logger.info("Results: %d/%d tests passed", passed, total)

    if passed == total:
        logger.info("All configuration tests passed! System is ready.")
        return 0
    else:
        logger.warning("Some configuration tests failed. Please review.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
