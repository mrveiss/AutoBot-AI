# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OS-Aware Tool Selection Module

Selects appropriate tools based on OS capabilities and goal requirements.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.network_constants import NetworkConstants
from intelligence.goal_processor import GoalCategory, ProcessedGoal
from intelligence.os_detector import LinuxDistro, OSDetector, OSType

logger = get_logger(__name__)


@dataclass
class ToolSelection:
    """Selected tool with installation requirements."""

    primary_command: str
    fallback_commands: List[str]
    install_command: str | None
    requires_install: bool
    explanation: str
    # #7245: `IntelligentAgent._build_tool_selection_chunks` iterates
    # `tool_selection.warnings` to surface advisory notes (e.g. "tool needs
    # sudo"). Field was missing — caused AttributeError on every goal.
    # Default empty so existing constructors keep working.
    warnings: List[str] = field(default_factory=list)


class OSAwareToolSelector:
    """Select the best tools based on OS and available capabilities."""

    def __init__(self, os_detector: OSDetector):
        """Initialize tool selector with OS detector."""
        self.os_detector = os_detector
        self.tool_mappings = self._initialize_tool_mappings()

    def _initialize_tool_mappings(self) -> Dict:
        """Initialize OS-specific tool mappings (Issue #281 - uses helper methods).

        #7245: keys must reference real ``GoalCategory`` enum members. The
        original version used ``NETWORK_DISCOVERY`` / ``SECURITY_SCAN`` /
        ``SYSTEM_UPDATE`` / ``SYSTEM_INFO`` / ``PROCESS_MANAGEMENT`` — none of
        which exist on the post-rename enum (collapsed into ``NETWORK`` /
        ``SECURITY`` / ``SYSTEM`` in ``goal_processor.py``). The bare
        attribute access raised ``AttributeError: NETWORK_DISCOVERY`` during
        ``OSAwareToolSelector`` construction, hard-failing every
        ``IntelligentAgent.initialize()``.

        The 3 system-related helpers (system_update, system_info,
        process_management) merge under one ``SYSTEM`` key — they have
        non-overlapping intent keys (``system_update`` vs ``system_info`` vs
        ``list_processes`` etc.), so the lookup at
        ``_get_mapped_tools(category_tools[goal.intent])`` keeps working.
        """
        return {
            GoalCategory.NETWORK: self._get_network_discovery_tools(),
            GoalCategory.SECURITY: self._get_security_scan_tools(),
            GoalCategory.SYSTEM: {
                **self._get_system_update_tools(),
                **self._get_system_info_tools(),
                **self._get_process_management_tools(),
            },
            GoalCategory.MONITORING: self._get_monitoring_tools(),
        }

    def _get_network_discovery_tools(self) -> Dict:
        """Get network discovery tool mappings (Issue #281 - extracted helper)."""
        return {
            "get_ip_address": {
                OSType.LINUX: ["ip addr show", "ifconfig", "hostname -I"],
                OSType.MACOS: ["ifconfig", "ipconfig getifaddr en0"],
                OSType.WINDOWS: ["ipconfig", "Get-NetIPAddress"],
            },
            "scan_network": {
                OSType.LINUX: [
                    "nmap -sn {network}",
                    "arp-scan -l",
                    "ping -c 1 {target}",
                ],
                OSType.MACOS: ["nmap -sn {network}", "ping -c 1 {target}"],
                OSType.WINDOWS: ["nmap -sn {network}", "ping {target}"],
            },
            "discover_devices": {
                OSType.LINUX: [
                    "nmap -sn {network}",
                    "arp-scan {network}",
                    "ping -c 1 {target}",
                ],
                OSType.MACOS: ["nmap -sn {network}", "ping -c 1 {target}"],
                OSType.WINDOWS: ["nmap -sn {network}", "ping {target}"],
            },
        }

    def _get_security_scan_tools(self) -> Dict:
        """Get security scan tool mappings (Issue #281 - extracted helper)."""
        return {
            "port_scan": {
                OSType.LINUX: ["nmap -p- {target}", "nc -zv {target} {port}"],
                OSType.MACOS: ["nmap -p- {target}", "nc -zv {target} {port}"],
                OSType.WINDOWS: [
                    "nmap -p- {target}",
                    "Test-NetConnection {target} -Port {port}",
                ],
            },
            "vulnerability_scan": {
                OSType.LINUX: ["nmap -sV --script vuln {target}", "nikto -h {target}"],
                OSType.MACOS: ["nmap -sV --script vuln {target}"],
                OSType.WINDOWS: ["nmap -sV --script vuln {target}"],
            },
        }

    def _get_system_update_tools(self) -> Dict:
        """Get system update tool mappings (Issue #281 - extracted helper)."""
        linux_update_cmds = {
            LinuxDistro.UBUNTU: ["apt update && apt upgrade -y"],
            LinuxDistro.DEBIAN: ["apt update && apt upgrade -y"],
            LinuxDistro.CENTOS: ["yum update -y"],
            LinuxDistro.FEDORA: ["dnf update -y"],
            LinuxDistro.ARCH: ["pacman -Syu --noconfirm"],
            LinuxDistro.KALI: ["apt update && apt upgrade -y"],
        }
        return {
            "system_update": {
                OSType.LINUX: linux_update_cmds,
                OSType.MACOS: ["brew update && brew upgrade"],
                OSType.WINDOWS: ["winget upgrade --all"],
            },
            "os_update": {
                OSType.LINUX: linux_update_cmds,
                OSType.MACOS: ["softwareupdate -ia"],
                OSType.WINDOWS: ["Get-WindowsUpdate -Install -AcceptAll"],
            },
        }

    def _get_system_info_tools(self) -> Dict:
        """Get system info tool mappings (Issue #281 - extracted helper)."""
        return {
            "system_info": {
                OSType.LINUX: ["uname -a", "hostnamectl", "cat /etc/os-release"],
                OSType.MACOS: ["system_profiler SPSoftwareDataType", "uname -a"],
                OSType.WINDOWS: ["systeminfo", "Get-ComputerInfo"],
            },
            "disk_usage": {
                OSType.LINUX: ["df -h", "du -sh /*"],
                OSType.MACOS: ["df -h", "du -sh /*"],
                OSType.WINDOWS: ["Get-PSDrive", "dir"],
            },
            "memory_info": {
                OSType.LINUX: ["free -h", "vmstat"],
                OSType.MACOS: ["vm_stat", "top -l 1 -s 0"],
                OSType.WINDOWS: ["Get-WmiObject -Class Win32_OperatingSystem"],
            },
            "hardware_info": {
                OSType.LINUX: ["lshw -short", "lscpu", "dmidecode"],
                OSType.MACOS: ["system_profiler SPHardwareDataType"],
                OSType.WINDOWS: ["Get-WmiObject -Class Win32_ComputerSystem"],
            },
        }

    def _get_process_management_tools(self) -> Dict:
        """Get process management tool mappings (Issue #281 - extracted helper)."""
        return {
            "list_processes": {
                OSType.LINUX: ["ps aux", "top -n 1", "htop"],
                OSType.MACOS: ["ps aux", "top -l 1"],
                OSType.WINDOWS: ["Get-Process", "tasklist"],
            },
            "kill_process": {
                OSType.LINUX: ["kill {pid}", "killall {name}", "pkill {name}"],
                OSType.MACOS: ["kill {pid}", "killall {name}"],
                OSType.WINDOWS: ["Stop-Process -Id {pid}", "taskkill /PID {pid}"],
            },
        }

    def _get_monitoring_tools(self) -> Dict:
        """Get monitoring tool mappings (Issue #281 - extracted helper)."""
        return {
            "system_monitor": {
                OSType.LINUX: ["top", "htop", "vmstat 1"],
                OSType.MACOS: ["top", "activity monitor"],
                OSType.WINDOWS: ["Get-Counter", "perfmon"],
            },
            "performance_check": {
                OSType.LINUX: ["top -n 1", "iotop", "nethogs"],
                OSType.MACOS: ["top -l 1", "fs_usage"],
                OSType.WINDOWS: ["Get-Counter", "typeper"],
            },
        }

    def _get_tools_for_os(self, intent_tools: Dict, os_info) -> List[str] | None:
        """Get tools for the current OS/distro (Issue #315 - extracted helper)."""
        if os_info.os_type not in intent_tools:
            return None

        tools = intent_tools[os_info.os_type]
        if not isinstance(tools, dict) or not os_info.distro:
            return tools if isinstance(tools, list) else None

        # Handle Linux distro-specific tools
        if os_info.distro in tools:
            return tools[os_info.distro]

        # Fallback to Ubuntu or first available distro
        fallback_distro = LinuxDistro.UBUNTU
        return tools.get(
            fallback_distro,
            list(tools.values())[0] if tools.values() else [],
        )

    def _get_mapped_tools(self, goal: ProcessedGoal, os_info) -> List[str] | None:
        """Get mapped tools for goal (Issue #315 - extracted helper)."""
        if goal.category not in self.tool_mappings:
            return None
        category_tools = self.tool_mappings[goal.category]

        if goal.intent not in category_tools:
            return None
        intent_tools = category_tools[goal.intent]

        return self._get_tools_for_os(intent_tools, os_info)

    async def select_tool(self, goal: ProcessedGoal) -> ToolSelection:
        """Select the best tool for the given goal (Issue #315 - refactored)."""
        os_info = await self.os_detector.detect_system()

        # Try mapped tools first
        tools = self._get_mapped_tools(goal, os_info)
        if tools:
            return await self._select_best_available_tool(tools, goal)

        # Fallback to suggested tools from goal processing
        if goal.suggested_commands:
            return await self._select_best_available_tool(goal.suggested_commands, goal)

        # No specific tools found
        return ToolSelection(
            primary_command="",
            fallback_commands=[],
            install_command=None,
            requires_install=False,
            explanation=f"No specific tools mapped for: {goal.intent}",
        )

    def _categorize_tools(self, tools: List[str]) -> tuple[List[str], List[tuple]]:
        """Categorize tools by availability. Issue #620."""
        available_tools = []
        unavailable_tools = []
        for tool_cmd in tools:
            tool_name = tool_cmd.split()[0]
            if self.os_detector.has_capability(tool_name):
                available_tools.append(tool_cmd)
            else:
                unavailable_tools.append((tool_cmd, tool_name))
        return available_tools, unavailable_tools

    def _build_available_tool_selection(self, available_tools: List[str], goal: ProcessedGoal) -> ToolSelection:
        """Build ToolSelection for available tools. Issue #620."""
        primary = available_tools[0]
        fallbacks = available_tools[1:]
        return ToolSelection(
            primary_command=self._format_command(primary, goal.parameters),
            fallback_commands=[self._format_command(cmd, goal.parameters) for cmd in fallbacks],
            install_command=None,
            requires_install=False,
            explanation=f"Using available tool: {primary.split()[0]}",
        )

    async def _build_install_tool_selection(self, unavailable_tools: List[tuple], goal: ProcessedGoal) -> ToolSelection:
        """Build ToolSelection for unavailable tools needing install. Issue #620."""
        tool_cmd, tool_name = unavailable_tools[0]
        install_cmd = await self.os_detector.get_install_command(tool_name)
        return ToolSelection(
            primary_command=self._format_command(tool_cmd, goal.parameters),
            fallback_commands=[],
            install_command=install_cmd,
            requires_install=True,
            explanation=f"Tool '{tool_name}' needs to be installed",
        )

    async def _select_best_available_tool(self, tools: List[str], goal: ProcessedGoal) -> ToolSelection:
        """Select the best available tool from a list. Issue #620."""
        available_tools, unavailable_tools = self._categorize_tools(tools)

        if available_tools:
            return self._build_available_tool_selection(available_tools, goal)
        elif unavailable_tools:
            return await self._build_install_tool_selection(unavailable_tools, goal)

        return ToolSelection(
            primary_command="",
            fallback_commands=[],
            install_command=None,
            requires_install=False,
            explanation="No suitable tools found",
        )

    def _format_command(self, command: str, parameters: Dict[str, str]) -> str:
        """Format command with parameters."""
        formatted = command

        # Get default network from environment; DEFAULT_SCAN_NETWORK="" until configured

        default_network = config.default_scan_network
        resolved_network = parameters.get("network", default_network)
        if "{network}" in command and not resolved_network:
            logger.warning(
                "Tool command contains {network} placeholder but no network is configured. "
                "Set AUTOBOT_DEFAULT_SCAN_NETWORK env var or pass 'network' in parameters."
            )
            return command

        # Replace common placeholders
        replacements = {
            "{network}": resolved_network,
            "{target}": parameters.get(
                "target_ip",
                parameters.get("target_host", NetworkConstants.LOCALHOST_IP),
            ),
            "{port}": parameters.get("port", "80"),
            "{pid}": parameters.get("pid", "1"),
            "{name}": parameters.get("process_name", "unknown"),
        }

        for placeholder, value in replacements.items():
            formatted = formatted.replace(placeholder, value)

        return formatted
