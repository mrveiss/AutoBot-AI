#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSH Manager Verification Script
Quick verification of SSH Manager installation and configuration
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.constants.network_constants import NetworkConstants


def _check_imports() -> bool:
    """
    Check that all required modules can be imported.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    print("1. Checking imports...")
    try:
        from backend.services.ssh_manager import SSHManager  # noqa: F401

        print("   ✅ All modules import successfully")
        return True
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False


def _check_ssh_key() -> str:
    """
    Check SSH key exists and has correct permissions.

    Issue #281: Extracted from verify_installation to reduce function length.

    Returns:
        SSH key path if found, empty string otherwise
    """
    print("\n2. Checking SSH key...")
    ssh_key_path = os.path.expanduser("~/.ssh/autobot_key")
    if os.path.exists(ssh_key_path):
        print(f"   ✅ SSH key found: {ssh_key_path}")

        # Check permissions
        stat_info = os.stat(ssh_key_path)
        perms = oct(stat_info.st_mode)[-3:]
        if perms == "600":
            print(f"   ✅ SSH key permissions correct: {perms}")
        else:
            print(f"   ⚠️  SSH key permissions should be 600, found: {perms}")
            print(f"   Fix with: chmod 600 {ssh_key_path}")
        return ssh_key_path
    else:
        print(f"   ❌ SSH key not found: {ssh_key_path}")
        print(f'   Generate with: ssh-keygen -t rsa -b 4096 -f {ssh_key_path} -N ""')
        return ""


def _check_configuration(project_root: Path) -> Path:
    """
    Check configuration file and SSH settings.

    Issue #281: Extracted from verify_installation to reduce function length.

    Returns:
        Config path if found, None otherwise
    """
    print("\n3. Checking configuration...")
    config_path = project_root / "config" / "config.yaml"
    if config_path.exists():
        print(f"   ✅ Configuration file found: {config_path}")

        try:
            import yaml

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            if "ssh" in config:
                print("   ✅ SSH configuration section found")

                ssh_config = config["ssh"]
                print(f"   - Enabled: {ssh_config.get('enabled', False)}")
                print(f"   - Key path: {ssh_config.get('key_path', 'not set')}")

                if "hosts" in ssh_config:
                    hosts = ssh_config["hosts"]
                    print(f"   ✅ {len(hosts)} hosts configured")
                    for name, host_config in hosts.items():
                        enabled = "✓" if host_config.get("enabled", False) else "✗"
                        print(f"      {enabled} {name}: {host_config['ip']}")
                else:
                    print("   ⚠️  No hosts configured")
            else:
                print("   ❌ SSH configuration section not found")
        except Exception as e:
            print(f"   ❌ Error reading configuration: {e}")
        return config_path
    else:
        print(f"   ❌ Configuration file not found: {config_path}")
        return None


async def _test_ssh_manager_init(ssh_key_path: str, config_path: Path) -> bool:
    """
    Test SSH Manager initialization and connection pool.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    from backend.services.ssh_manager import SSHManager

    print("\n4. Testing SSH Manager initialization...")
    try:
        ssh_manager = SSHManager(
            ssh_key_path=ssh_key_path,
            config_path=str(config_path),
            enable_audit_logging=False,
        )
        print("   ✅ SSH Manager initialized successfully")

        hosts = ssh_manager.list_hosts()
        print(f"   ✅ Found {len(hosts)} hosts")

        await ssh_manager.start()
        print("   ✅ SSH Manager started successfully")

        stats = await ssh_manager.get_pool_stats()
        print(f"   ✅ Connection pool operational (pools: {len(stats)})")

        await ssh_manager.stop()
        print("   ✅ SSH Manager stopped successfully")
        return True

    except Exception as e:
        print(f"   ❌ SSH Manager initialization failed: {e}")
        return False


async def _test_command_execution(ssh_key_path: str) -> None:
    """
    Test simple command execution via SSH.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    from backend.services.ssh_manager import SSHManager

    print("\n5. Testing command execution...")
    try:
        ssh_manager = SSHManager(ssh_key_path=ssh_key_path, enable_audit_logging=False)
        await ssh_manager.start()

        result = await ssh_manager.execute_command(
            host="main", command='echo "SSH Manager Test"', timeout=10, validate=False
        )

        if result.success:
            print("   ✅ Command execution successful")
            print(f"   - Output: {result.stdout.strip()}")
            print(f"   - Execution time: {result.execution_time:.3f}s")
        else:
            print(f"   ⚠️  Command execution failed (exit code: {result.exit_code})")

        await ssh_manager.stop()

    except Exception as e:
        print(f"   ⚠️  Command execution test failed: {e}")
        print("   This is expected if SSH is not configured for localhost")


def _check_test_files(project_root: Path) -> None:
    """
    Check that test files exist.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    print("\n6. Checking test files...")
    test_files = [
        "tests/test_ssh_connection_pool.py",
        "tests/test_ssh_manager_integration.py",
    ]

    for test_file in test_files:
        test_path = project_root / test_file
        if test_path.exists():
            print(f"   ✅ {test_file}")
        else:
            print(f"   ❌ {test_file} not found")


def _check_documentation(project_root: Path) -> None:
    """
    Check that documentation files exist.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    print("\n7. Checking documentation...")
    doc_files = [
        "docs/features/SSH_CONNECTION_MANAGER.md",
        "docs/SSH_MANAGER_IMPLEMENTATION_SUMMARY.md",
    ]

    for doc_file in doc_files:
        doc_path = project_root / doc_file
        if doc_path.exists():
            print(f"   ✅ {doc_file}")
        else:
            print(f"   ❌ {doc_file} not found")


def _print_summary() -> None:
    """
    Print verification summary and next steps.

    Issue #281: Extracted from verify_installation to reduce function length.
    """
    print("\n" + "=" * 60)
    print("Verification Summary")
    print("=" * 60)
    print("✅ SSH Manager installation verified successfully!")
    print()
    print("Next steps:")
    print("1. Ensure SSH key is copied to all target hosts:")
    print(
        f"   for host in {NetworkConstants.MAIN_MACHINE_IP.rsplit('.', 1)[0]}.{{20..25}}; do"
    )
    print("       ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@$host")
    print("   done")
    print()
    print("2. Run unit tests:")
    print("   pytest tests/test_ssh_connection_pool.py -v")
    print()
    print("3. Run integration tests (requires SSH access):")
    print("   pytest tests/test_ssh_manager_integration.py -v -m integration")
    print()
    print("4. Start AutoBot backend:")
    print("   bash run_autobot.sh --dev")
    print()
    print("5. Test API endpoint:")
    print(
        f"   curl http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}/api/remote-terminal/"
    )
    print()


async def verify_installation():
    """
    Verify SSH Manager installation.

    Issue #281: Verification steps extracted to helper functions to reduce
    function length from 182 to ~30 lines.
    """
    print("=" * 60)
    print("SSH Manager Verification Script")
    print("=" * 60)
    print()

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
        print("\n\nVerification interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
