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
from typing import Dict, Optional, Tuple, Set

logger = logging.getLogger(__name__)


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

    async def detect_system(self) -> OSInfo:
        """
        Detect system information and capabilities.

        Returns:
            OSInfo: Complete system information
        """
        if self._os_info is not None:
            return self._os_info

        logger.info("Detecting system information...")

        # Detect OS type
        os_type = self._detect_os_type()

        # Detect Linux distribution if applicable
        distro = None
        if os_type == OSType.LINUX:
            distro = await self._detect_linux_distro()

        # Get system details
        version = platform.release()
        architecture = platform.machine()
        user = os.getenv("USER", os.getenv("USERNAME", "unknown"))
        is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
        is_wsl = self._detect_wsl()

        # Detect package manager
        package_manager = await self._detect_package_manager(os_type, distro)

        # Detect shell
        shell = os.getenv("SHELL", "unknown")

        # Detect capabilities
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
            shell=shell,
            capabilities=capabilities,
        )

        logger.info(
            f"System detected: {os_type.value} "
            f"({distro.value if distro else 'N/A'})"
        )
        logger.info(f"User: {user} (root: {is_root})")
        logger.info(f"Capabilities: {len(capabilities)} tools detected")

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

    async def _detect_linux_distro(self) -> LinuxDistro:
        """Detect Linux distribution."""
        try:
            # Try /etc/os-release first
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r") as f:
                    content = f.read().lower()

                    if "ubuntu" in content:
                        return LinuxDistro.UBUNTU
                    elif "debian" in content:
                        return LinuxDistro.DEBIAN
                    elif "fedora" in content:
                        return LinuxDistro.FEDORA
                    elif "centos" in content:
                        return LinuxDistro.CENTOS
                    elif "rhel" in content or "red hat" in content:
                        return LinuxDistro.RHEL
                    elif "arch" in content:
                        return LinuxDistro.ARCH
                    elif "opensuse" in content or "suse" in content:
                        return LinuxDistro.OPENSUSE
                    elif "kali" in content:
                        return LinuxDistro.KALI

            # Fallback to other methods
            if os.path.exists("/etc/debian_version"):
                return LinuxDistro.DEBIAN
            elif os.path.exists("/etc/fedora-release"):
                return LinuxDistro.FEDORA
            elif os.path.exists("/etc/centos-release"):
                return LinuxDistro.CENTOS
            elif os.path.exists("/etc/arch-release"):
                return LinuxDistro.ARCH

        except Exception as e:
            logger.warning(f"Error detecting Linux distribution: {e}")

        return LinuxDistro.UNKNOWN

    def _detect_wsl(self) -> bool:
        """Detect if running in Windows Subsystem for Linux."""
        try:
            if os.path.exists("/proc/version"):
                with open("/proc/version", "r") as f:
                    content = f.read().lower()
                    return "microsoft" in content or "wsl" in content
        except Exception:
            pass

        return False

    async def _detect_package_manager(
        self, os_type: OSType, distro: Optional[LinuxDistro]
    ) -> str:
        """Detect the system package manager."""
        if os_type == OSType.LINUX:
            if distro in [LinuxDistro.UBUNTU, LinuxDistro.DEBIAN, LinuxDistro.KALI]:
                return "apt"
            elif distro == LinuxDistro.FEDORA:
                return "dnf"
            elif distro in [LinuxDistro.CENTOS, LinuxDistro.RHEL]:
                return "yum"
            elif distro == LinuxDistro.ARCH:
                return "pacman"
            elif distro == LinuxDistro.OPENSUSE:
                return "zypper"
            else:
                # Auto-detect common package managers
                for pm in ["apt", "dnf", "yum", "pacman", "zypper"]:
                    if shutil.which(pm):
                        return pm
        elif os_type == OSType.MACOS:
            if shutil.which("brew"):
                return "brew"
            elif shutil.which("port"):
                return "port"
        elif os_type == OSType.WINDOWS:
            if shutil.which("winget"):
                return "winget"
            elif shutil.which("choco"):
                return "choco"

        return "unknown"

    async def _detect_capabilities(self) -> Set[str]:
        """Detect available system capabilities and tools."""
        if self._capabilities_cache is not None:
            return set(self._capabilities_cache.keys())

        capabilities = set()

        # Network tools
        network_tools = [
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
        ]

        # System tools
        system_tools = [
            "ps",
            "top",
            "htop",
            "df",
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
        ]

        # File tools
        file_tools = [
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
        ]

        # Development tools
        dev_tools = [
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
        ]

        all_tools = network_tools + system_tools + file_tools + dev_tools

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
        root_required_managers = ["apt", "yum", "dnf", "pacman", "zypper"]

        if (
            self._os_info.package_manager in root_required_managers
            and not self._os_info.is_root
            and not shutil.which("sudo")
        ):
            return (
                False,
                f"Package manager {self._os_info.package_manager} "
                f"requires root access",
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

        # Categorize capabilities
        network_tools = [
            tool
            for tool in capabilities
            if tool
            in [
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
            ]
        ]

        system_tools = [
            tool
            for tool in capabilities
            if tool
            in [
                "ps",
                "top",
                "htop",
                "df",
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
            ]
        ]

        file_tools = [
            tool
            for tool in capabilities
            if tool
            in [
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
            ]
        ]

        dev_tools = [
            tool
            for tool in capabilities
            if tool
            in [
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
            ]
        ]

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

        if package_manager == "apt":
            return f"sudo apt update && sudo apt install -y {tool_name}"
        elif package_manager == "dnf":
            return f"sudo dnf install -y {tool_name}"
        elif package_manager == "yum":
            return f"sudo yum install -y {tool_name}"
        elif package_manager == "pacman":
            return f"sudo pacman -S --noconfirm {tool_name}"
        elif package_manager == "zypper":
            return f"sudo zypper install -y {tool_name}"
        elif package_manager == "brew":
            return f"brew install {tool_name}"
        elif package_manager == "winget":
            return f"winget install {tool_name}"
        elif package_manager == "choco":
            return f"choco install {tool_name}"

        return None


# Global detector instance
_detector_instance: Optional[OSDetector] = None


async def get_os_detector() -> OSDetector:
    """
    Get singleton OS detector instance.

    Returns:
        OSDetector: Global detector instance
    """
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = OSDetector()
    return _detector_instance


if __name__ == "__main__":
    """Test the OS detector functionality."""

    async def test_detector():
        detector = await get_os_detector()

        print("=== OS Detection Test ===")
        os_info = await detector.detect_system()

        print(f"OS Type: {os_info.os_type.value}")
        if os_info.distro:
            print(f"Distribution: {os_info.distro.value}")
        print(f"Version: {os_info.version}")
        print(f"Architecture: {os_info.architecture}")
        print(f"User: {os_info.user}")
        print(f"Root Access: {os_info.is_root}")
        print(f"WSL: {os_info.is_wsl}")
        print(f"Package Manager: {os_info.package_manager}")
        print(f"Shell: {os_info.shell}")
        print()

        # Test installation capability
        can_install, reason = await detector.validate_installation_capability()
        print(f"Can Install Tools: {can_install}")
        print(f"Reason: {reason}")
        print()

        # Show capabilities summary
        capabilities_info = await detector.get_capabilities_info()
        print("=== Capabilities Summary ===")
        print(f"Total Tools: {capabilities_info['total_count']}")
        print(f"Network Tools: {capabilities_info['network_tools']}")
        print(f"System Tools: {capabilities_info['system_tools']}")
        print(f"File Tools: {capabilities_info['file_tools']}")
        print(f"Development Tools: {capabilities_info['development_tools']}")
        print()

        # Show some examples
        print("=== Available Tools (Examples) ===")
        for category, tools in capabilities_info["by_category"].items():
            if tools:
                print(f"{category.title()}: {', '.join(tools[:5])}")
                if len(tools) > 5:
                    print(f"  ... and {len(tools) - 5} more")

    asyncio.run(test_detector())
