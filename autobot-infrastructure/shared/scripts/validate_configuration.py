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
    """Test configuration with default values (read from the SSOT, #18094)."""
    logger.info("Testing Default Configuration...")

    try:
        from autobot_shared.ssot_config import config as ssot_config

        # Test URLs are properly formed (Issue #380: use module-level constants)
        assert ssot_config.backend_url.startswith(_HTTP_PROTOCOLS)
        assert ssot_config.redis_url.startswith(("redis://", "rediss://"))
        assert ssot_config.websocket_url.startswith(_WS_PROTOCOLS)

        # Test ports are integers
        assert isinstance(ssot_config.port.backend, int)
        assert isinstance(ssot_config.port.ollama, int)
        assert isinstance(ssot_config.port.redis, int)

        logger.info("Default configuration validation passed")
        return True

    except Exception as e:
        logger.error("Default configuration validation failed: %s", e)
        return False


def test_custom_configuration():
    """Test that AUTOBOT_* overrides reach the SSOT after a reload."""
    logger.info("Testing Custom Configuration...")

    test_env = {
        "AUTOBOT_BACKEND_PORT": "8002",
        "AUTOBOT_OLLAMA_PORT": "11435",
        "AUTOBOT_REDIS_PORT": "6380",
    }
    original_env = {key: os.environ.get(key) for key in test_env}
    os.environ.update(test_env)

    try:
        from autobot_shared.ssot_config import config as ssot_config
        from autobot_shared.ssot_config import reload_config

        reload_config()

        assert ssot_config.port.backend == 8002
        assert ssot_config.port.ollama == 11435
        assert ssot_config.port.redis == 6380
        assert f":{ssot_config.port.backend}" in ssot_config.backend_url

        logger.info("Custom configuration validation passed")
        return True

    except Exception as e:
        logger.error("Custom configuration validation failed: %s", e)
        return False

    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from autobot_shared.ssot_config import reload_config

        reload_config()


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
