# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OS Detection and Capability Assessment Module

This module provides cross-platform OS detection and capability assessment
for the intelligent agent system.
"""

import asyncio
import logging
import os
import platform
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Optional, Set, Tuple

import aiofiles

logger = logging.getLogger(__name__)

# Issue #380: Module-level cached tool category sets to avoid repeated set creation
_NETWORK_TOOLS: FrozenSet[str] = frozenset(
    {
        "ping",
        "curl",
        "wget",
        "netstat",
        "ss",
        "nmap",
        "arp",
        "dig",
        "nslookup",
        "traceroute",
        "ifconfig",
        "ip",
    }
)

_SYSTEM_TOOLS: FrozenSet[str] = frozenset(
    {
        "ps",
        "top",
        "htop",
        "d",
        "du",
        "free",
        "uname",
        "whoami",
        "id",
        "groups",
        "sudo",
        "su",
        "crontab",
        "systemctl",
        "service",
    }
)

_FILE_TOOLS: FrozenSet[str] = frozenset(
    {
        "ls",
        "find",
        "grep",
        "sed",
        "awk",
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "wc",
        "sort",
        "uniq",
        "tar",
        "zip",
        "unzip",
    }
)

_DEV_TOOLS: FrozenSet[str] = frozenset(
    {
        "git",
        "python",
        "python3",
        "pip",
        "pip3",
        "node",
        "npm",
        "docker",
        "docker-compose",
        "vim",
        "nano",
        "emacs",
    }
)

# Issue #380: Root-required package managers frozenset
_ROOT_REQUIRED_MANAGERS: FrozenSet[str] = frozenset(
    {"apt", "yum", "dnf", "pacman", "zypper"}
)

# Issue #380: Package manager command templates (static parts cached)
_PM_INSTALL_TEMPLATES: Dict[str, str] = {
    "apt": "sudo apt update && sudo apt install -y {}",
    "dnf": "sudo dnf install -y {}",
    "yum": "sudo yum install -y {}",
    "pacman": "sudo pacman -S --noconfirm {}",
    "zypper": "sudo zypper install -y {}",
    "brew": "brew install {}",
    "winget": "winget install {}",
    "choco": "choco install {}",
}


class OSType(Enum):
    """Supported operating system types."""

    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    UNKNOWN = "unknown"


class LinuxDistro(Enum):
    """Common Linux distributions."""

    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    FEDORA = "fedora"
    CENTOS = "centos"
    RHEL = "rhel"
    ARCH = "arch"
    OPENSUSE = "opensuse"
    KALI = "kali"
    UNKNOWN = "unknown"


@dataclass
class OSInfo:
    """System information container."""

    os_type: OSType
    distro: Optional[LinuxDistro] = None
    version: str = ""
    architecture: str = ""
    user: str = ""
    is_root: bool = False
    is_wsl: bool = False
    package_manager: str = ""
    shell: str = ""
    capabilities: Set[str] = None

    def __post_init__(self):
        """Initialize capabilities set if None."""
        if self.capabilities is None:
            self.capabilities = set()


class OSDetector:
    """Cross-platform OS detection and capability assessment."""

    def __init__(self):
        """Initialize the OS detector."""
        self._os_info: Optional[OSInfo] = None
        self._capabilities_cache: Optional[Dict[str, bool]] = None

    def _get_basic_system_details(self) -> Tuple[str, str, str, bool, str]:
        """
        Get basic system details from platform and environment.

        Returns:
            Tuple of (version, architecture, user, is_root, shell).
        Issue #620.
        """
        version = platform.release()
        architecture = platform.machine()
        user = os.getenv("USER", os.getenv("USERNAME", "unknown"))
        is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
        shell = os.getenv("SHELL", "unknown")
        return version, architecture, user, is_root, shell

    def _log_detection_results(
        self,
        os_type: OSType,
        distro: Optional[LinuxDistro],
        user: str,
        is_root: bool,
        capabilities: Set[str],
    ) -> None:
        """
        Log system detection results.

        Issue #620.
        """
        logger.info(
            "System detected: %s (%s)",
            os_type.value,
            distro.value if distro else "N/A",
        )
        logger.info("User: %s (root: %s)", user, is_root)
        logger.info("Capabilities: %d tools detected", len(capabilities))

    async def detect_system(self) -> OSInfo:
        """
        Detect system information and capabilities.

        Returns:
            OSInfo: Complete system information
        Issue #620.
        """
        if self._os_info is not None:
            return self._os_info

        logger.info("Detecting system information...")

        os_type = self._detect_os_type()
        distro = await self._detect_linux_distro() if os_type == OSType.LINUX else None
        version, architecture, user, is_root, shell = self._get_basic_system_details()
        is_wsl = await self._detect_wsl()
        package_manager = await self._detect_package_manager(os_type, distro)
        capabilities = await self._detect_capabilities()

        self._os_info = OSInfo(
            os_type=os_type,
            distro=distro,
            version=version,
            architecture=architecture,
            user=user,
            is_root=is_root,
            is_wsl=is_wsl,
            package_manager=package_manager,
            shell=shell,  # nosec B604 - dataclass field assignment
            capabilities=capabilities,
        )

        self._log_detection_results(os_type, distro, user, is_root, capabilities)
        return self._os_info

    def _detect_os_type(self) -> OSType:
        """Detect the operating system type."""
        system = platform.system().lower()

        if system == "linux":
            return OSType.LINUX
        elif system == "windows":
            return OSType.WINDOWS
        elif system == "darwin":
            return OSType.MACOS
        else:
            return OSType.UNKNOWN

    # Issue #315 - Distro detection mapping for os-release file
    _DISTRO_KEYWORDS = [
        ("kali", LinuxDistro.KALI),
        ("ubuntu", LinuxDistro.UBUNTU),
        ("debian", LinuxDistro.DEBIAN),
        ("fedora", LinuxDistro.FEDORA),
        ("centos", LinuxDistro.CENTOS),
        ("rhel", LinuxDistro.RHEL),
        ("red hat", LinuxDistro.RHEL),
        ("arch", LinuxDistro.ARCH),
        ("opensuse", LinuxDistro.OPENSUSE),
        ("suse", LinuxDistro.OPENSUSE),
    ]

    # Issue #315 - Fallback file detection mapping
    _FALLBACK_FILES = {
        "/etc/debian_version": LinuxDistro.DEBIAN,
        "/etc/fedora-release": LinuxDistro.FEDORA,
        "/etc/centos-release": LinuxDistro.CENTOS,
        "/etc/arch-release": LinuxDistro.ARCH,
    }

    def _match_distro_keyword(self, content: str) -> Optional[LinuxDistro]:
        """Match distro from content keywords (Issue #315 - extracted helper)."""
        for keyword, distro in self._DISTRO_KEYWORDS:
            if keyword in content:
                return distro
        return None

    async def _detect_from_os_release(self) -> Optional[LinuxDistro]:
        """Detect distro from /etc/os-release (Issue #315 - extracted helper)."""
        os_release_exists = await asyncio.to_thread(os.path.exists, "/etc/os-release")
        if not os_release_exists:
            return None

        async with aiofiles.open("/etc/os-release", "r", encoding="utf-8") as f:
            content = (await f.read()).lower()
            return self._match_distro_keyword(content)

    async def _detect_from_fallback_files(self) -> Optional[LinuxDistro]:
        """Detect distro from fallback files (Issue #315 - extracted helper)."""
        for file_path, distro in self._FALLBACK_FILES.items():
            file_exists = await asyncio.to_thread(os.path.exists, file_path)
            if file_exists:
                return distro
        return None

    async def _detect_linux_distro(self) -> LinuxDistro:
        """Detect Linux distribution (Issue #315 - refactored)."""
        try:
            distro = await self._detect_from_os_release()
            if distro:
                return distro

            distro = await self._detect_from_fallback_files()
            if distro:
                return distro
        except Exception as e:
            logger.warning("Error detecting Linux distribution: %s", e)

        return LinuxDistro.UNKNOWN

    async def _detect_wsl(self) -> bool:
        """Detect if running in Windows Subsystem for Linux."""
        try:
            proc_version_exists = await asyncio.to_thread(
                os.path.exists, "/proc/version"
            )
            if proc_version_exists:
                async with aiofiles.open("/proc/version", "r", encoding="utf-8") as f:
                    content = (await f.read()).lower()
                    return "microsoft" in content or "wsl" in content
        except OSError as e:
            logger.debug("Failed to read /proc/version: %s", e)
        except Exception:  # nosec B110 - WSL detection fallback
            pass

        return False

    # Issue #315 - Package manager mappings
    _LINUX_DISTRO_PM = {
        LinuxDistro.UBUNTU: "apt",
        LinuxDistro.DEBIAN: "apt",
        LinuxDistro.KALI: "apt",
        LinuxDistro.FEDORA: "dnf",
        LinuxDistro.CENTOS: "yum",
        LinuxDistro.RHEL: "yum",
        LinuxDistro.ARCH: "pacman",
        LinuxDistro.OPENSUSE: "zypper",
    }
    _MACOS_PM = ["brew", "port"]
    _WINDOWS_PM = ["winget", "choco"]
    _LINUX_PM_FALLBACK = ["apt", "dnf", "yum", "pacman", "zypper"]

    def _find_available_pm(self, pm_list: list[str]) -> Optional[str]:
        """Find first available package manager (Issue #315 - extracted helper)."""
        for pm in pm_list:
            if shutil.which(pm):
                return pm
        return None

    async def _detect_package_manager(
        self, os_type: OSType, distro: Optional[LinuxDistro]
    ) -> str:
        """Detect the system package manager (Issue #315 - refactored)."""
        if os_type == OSType.LINUX:
            if distro and distro in self._LINUX_DISTRO_PM:
                return self._LINUX_DISTRO_PM[distro]
            return self._find_available_pm(self._LINUX_PM_FALLBACK) or "unknown"

        if os_type == OSType.MACOS:
            return self._find_available_pm(self._MACOS_PM) or "unknown"

        if os_type == OSType.WINDOWS:
            return self._find_available_pm(self._WINDOWS_PM) or "unknown"

        return "unknown"

    async def _detect_capabilities(self) -> Set[str]:
        """Detect available system capabilities and tools.

        Issue #281: Refactored to use module-level frozensets.
        Reduced from 88 to ~15 lines (83% reduction).
        """
        if self._capabilities_cache is not None:
            return set(self._capabilities_cache.keys())

        capabilities = set()

        # Issue #281: Use module-level frozensets instead of recreating lists
        all_tools = _NETWORK_TOOLS | _SYSTEM_TOOLS | _FILE_TOOLS | _DEV_TOOLS

        # Test each tool
        for tool in all_tools:
            if shutil.which(tool):
                capabilities.add(tool)

        # Cache the results
        self._capabilities_cache = {tool: True for tool in capabilities}

        return capabilities

    async def validate_installation_capability(self) -> Tuple[bool, str]:
        """
        Validate if the system can install new tools.

        Returns:
            Tuple[bool, str]: Can install flag and reason
        """
        if not self._os_info:
            await self.detect_system()

        if self._os_info.package_manager == "unknown":
            return False, "No supported package manager found"

        # Check if package manager is available
        if not shutil.which(self._os_info.package_manager):
            return False, f"Package manager {self._os_info.package_manager} not found"

        # Check permissions for common package managers that need root
        # Issue #380: Use module-level frozenset
        if (
            self._os_info.package_manager in _ROOT_REQUIRED_MANAGERS
            and not self._os_info.is_root
            and not shutil.which("sudo")
        ):
            return (
                False,
                f"Package manager {self._os_info.package_manager} "
                "requires root access",
            )

        return True, f"Can install using {self._os_info.package_manager}"

    async def get_capabilities_info(self) -> Dict[str, any]:
        """
        Get comprehensive capabilities information.

        Returns:
            Dict[str, any]: Capabilities summary
        """
        if not self._os_info:
            await self.detect_system()

        capabilities = self._os_info.capabilities

        # Issue #380: Use module-level cached sets instead of recreating each call
        network_tools = [tool for tool in capabilities if tool in _NETWORK_TOOLS]
        system_tools = [tool for tool in capabilities if tool in _SYSTEM_TOOLS]
        file_tools = [tool for tool in capabilities if tool in _FILE_TOOLS]
        dev_tools = [tool for tool in capabilities if tool in _DEV_TOOLS]

        return {
            "total_count": len(capabilities),
            "network_tools": len(network_tools),
            "system_tools": len(system_tools),
            "file_tools": len(file_tools),
            "development_tools": len(dev_tools),
            "by_category": {
                "network": network_tools,
                "system": system_tools,
                "files": file_tools,
                "development": dev_tools,
            },
        }

    def has_capability(self, tool: str) -> bool:
        """
        Check if a specific tool is available.

        Args:
            tool: Tool name to check

        Returns:
            bool: True if tool is available
        """
        if self._os_info and tool in self._os_info.capabilities:
            return True

        # Fallback to real-time check
        return shutil.which(tool) is not None

    async def refresh_capabilities(self):
        """Refresh the capabilities cache."""
        self._capabilities_cache = None
        if self._os_info:
            self._os_info.capabilities = await self._detect_capabilities()

    async def get_install_command(self, tool_name: str) -> Optional[str]:
        """
        Get the installation command for a specific tool.

        Args:
            tool_name: Name of the tool to install

        Returns:
            Optional[str]: Installation command or None if not available
        """
        if not self._os_info:
            await self.detect_system()

        package_manager = self._os_info.package_manager

        # Issue #380: Use module-level cached templates instead of recreating dict
        template = _PM_INSTALL_TEMPLATES.get(package_manager)
        if template:
            return template.format(tool_name)
        return None


# Global detector instance (thread-safe)
_detector_instance: Optional[OSDetector] = None
_detector_lock = asyncio.Lock()


async def get_os_detector() -> OSDetector:
    """
    Get singleton OS detector instance (thread-safe).

    Returns:
        OSDetector: Global detector instance
    """
    global _detector_instance
    if _detector_instance is None:
        async with _detector_lock:
            # Double-check after acquiring lock
            if _detector_instance is None:
                _detector_instance = OSDetector()
    return _detector_instance


if __name__ == "__main__":
    """Test the OS detector functionality."""

    async def test_detector():
        """
        Test function to demonstrate OS detector capabilities.

        Detects and displays system information, installation capabilities,
        and available tools organized by category.
        """
        detector = await get_os_detector()

        logger.info("=== OS Detection Test ===")
        os_info = await detector.detect_system()

        logger.info("OS Type: {os_info.os_type.value}")
        if os_info.distro:
            logger.info("Distribution: {os_info.distro.value}")
        logger.info("Version: {os_info.version}")
        logger.info("Architecture: {os_info.architecture}")
        logger.info("User: {os_info.user}")
        logger.info("Root Access: {os_info.is_root}")
        logger.info("WSL: {os_info.is_wsl}")
        logger.info("Package Manager: {os_info.package_manager}")
        logger.info("Shell: {os_info.shell}")
        print()

        # Test installation capability
        can_install, reason = await detector.validate_installation_capability()
        logger.info("Can Install Tools: {can_install}")
        logger.info("Reason: {reason}")
        print()

        # Show capabilities summary
        capabilities_info = await detector.get_capabilities_info()
        logger.info("=== Capabilities Summary ===")
        logger.info("Total Tools: {capabilities_info['total_count']}")
        logger.info("Network Tools: {capabilities_info['network_tools']}")
        logger.info("System Tools: {capabilities_info['system_tools']}")
        logger.info("File Tools: {capabilities_info['file_tools']}")
        logger.info("Development Tools: {capabilities_info['development_tools']}")
        print()

        # Show some examples
        logger.info("=== Available Tools (Examples) ===")
        for category, tools in capabilities_info["by_category"].items():
            if tools:
                logger.info("{category.title()}: {', '.join(tools[:5])}")
                if len(tools) > 5:
                    logger.info("  ... and {len(tools) - 5} more")

    asyncio.run(test_detector())
