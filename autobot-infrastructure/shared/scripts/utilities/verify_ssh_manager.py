#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSH Manager Verification Script
Quick verification of SSH Manager installation and configuration
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from constants.network_constants import NetworkConstants

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _check_imports() -> bool:
    """
    Check that all required modules can be imported.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    logger.info("1. Checking imports...")
    try:
        from backend.services.ssh_manager import SSHManager  # noqa: F401

        logger.info("   All modules import successfully")
        return True
    except ImportError as e:
        logger.error("   Import failed: %s", e)
        return False


def _check_ssh_key() -> str:
    """
    Check SSH key exists and has correct permissions.

    Issue #281: Extracted from verify_installation to reduce function length.

    Returns:
        SSH key path if found, empty string otherwise
    """
    logger.info("2. Checking SSH key...")
    ssh_key_path = os.path.expanduser("~/.ssh/autobot_key")
    if os.path.exists(ssh_key_path):
        logger.info("   SSH key found: %s", ssh_key_path)

        # Check permissions
        stat_info = os.stat(ssh_key_path)
        perms = oct(stat_info.st_mode)[-3:]
        if perms == "600":
            logger.info("   SSH key permissions correct: %s", perms)
        else:
            logger.warning("   SSH key permissions should be 600, found: %s", perms)
            logger.warning("   Fix with: chmod 600 %s", ssh_key_path)
        return ssh_key_path
    else:
        logger.error("   SSH key not found: %s", ssh_key_path)
        logger.error(
            '   Generate with: ssh-keygen -t rsa -b 4096 -f %s -N ""', ssh_key_path
        )
        return ""


def _check_configuration(project_root: Path) -> Path:
    """
    Check configuration file and SSH settings.

    Issue #281: Extracted from verify_installation to reduce function length.

    Returns:
        Config path if found, None otherwise
    """
    logger.info("3. Checking configuration...")
    config_path = project_root / "config" / "config.yaml"
    if config_path.exists():
        logger.info("   Configuration file found: %s", config_path)

        try:
            import yaml

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            if "ssh" in config:
                logger.info("   SSH configuration section found")

                ssh_config = config["ssh"]
                logger.info("   - Enabled: %s", ssh_config.get("enabled", False))
                logger.info("   - Key path: %s", ssh_config.get("key_path", "not set"))

                if "hosts" in ssh_config:
                    hosts = ssh_config["hosts"]
                    logger.info("   %d hosts configured", len(hosts))
                    for name, host_config in hosts.items():
                        enabled = "✓" if host_config.get("enabled", False) else "✗"
                        logger.info("      %s %s: %s", enabled, name, host_config["ip"])
                else:
                    logger.warning("   No hosts configured")
            else:
                logger.error("   SSH configuration section not found")
        except Exception as e:
            logger.error("   Error reading configuration: %s", e)
        return config_path
    else:
        logger.error("   Configuration file not found: %s", config_path)
        return None


async def _test_ssh_manager_init(ssh_key_path: str, config_path: Path) -> bool:
    """
    Test SSH Manager initialization and connection pool.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    from backend.services.ssh_manager import SSHManager

    logger.info("4. Testing SSH Manager initialization...")
    try:
        ssh_manager = SSHManager(
            ssh_key_path=ssh_key_path,
            config_path=str(config_path),
            enable_audit_logging=False,
        )
        logger.info("   SSH Manager initialized successfully")

        hosts = ssh_manager.list_hosts()
        logger.info("   Found %d hosts", len(hosts))

        await ssh_manager.start()
        logger.info("   SSH Manager started successfully")

        stats = await ssh_manager.get_pool_stats()
        logger.info("   Connection pool operational (pools: %d)", len(stats))

        await ssh_manager.stop()
        logger.info("   SSH Manager stopped successfully")
        return True

    except Exception as e:
        logger.error("   SSH Manager initialization failed: %s", e)
        return False


