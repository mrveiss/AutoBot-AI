#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_default_configuration():
    """Test configuration with default values"""
    logger.info("Testing Default Configuration...")

    try:
        from src.config import (
            API_BASE_URL,
            BACKEND_PORT,
            HTTP_PROTOCOL,
            OLLAMA_PORT,
            REDIS_PORT,
            REDIS_PROTOCOL,
            REDIS_URL,
            WS_BASE_URL,
            WS_PROTOCOL,
        )

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


def test_custom_configuration():
    """Test configuration with custom environment variables"""
    logger.info("Testing Custom Configuration...")

    # Set custom environment variables
    test_env = {
        "AUTOBOT_HTTP_PROTOCOL": "https",
        "AUTOBOT_BACKEND_PORT": "8002",
        "AUTOBOT_OLLAMA_HOST": "192.168.1.100",
        "AUTOBOT_OLLAMA_PORT": "11435",
        "AUTOBOT_REDIS_PORT": "6380",
    }

    # Save original environment
    original_env = {}
    for key in test_env:
        original_env[key] = os.environ.get(key)
        os.environ[key] = test_env[key]

    try:
        # Reload configuration with new environment
        import importlib

        import src.config

        importlib.reload(src.config)

        from src.config import (
            API_BASE_URL,
            BACKEND_PORT,
            HTTP_PROTOCOL,
            OLLAMA_HOST_IP,
            OLLAMA_PORT,
            REDIS_PORT,
        )

        # Verify custom values are applied
        assert HTTP_PROTOCOL == "https"
        assert BACKEND_PORT == 8002
        assert OLLAMA_PORT == 11435
        assert REDIS_PORT == 6380
        assert OLLAMA_HOST_IP == "192.168.1.100"
        assert API_BASE_URL.startswith("https://")
        assert f":{BACKEND_PORT}" in API_BASE_URL

        logger.info("Custom configuration validation passed")
        return True

    except Exception as e:
        logger.error("Custom configuration validation failed: %s", e)
        return False

    finally:
        # Restore original environment
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_backend_configuration():
    """Test backend configuration service"""
    logger.info("Testing Backend Configuration Service...")

    try:
        from backend.services.config_service import ConfigService

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
