#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Context Detection for AutoBot
Collects OS, machine, and architecture information for knowledge base tagging
"""

import platform
import socket
from pathlib import Path
from typing import Dict, List, Optional

from src.constants.network_constants import NetworkConstants
from src.utils.logging_manager import get_logger

# Get centralized logger
logger = get_logger(__name__, "backend")


def _parse_os_release_field(field_prefix: str) -> Optional[str]:
    """Parse a field from /etc/os-release. (Issue #315 - extracted)"""
    os_release_path = Path("/etc/os-release")
    if not os_release_path.exists():
        return None
    with open(os_release_path, "r") as f:
        for line in f:
            if line.startswith(field_prefix):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                return value
    return None


def get_system_context(machine_id: Optional[str] = None) -> Dict[str, any]:
    """
    Collect comprehensive system information for man page tagging and context awareness

    Args:
        machine_id: Override machine identifier (default: auto-detect from hostname)

    Returns:
        Dictionary with system context information
    """
    context = {
        "machine_id": machine_id or get_machine_id(),
        "machine_ip": get_local_ip(),
        "os_name": get_os_name(),
        "os_version": get_os_version(),
        "os_type": platform.system(),  # Linux, Windows, Darwin
        "architecture": platform.machine(),  # x86_64, aarch64, etc.
        "kernel_version": platform.release(),
    }

    logger.debug("System context: %s", context)
    return context


def get_machine_id() -> str:
    """
    Get machine identifier from hostname or environment

    Returns:
        Machine identifier (e.g., 'main', 'vm1', etc.)
    """
    try:
        hostname = socket.gethostname().lower()

        # Map common hostnames to machine IDs
        hostname_map = {
            "kali": "main",
            "autobot-frontend": "vm1",
            "autobot-npu": "vm2",
            "autobot-redis": "vm3",
            "autobot-ai": "vm4",
            "autobot-browser": "vm5",
        }

        # Check for exact matches or partial matches
        for host_pattern, machine_id in hostname_map.items():
            if host_pattern in hostname:
                return machine_id

        # Default: use hostname
        return hostname.split(".")[0]

    except Exception as e:
        logger.warning("Failed to get machine ID: %s", e)
        return "unknown"


def get_local_ip() -> str:
    """
    Get primary local IP address

    Returns:
        IP address string or 'unknown'
    """
    try:
        # Get local IP without external network dependency
        # First try getting hostname and resolving it
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)

        # If we got loopback, try more robust method
        if ip.startswith("127."):
            # Try getting IP from network interfaces
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # Connect to dummy address to let OS choose route (doesn't actually send data)
                s.connect((NetworkConstants.DUMMY_ROUTE_IP, 1))
                ip = s.getsockname()[0]
            finally:
                s.close()

        return ip
    except Exception as e:
        logger.warning("Failed to get local IP: %s", e)
        return "unknown"


def get_os_name() -> str:
    """
    Get specific OS distribution name (e.g., 'Kali', 'Ubuntu', 'Fedora')

    Returns:
        OS distribution name or system name
    """
    try:
        # Try reading /etc/os-release using helper (Issue #315)
        name = _parse_os_release_field("NAME=")
        if name:
            # Clean up common suffixes
            return name.replace(" GNU/Linux", "").replace(" Linux", "")
        # Fallback to platform system
        return platform.system()
    except Exception as e:
        logger.warning("Failed to get OS name: %s", e)
        return platform.system()


def get_os_version() -> str:
    """
    Get OS version number

    Returns:
        OS version string
    """
    try:
        # Try reading /etc/os-release using helper (Issue #315)
        version = _parse_os_release_field("VERSION_ID=")
        if version:
            return version
        # Fallback to platform release
        return platform.release()
    except Exception as e:
        logger.warning("Failed to get OS version: %s", e)
        return platform.release()


def get_compatible_os_list(os_name: str) -> List[str]:
    """
    Get list of OSes that are likely compatible with this OS

    Args:
        os_name: The OS name to find compatible OSes for

    Returns:
        List of compatible OS names
    """
    # OS family compatibility mappings
    os_families = {
        "Kali": ["Kali", "Debian", "Ubuntu"],
        "Ubuntu": ["Ubuntu", "Debian"],
        "Debian": ["Debian"],
        "Fedora": ["Fedora", "Red Hat", "CentOS", "Rocky"],
        "Red Hat": ["Red Hat", "CentOS", "Fedora", "Rocky"],
        "CentOS": ["CentOS", "Red Hat", "Fedora", "Rocky"],
        "Rocky": ["Rocky", "CentOS", "Red Hat", "Fedora"],
        "Arch": ["Arch", "Manjaro"],
        "Manjaro": ["Manjaro", "Arch"],
        "openSUSE": ["openSUSE", "SUSE"],
        "SUSE": ["SUSE", "openSUSE"],
        "Alpine": ["Alpine"],
        "Gentoo": ["Gentoo"],
    }

    # Return compatible list or just the OS itself
    return os_families.get(os_name, [os_name])


def generate_unique_key(
    machine_id: str, os_name: str, command: str, section: str
) -> str:
    """
    Generate unique key for man page deduplication

    Format: {machine_id}:{os_name}:{command}:{section}

    Args:
        machine_id: Machine identifier
        os_name: OS distribution name
        command: Command name
        section: Man page section

    Returns:
        Unique key string
    """
    # Normalize components to lowercase for consistency
    return f"{machine_id.lower()}:{os_name.lower()}:{command.lower()}:{section}"


# Test function for manual verification
def test_system_context():
    """Test system context detection"""
    logger.debug("=" * 80)
    logger.debug("System Context Detection Test")
    logger.debug("=" * 80)

    context = get_system_context()

    logger.debug("\nMachine ID: %s", context['machine_id'])
    logger.debug("Machine IP: %s", context['machine_ip'])
    logger.debug("OS Name: %s", context['os_name'])
    logger.debug("OS Version: %s", context['os_version'])
    logger.debug("OS Type: %s", context['os_type'])
    logger.debug("Architecture: %s", context['architecture'])
    logger.debug("Kernel Version: %s", context['kernel_version'])

    logger.debug(f"\nCompatible OSes: {get_compatible_os_list(context['os_name'])}")

    # Test unique key generation
    test_key = generate_unique_key(context["machine_id"], context["os_name"], "ls", "1")
    logger.debug(f"\nSample unique key (ls): {test_key}")

    logger.debug("=" * 80)


if __name__ == "__main__":
    # Logging configured via centralized logging_manager
    test_system_context()