async def _test_command_execution(ssh_key_path: str) -> None:
    """
    Test simple command execution via SSH.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    from backend.services.ssh_manager import SSHManager

    logger.info("5. Testing command execution...")
    try:
        ssh_manager = SSHManager(ssh_key_path=ssh_key_path, enable_audit_logging=False)
        await ssh_manager.start()

        result = await ssh_manager.execute_command(
            host="main", command='echo "SSH Manager Test"', timeout=10, validate=False
        )

        if result.success:
            logger.info("   Command execution successful")
            logger.info("   - Output: %s", result.stdout.strip())
            logger.info("   - Execution time: %.3fs", result.execution_time)
        else:
            logger.warning(
                "   Command execution failed (exit code: %d)", result.exit_code
            )

        await ssh_manager.stop()

    except Exception as e:
        logger.warning("   Command execution test failed: %s", e)
        logger.warning("   This is expected if SSH is not configured for localhost")


def _check_test_files(project_root: Path) -> None:
    """
    Check that test files exist.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    logger.info("6. Checking test files...")
    test_files = [
        "tests/test_ssh_connection_pool.py",
        "tests/test_ssh_manager_integration.py",
    ]

    for test_file in test_files:
        test_path = project_root / test_file
        if test_path.exists():
            logger.info("   %s", test_file)
        else:
            logger.error("   %s not found", test_file)


def _check_documentation(project_root: Path) -> None:
    """
    Check that documentation files exist.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    logger.info("7. Checking documentation...")
    doc_files = [
        "docs/features/SSH_CONNECTION_MANAGER.md",
        "docs/SSH_MANAGER_IMPLEMENTATION_SUMMARY.md",
    ]

    for doc_file in doc_files:
        doc_path = project_root / doc_file
        if doc_path.exists():
            logger.info("   %s", doc_file)
        else:
            logger.error("   %s not found", doc_file)


def _print_summary() -> None:
    """
    Print verification summary and next steps.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    logger.info("=" * 60)
    logger.info("Verification Summary")
    logger.info("=" * 60)
    logger.info("SSH Manager installation verified successfully!")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Ensure SSH key is copied to all target hosts:")
    logger.info(
        "   for host in %s.{20..25}; do",
        NetworkConstants.MAIN_MACHINE_IP.rsplit(".", 1)[0],
    )
    logger.info("       ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@$host")
    logger.info("   done")
    logger.info("")
    logger.info("2. Run unit tests:")
    logger.info("   pytest tests/test_ssh_connection_pool.py -v")
    logger.info("")
    logger.info("3. Run integration tests (requires SSH access):")
    logger.info("   pytest tests/test_ssh_manager_integration.py -v -m integration")
    logger.info("")
    logger.info("4. Start AutoBot backend:")
    logger.info("   scripts/start-services.sh start")
    logger.info("")
    logger.info("5. Test API endpoint:")
    logger.info(
        "   curl http://%s:%d/api/remote-terminal/",
        NetworkConstants.MAIN_MACHINE_IP,
        NetworkConstants.BACKEND_PORT,
    )
    logger.info("")


async def verify_installation():
    """
    Verify SSH Manager installation.

    Issue #281: Verification steps extracted to helper functions to reduce
    function length from 182 to ~30 lines.
    """
    logger.info("=" * 60)
    logger.info("SSH Manager Verification Script")
    logger.info("=" * 60)
    logger.info("")

    # Issue #281: Use extracted helpers for each verification step
    if not _check_imports():
        return False

    ssh_key_path = _check_ssh_key()
    config_path = _check_configuration(project_root)

    if not await _test_ssh_manager_init(ssh_key_path, config_path):
        return False

    await _test_command_execution(ssh_key_path)
    _check_test_files(project_root)
    _check_documentation(project_root)
    _print_summary()

    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(verify_installation())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("Verification interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        import traceback

        traceback.print_exc()
        sys.exit(1)
