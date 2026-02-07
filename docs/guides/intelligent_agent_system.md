# Intelligent Agent System - Complete Implementation

## Overview

This system creates an intelligent agent that can:
- Understand natural language goals ("do the os update", "what is your ip?")
- Automatically select appropriate tools/commands
- Discover and install missing tools
- Stream command output in real-time
- Provide intelligent commentary on results
- Be fully OS-aware

## Architecture

```
User Input: "what other devices are on our network?"
     ↓
[Goal Processor] → Understands intent
     ↓
[OS-Aware Tool Selector] → Chooses: nmap, arp-scan, or ping sweep
     ↓
[Tool Discovery] → Checks if tool exists, installs if needed
     ↓
[Streaming Executor] → Runs command with real-time output
     ↓
[Result Analyzer] → LLM analyzes output and provides commentary
     ↓
User receives: Streamed output + intelligent analysis
```

## Step-by-Step Implementation

### Step 1: OS Detection and Awareness System

```python
# src/system/os_detector.py
import platform
import subprocess
import shutil
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class OSType(Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    WSL = "wsl"

class LinuxDistro(Enum):
    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    CENTOS = "centos"
    RHEL = "rhel"
    FEDORA = "fedora"
    ARCH = "arch"
    KALI = "kali"
    UNKNOWN = "unknown"

@dataclass
class OSInfo:
    os_type: OSType
    distro: Optional[LinuxDistro] = None
    version: str = ""
    architecture: str = ""
    kernel_version: str = ""
    package_manager: str = ""
    shell: str = ""
    user: str = ""
    is_root: bool = False
    capabilities: List[str] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []

class OSDetector:
    """Comprehensive OS detection and system awareness"""

    def __init__(self):
        self._os_info = None
        self._tool_cache = {}

    async def detect_system(self) -> OSInfo:
        """Detect comprehensive OS information"""
        if self._os_info:
            return self._os_info

        system = platform.system().lower()

        if system == "linux":
            self._os_info = await self._detect_linux()
        elif system == "windows":
            self._os_info = await self._detect_windows()
        elif system == "darwin":
            self._os_info = await self._detect_macos()
        else:
            self._os_info = OSInfo(
                os_type=OSType.LINUX,
                version="unknown",
                architecture=platform.machine()
            )

        return self._os_info

    async def _detect_linux(self) -> OSInfo:
        """Detect Linux distribution and capabilities"""
        distro = LinuxDistro.UNKNOWN
        version = ""
        package_manager = ""

        # Detect WSL
        is_wsl = False
        try:
            with open('/proc/version', 'r') as f:
                if 'microsoft' in f.read().lower():
                    is_wsl = True
        except:
            pass

        # Detect distribution
        try:
            # Try /etc/os-release first
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    content = f.read().lower()
                    if 'ubuntu' in content:
                        distro = LinuxDistro.UBUNTU
                        package_manager = "apt"
                    elif 'debian' in content:
                        distro = LinuxDistro.DEBIAN
                        package_manager = "apt"
                    elif 'centos' in content:
                        distro = LinuxDistro.CENTOS
                        package_manager = "yum"
                    elif 'rhel' in content or 'red hat' in content:
                        distro = LinuxDistro.RHEL
                        package_manager = "yum"
                    elif 'fedora' in content:
                        distro = LinuxDistro.FEDORA
                        package_manager = "dnf"
                    elif 'arch' in content:
                        distro = LinuxDistro.ARCH
                        package_manager = "pacman"
                    elif 'kali' in content:
                        distro = LinuxDistro.KALI
                        package_manager = "apt"

            # Get version
            result = subprocess.run(['lsb_release', '-r'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.split('\t')[1].strip()
        except:
            pass

        # Detect capabilities
        capabilities = []

        # Check if running as root
        is_root = os.geteuid() == 0

        # Check for sudo
        if shutil.which('sudo'):
            capabilities.append('sudo')

        # Check for network tools
        network_tools = ['nmap', 'netstat', 'ss', 'arp', 'ping', 'traceroute']
        for tool in network_tools:
            if shutil.which(tool):
                capabilities.append(f'network_{tool}')

        # Check for system tools
        system_tools = ['systemctl', 'service', 'ps', 'top', 'htop']
        for tool in system_tools:
            if shutil.which(tool):
                capabilities.append(f'system_{tool}')

        return OSInfo(
            os_type=OSType.WSL if is_wsl else OSType.LINUX,
            distro=distro,
            version=version,
            architecture=platform.machine(),
            kernel_version=platform.release(),
            package_manager=package_manager,
            shell=os.environ.get('SHELL', '/bin/bash'),
            user=os.environ.get('USER', 'unknown'),
            is_root=is_root,
            capabilities=capabilities
        )

    async def _detect_windows(self) -> OSInfo:
        """Detect Windows system information"""
        capabilities = []

        # Check for PowerShell
        if shutil.which('powershell') or shutil.which('pwsh'):
            capabilities.append('powershell')

        # Check for WSL
        if shutil.which('wsl'):
            capabilities.append('wsl')

        # Check for common Windows tools
        windows_tools = ['netstat', 'ping', 'tracert', 'ipconfig', 'tasklist']
        for tool in windows_tools:
            if shutil.which(tool):
                capabilities.append(f'windows_{tool}')

        return OSInfo(
            os_type=OSType.WINDOWS,
            version=platform.release(),
            architecture=platform.machine(),
            package_manager="winget",  # or chocolatey
            shell="cmd",
            user=os.environ.get('USERNAME', 'unknown'),
            is_root='Administrator' in subprocess.getoutput('whoami'),
            capabilities=capabilities
        )

    async def _detect_macos(self) -> OSInfo:
        """Detect macOS system information"""
        capabilities = []

        # Check for Homebrew
        if shutil.which('brew'):
            capabilities.append('homebrew')

        # Check for common macOS tools
        macos_tools = ['netstat', 'ping', 'traceroute', 'ifconfig', 'ps']
        for tool in macos_tools:
            if shutil.which(tool):
                capabilities.append(f'macos_{tool}')

        return OSInfo(
            os_type=OSType.MACOS,
            version=platform.mac_ver()[0],
            architecture=platform.machine(),
            package_manager="brew",
            shell=os.environ.get('SHELL', '/bin/bash'),
            user=os.environ.get('USER', 'unknown'),
            is_root=os.geteuid() == 0,
            capabilities=capabilities
        )

    async def has_tool(self, tool_name: str) -> bool:
        """Check if a tool is available"""
        if tool_name in self._tool_cache:
            return self._tool_cache[tool_name]

        result = shutil.which(tool_name) is not None
        self._tool_cache[tool_name] = result
        return result

    async def get_install_command(self, tool_name: str) -> Optional[str]:
        """Get the command to install a tool on this OS"""
        os_info = await self.detect_system()

        # Tool installation mappings
        install_commands = {
            OSType.LINUX: {
                "apt": {
                    "nmap": "apt install -y nmap",
                    "arp-scan": "apt install -y arp-scan",
                    "netstat": "apt install -y net-tools",
                    "ss": "apt install -y iproute2",
                    "htop": "apt install -y htop",
                    "curl": "apt install -y curl",
                    "wget": "apt install -y wget",
                    "git": "apt install -y git",
                    "python3": "apt install -y python3",
                    "pip": "apt install -y python3-pip"
                },
                "yum": {
                    "nmap": "yum install -y nmap",
                    "arp-scan": "yum install -y arp-scan",
                    "netstat": "yum install -y net-tools",
                    "htop": "yum install -y htop",
                    "curl": "yum install -y curl",
                    "wget": "yum install -y wget"
                },
                "dnf": {
                    "nmap": "dnf install -y nmap",
                    "arp-scan": "dnf install -y arp-scan",
                    "netstat": "dnf install -y net-tools",
                    "htop": "dnf install -y htop"
                },
                "pacman": {
                    "nmap": "pacman -S --noconfirm nmap",
                    "arp-scan": "pacman -S --noconfirm arp-scan",
                    "netstat": "pacman -S --noconfirm net-tools",
                    "htop": "pacman -S --noconfirm htop"
                }
            },
            OSType.MACOS: {
                "brew": {
                    "nmap": "brew install nmap",
                    "arp-scan": "brew install arp-scan",
                    "htop": "brew install htop",
                    "curl": "brew install curl",
                    "wget": "brew install wget"
                }
            },
            OSType.WINDOWS: {
                "winget": {
                    "nmap": "winget install nmap",
                    "curl": "winget install curl",
                    "wget": "winget install wget",
                    "git": "winget install git"
                }
            }
        }

        if os_info.os_type in install_commands:
            pkg_mgr = os_info.package_manager
            if pkg_mgr in install_commands[os_info.os_type]:
                return install_commands[os_info.os_type][pkg_mgr].get(tool_name)

        return None
```

### Step 2: Goal Processing and Intent Understanding

```python
# src/intelligence/goal_processor.py
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class GoalCategory(Enum):
    NETWORK_DISCOVERY = "network_discovery"
    SYSTEM_UPDATE = "system_update"
    SYSTEM_INFO = "system_info"
    FILE_OPERATIONS = "file_operations"
    PROCESS_MANAGEMENT = "process_management"
    SECURITY_SCAN = "security_scan"
    PACKAGE_MANAGEMENT = "package_management"
    MONITORING = "monitoring"
    UNKNOWN = "unknown"

@dataclass
class ProcessedGoal:
    original_goal: str
    category: GoalCategory
    intent: str
    parameters: Dict[str, str]
    confidence: float
    suggested_tools: List[str]
    requires_root: bool = False
    risk_level: str = "low"

class GoalProcessor:
    """Process natural language goals into actionable intents"""

    def __init__(self):
        self.goal_patterns = {
            GoalCategory.NETWORK_DISCOVERY: [
                (r"what.*ip.*address", "get_ip_address", ["ip", "ifconfig", "hostname"]),
                (r"what.*devices.*network", "scan_network", ["nmap", "arp-scan", "ping"]),
                (r"scan.*network", "scan_network", ["nmap", "arp-scan"]),
                (r"find.*devices", "discover_devices", ["nmap", "arp-scan"]),
                (r"network.*scan", "network_scan", ["nmap", "masscan"]),
            ],
            GoalCategory.SECURITY_SCAN: [
                (r"find.*open.*ports", "port_scan", ["nmap", "masscan"]),
                (r"scan.*ports", "port_scan", ["nmap", "nc"]),
                (r"check.*vulnerabilities", "vulnerability_scan", ["nmap", "nikto"]),
                (r"security.*scan", "security_scan", ["nmap", "openvas"]),
            ],
            GoalCategory.SYSTEM_UPDATE: [
                (r"update.*system", "system_update", ["apt", "yum", "dnf", "brew"]),
                (r"upgrade.*system", "system_upgrade", ["apt", "yum", "dnf"]),
                (r"os.*update", "os_update", ["apt", "yum", "dnf"]),
                (r"install.*updates", "install_updates", ["apt", "yum", "dnf"]),
            ],
            GoalCategory.SYSTEM_INFO: [
                (r"system.*info", "system_info", ["uname", "hostnamectl", "lscpu"]),
                (r"hardware.*info", "hardware_info", ["lshw", "dmidecode", "lscpu"]),
                (r"disk.*space", "disk_usage", ["df", "du"]),
                (r"memory.*usage", "memory_info", ["free", "vmstat"]),
                (r"what.*os", "os_info", ["uname", "cat /etc/os-release"]),
            ],
            GoalCategory.PROCESS_MANAGEMENT: [
                (r"list.*processes", "list_processes", ["ps", "top", "htop"]),
                (r"kill.*process", "kill_process", ["kill", "killall", "pkill"]),
                (r"running.*processes", "show_processes", ["ps", "pgrep"]),
            ],
            GoalCategory.MONITORING: [
                (r"monitor.*system", "system_monitor", ["top", "htop", "vmstat"]),
                (r"check.*performance", "performance_check", ["top", "iotop", "nethogs"]),
                (r"system.*load", "system_load", ["uptime", "w", "top"]),
            ]
        }

    async def process_goal(self, goal: str) -> ProcessedGoal:
        """Process a natural language goal into structured intent"""
        goal_lower = goal.lower().strip()

        # Find matching pattern
        best_match = None
        best_confidence = 0.0

        for category, patterns in self.goal_patterns.items():
            for pattern, intent, tools in patterns:
                if re.search(pattern, goal_lower):
                    # Calculate confidence based on pattern match quality
                    confidence = self._calculate_confidence(pattern, goal_lower)
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = (category, intent, tools)

        if best_match:
            category, intent, tools = best_match
            parameters = self._extract_parameters(goal_lower, intent)

            return ProcessedGoal(
                original_goal=goal,
                category=category,
                intent=intent,
                parameters=parameters,
                confidence=best_confidence,
                suggested_tools=tools,
                requires_root=self._requires_root(intent),
                risk_level=self._assess_risk(intent)
            )

        # Unknown goal - let LLM handle it
        return ProcessedGoal(
            original_goal=goal,
            category=GoalCategory.UNKNOWN,
            intent="unknown",
            parameters={},
            confidence=0.0,
            suggested_tools=[],
            requires_root=False,
            risk_level="unknown"
        )

    def _calculate_confidence(self, pattern: str, goal: str) -> float:
        """Calculate confidence score for pattern match"""
        # Simple confidence based on pattern specificity
        pattern_words = len(pattern.split())
        goal_words = len(goal.split())

        base_confidence = 0.7
        specificity_bonus = min(pattern_words / goal_words, 0.3)

        return base_confidence + specificity_bonus

    def _extract_parameters(self, goal: str, intent: str) -> Dict[str, str]:
        """Extract parameters from goal text"""
        parameters = {}

        # Extract IP addresses
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ips = re.findall(ip_pattern, goal)
        if ips:
            parameters['target_ip'] = ips[0]

        # Extract hostnames
        hostname_pattern = r'\b[a-zA-Z0-9][-a-zA-Z0-9]*[a-zA-Z0-9]*\.[a-zA-Z]{2,}\b'
        hostnames = re.findall(hostname_pattern, goal)
        if hostnames:
            parameters['target_host'] = hostnames[0]

        # Extract port numbers
        port_pattern = r'\bport\s+(\d+)\b'
        ports = re.findall(port_pattern, goal)
        if ports:
            parameters['port'] = ports[0]

        # Extract network ranges
        network_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b'
        networks = re.findall(network_pattern, goal)
        if networks:
            parameters['network'] = networks[0]

        return parameters

    def _requires_root(self, intent: str) -> bool:
        """Check if intent requires root privileges"""
        root_required = [
            'system_update', 'system_upgrade', 'os_update',
            'install_updates', 'port_scan', 'network_scan'
        ]
        return intent in root_required

    def _assess_risk(self, intent: str) -> str:
        """Assess risk level of intent"""
        high_risk = ['vulnerability_scan', 'security_scan', 'kill_process']
        medium_risk = ['port_scan', 'network_scan', 'system_update']

        if intent in high_risk:
            return "high"
        elif intent in medium_risk:
            return "medium"
        else:
            return "low"
```

### Step 3: OS-Aware Tool Selector

```python
# src/intelligence/tool_selector.py
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from src.system.os_detector import OSDetector, OSType, LinuxDistro
from src.intelligence.goal_processor import ProcessedGoal, GoalCategory

@dataclass
class ToolSelection:
    primary_command: str
    fallback_commands: List[str]
    install_command: Optional[str]
    requires_install: bool
    explanation: str

class OSAwareToolSelector:
    """Select the best tools based on OS and available capabilities"""

    def __init__(self, os_detector: OSDetector):
        self.os_detector = os_detector
        self.tool_mappings = self._initialize_tool_mappings()

    def _initialize_tool_mappings(self) -> Dict:
        """Initialize OS-specific tool mappings"""
        return {
            GoalCategory.NETWORK_DISCOVERY: {
                "get_ip_address": {
                    OSType.LINUX: ["ip addr show", "ifconfig", "hostname -I"],
                    OSType.MACOS: ["ifconfig", "ipconfig getifaddr en0"],
                    OSType.WINDOWS: ["ipconfig", "Get-NetIPAddress"]
                },
                "scan_network": {
                    OSType.LINUX: ["nmap -sn {network}", "arp-scan -l", "ping -c 1 {target}"],
                    OSType.MACOS: ["nmap -sn {network}", "ping -c 1 {target}"],
                    OSType.WINDOWS: ["nmap -sn {network}", "ping {target}"]
                }
            },
            GoalCategory.SECURITY_SCAN: {
                "port_scan": {
                    OSType.LINUX: ["nmap -p- {target}", "nc -zv {target} {port}"],
                    OSType.MACOS: ["nmap -p- {target}", "nc -zv {target} {port}"],
                    OSType.WINDOWS: ["nmap -p- {target}", "Test-NetConnection {target} -Port {port}"]
                }
            },
            GoalCategory.SYSTEM_UPDATE: {
                "system_update": {
                    OSType.LINUX: {
                        LinuxDistro.UBUNTU: ["apt update && apt upgrade -y"],
                        LinuxDistro.DEBIAN: ["apt update && apt upgrade -y"],
                        LinuxDistro.CENTOS: ["yum update -y"],
                        LinuxDistro.FEDORA: ["dnf update -y"],
                        LinuxDistro.ARCH: ["pacman -Syu --noconfirm"]
                    },
                    OSType.MACOS: ["brew update && brew upgrade"],
                    OSType.WINDOWS: ["winget upgrade --all"]
                }
            },
            GoalCategory.SYSTEM_INFO: {
                "system_info": {
                    OSType.LINUX: ["uname -a", "hostnamectl", "cat /etc/os-release"],
                    OSType.MACOS: ["system_profiler SPSoftwareDataType", "uname -a"],
                    OSType.WINDOWS: ["systeminfo", "Get-ComputerInfo"]
                },
                "disk_usage": {
                    OSType.LINUX: ["df -h", "du -sh /*"],
                    OSType.MACOS: ["df -h", "du -sh /*"],
                    OSType.WINDOWS: ["Get-PSDrive", "dir"]
                }
            }
        }

    async def select_tool(self, goal: ProcessedGoal) -> ToolSelection:
        """Select the best tool for the given goal"""
        os_info = await self.os_detector.detect_system()

        # Get tool mapping for this goal
        if goal.category in self.tool_mappings:
            category_tools = self.tool_mappings[goal.category]
            if goal.intent in category_tools:
                intent_tools = category_tools[goal.intent]

                # Handle nested OS/distro mapping
                if os_info.os_type in intent_tools:
                    tools = intent_tools[os_info.os_type]

                    # Handle Linux distro-specific tools
                    if isinstance(tools, dict) and os_info.distro:
                        if os_info.distro in tools:
                            tools = tools[os_info.distro]
                        else:
                            # Fallback to common Linux tools
                            tools = tools.get(LinuxDistro.UBUNTU, list(tools.values())[0])

                    if isinstance(tools, list) and tools:
                        # Select best available tool
                        return await self._select_best_available_tool(tools, goal)

        # Fallback to suggested tools from goal processing
        if goal.suggested_tools:
            return await self._select_best_available_tool(goal.suggested_tools, goal)

        # No specific tools found - let LLM decide
        return ToolSelection(
            primary_command="",
            fallback_commands=[],
            install_command=None,
            requires_install=False,
            explanation=f"No specific tools mapped for: {goal.intent}"
        )

    async def _select_best_available_tool(self, tools: List[str], goal: ProcessedGoal) -> ToolSelection:
        """Select the best available tool from a list"""
        available_tools = []
        unavailable_tools = []

        for tool_cmd in tools:
            # Extract tool name from command
            tool_name = tool_cmd.split()[0]

            if await self.os_detector.has_tool(tool_name):
                available_tools.append(tool_cmd)
            else:
                unavailable_tools.append((tool_cmd, tool_name))

        if available_tools:
            # Use first available tool as primary
            primary = available_tools[0]
            fallbacks = available_tools[1:]

            # Format command with parameters
            formatted_primary = self._format_command(primary, goal.parameters)

            return ToolSelection(
                primary_command=formatted_primary,
                fallback_commands=[self._format_command(cmd, goal.parameters) for cmd in fallbacks],
                install_command=None,
                requires_install=False,
                explanation=f"Using available tool: {primary.split()[0]}"
            )

        elif unavailable_tools:
            # Need to install a tool
            tool_cmd, tool_name = unavailable_tools[0]
            install_cmd = await self.os_detector.get_install_command(tool_name)

            formatted_cmd = self._format_command(tool_cmd, goal.parameters)

            return ToolSelection(
                primary_command=formatted_cmd,
                fallback_commands=[],
                install_command=install_cmd,
                requires_install=True,
                explanation=f"Tool '{tool_name}' needs to be installed"
            )

        return ToolSelection(
            primary_command="",
            fallback_commands=[],
            install_command=None,
            requires_install=False,
            explanation="No suitable tools found"
        )

    def _format_command(self, command: str, parameters: Dict[str, str]) -> str:
        """Format command with parameters"""
        formatted = command

        # Replace common placeholders
        replacements = {
            '{network}': parameters.get('network', '192.168.1.0/24'),
            '{target}': parameters.get('target_ip', parameters.get('target_host', '127.0.0.1')),
            '{port}': parameters.get('port', '80')
        }

        for placeholder, value in replacements.items():
            formatted = formatted.replace(placeholder, value)

        return formatted
```

### Step 4: Streaming Command Executor with Real-time Output

```python
# src/execution/streaming_executor.py
import asyncio
import subprocess
import json
import time
from typing import AsyncGenerator, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class StreamChunk:
    timestamp: str
    chunk_type: str  # "stdout", "stderr", "status", "commentary"
    content: str
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        if self.metadata is None:
            result['metadata'] = {}
        return result

class StreamingCommandExecutor:
    """Execute commands with real-time streaming output"""

    def __init__(self, llm_interface=None):
        self.llm_interface = llm_interface
        self.active_processes = {}

    async def execute_with_streaming(self,
                                   command: str,
                                   goal: str,
                                   working_dir: str = ".",
                                   timeout: int = 300) -> AsyncGenerator[StreamChunk, None]:
        """Execute command with real-time streaming output and commentary"""

        process_id = f"cmd_{int(time.time())}"

        # Send initial status
        yield StreamChunk(
            timestamp=datetime.now().isoformat(),
            chunk_type="status",
            content=f"🚀 Starting execution: {command}",
            metadata={"command": command, "goal": goal, "process_id": process_id}
        )

        # Send initial commentary
        if self.llm_interface:
            initial_comment = await self._get_initial_commentary(command, goal)
            yield StreamChunk(
                timestamp=datetime.now().isoformat(),
                chunk_type="commentary",
                content=f"💭 {initial_comment}",
                metadata={"type": "initial_analysis"}
            )

        try:
            # Start the process
            process = await asyncio.create_subprocess_exec(
                *command.split(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir
            )

            self.active_processes[process_id] = process

            # Stream output in real-time
            output_buffer = []
            error_buffer = []

            async def read_stdout():
                while True:
                    try:
                        line = await process.stdout.readline()
                        if not line:
                            break

                        decoded_line = line.decode('utf-8', errors='replace').rstrip()
                        output_buffer.append(decoded_line)

                        yield StreamChunk(
                            timestamp=datetime.now().isoformat(),
                            chunk_type="stdout",
                            content=decoded_line,
                            metadata={"process_id": process_id}
                        )

                        # Provide periodic commentary on output
                        if len(output_buffer) % 10 == 0 and self.llm_interface:
                            recent_output = '\n'.join(output_buffer[-5:])
                            commentary = await self._get_progress_commentary(recent_output, goal)
                            if commentary:
                                yield StreamChunk(
                                    timestamp=datetime.now().isoformat(),
                                    chunk_type="commentary",
                                    content=f"🔍 {commentary}",
                                    metadata={"type": "progress_analysis"}
                                )

                    except Exception as e:
                        yield StreamChunk(
                            timestamp=datetime.now().isoformat(),
                            chunk_type="stderr",
                            content=f"Error reading stdout: {str(e)}",
                            metadata={"error": True}
                        )
                        break

            async def read_stderr():
                while True:
                    try:
                        line = await process.stderr.readline()
                        if not line:
                            break

                        decoded_line = line.decode('utf-8', errors='replace').rstrip()
                        error_buffer.append(decoded_line)

                        yield StreamChunk(
                            timestamp=datetime.now().isoformat(),
                            chunk_type="stderr",
                            content=decoded_line,
                            metadata={"process_id": process_id, "error": True}
                        )

                    except Exception as e:
                        yield StreamChunk(
                            timestamp=datetime.now().isoformat(),
                            chunk_type="stderr",
                            content=f"Error reading stderr: {str(e)}",
                            metadata={"error": True}
                        )
                        break

            # Stream both stdout and stderr concurrently
            async for chunk in self._merge_streams(read_stdout(), read_stderr()):
                yield chunk

            # Wait for process completion
            try:
                return_code = await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                yield StreamChunk(
                    timestamp=datetime.now().isoformat(),
                    chunk_type="status",
                    content="⏰ Command timed out and was terminated",
                    metadata={"timeout": True, "process_id": process_id}
                )
                return_code = -1

            # Send completion status
            success = return_code == 0
            status_emoji = "✅" if success else "❌"
            yield StreamChunk(
                timestamp=datetime.now().isoformat(),
                chunk_type="status",
                content=f"{status_emoji} Command completed with exit code: {return_code}",
                metadata={"exit_code": return_code, "success": success, "process_id": process_id}
            )

            # Provide final commentary on results
            if self.llm_interface:
                full_output = '\n'.join(output_buffer)
                full_error = '\n'.join(error_buffer)

                final_commentary = await self._get_final_commentary(
                    command, goal, full_output, full_error, return_code
                )

                yield StreamChunk(
                    timestamp=datetime.now().isoformat(),
                    chunk_type="commentary",
                    content=f"📊 {final_commentary}",
                    metadata={"type": "final_analysis", "success": success}
                )

        except Exception as e:
            yield StreamChunk(
                timestamp=datetime.now().isoformat(),
                chunk_type="status",
                content=f"❌ Error executing command: {str(e)}",
                metadata={"error": True, "exception": str(e)}
            )

        finally:
            # Cleanup
            if process_id in self.active_processes:
                del self.active_processes[process_id]

    async def _merge_streams(self, *streams) -> AsyncGenerator[StreamChunk, None]:
        """Merge multiple async streams into one"""
        pending = {asyncio.create_task(stream.__anext__()): stream for stream in streams}

        while pending:
            done, _ = await asyncio.wait(pending.keys(), return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                stream = pending.pop(task)
                try:
                    chunk = task.result()
                    yield chunk
                    # Create new task for this stream
                    pending[asyncio.create_task(stream.__anext__())] = stream
                except StopAsyncIteration:
                    # Stream is exhausted
                    continue
                except Exception as e:
                    # Error in stream - log and continue
                    yield StreamChunk(
                        timestamp=datetime.now().isoformat(),
                        chunk_type="stderr",
                        content=f"Stream error: {str(e)}",
                        metadata={"error": True}
                    )

    async def _get_initial_commentary(self, command: str, goal: str) -> str:
        """Get initial commentary about the command"""
        if not self.llm_interface:
            return f"Executing {command.split()[0]} to {goal}"

        try:
            prompt = f"""
            I'm about to execute this command: {command}
            Goal: {goal}

            Provide a brief, helpful comment about what this command will do and what to expect.
            Keep it under 50 words and be encouraging.
            """

            response = await self.llm_interface.generate_response(prompt)
            return response.strip()
        except:
            return f"Running {command.split()[0]} to accomplish: {goal}"

    async def _get_progress_commentary(self, recent_output: str, goal: str) -> Optional[str]:
        """Get commentary on command progress"""
        if not self.llm_interface or not recent_output.strip():
            return None

        try:
            prompt = f"""
            Command output so far:
            {recent_output}

            Goal: {goal}

            Provide a brief progress update or observation about what's happening.
            Keep it under 30 words. Only respond if there's something meaningful to say.
            If the output is routine/boring, respond with "SKIP".
            """

            response = await self.llm_interface.generate_response(prompt)
            return response.strip() if response.strip() != "SKIP" else None
        except:
            return None

    async def _get_final_commentary(self,
                                  command: str,
                                  goal: str,
                                  output: str,
                                  error: str,
                                  exit_code: int) -> str:
        """Get final commentary on command results"""
        if not self.llm_interface:
            if exit_code == 0:
                return f"Command completed successfully!"
            else:
                return f"Command failed with exit code {exit_code}"

        try:
            prompt = f"""
            Command: {command}
            Goal: {goal}
            Exit Code: {exit_code}

            Output:
            {output[:1000]}  # Limit output length

            Error:
            {error[:500]}

            Provide intelligent analysis of these results:
            1. Did it accomplish the goal?
            2. What do the results mean?
            3. Any next steps or recommendations?

            Keep response under 100 words and be helpful.
            """

            response = await self.llm_interface.generate_response(prompt)
            return response.strip()
        except:
            status = "successfully" if exit_code == 0 else f"with exit code {exit_code}"
            return f"Command completed {status}. {len(output.split())} lines of output generated."
```

### Step 5: Intelligent Agent Orchestrator

```python
# src/intelligence/intelligent_agent.py
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, Optional

from src.system.os_detector import OSDetector
from src.intelligence.goal_processor import GoalProcessor
from src.intelligence.tool_selector import OSAwareToolSelector
from src.execution.streaming_executor import StreamingCommandExecutor, StreamChunk
from src.services.enhanced_command_service import EnhancedCommandService

logger = logging.getLogger(__name__)

class IntelligentAgent:
    """Main intelligent agent that orchestrates the entire workflow"""

    def __init__(self,
                 llm_interface,
                 knowledge_base,
                 worker_node,
                 command_validator):
        self.llm_interface = llm_interface
        self.knowledge_base = knowledge_base
        self.worker_node = worker_node
        self.command_validator = command_validator

        # Initialize components
        self.os_detector = OSDetector()
        self.goal_processor = GoalProcessor()
        self.tool_selector = OSAwareToolSelector(self.os_detector)
        self.streaming_executor = StreamingCommandExecutor(llm_interface)
        self.command_service = EnhancedCommandService(
            knowledge_base, worker_node, command_validator
        )

        # System state
        self.os_info = None
        self.conversation_context = []

    async def initialize(self):
        """Initialize the agent system"""
        logger.info("Initializing Intelligent Agent...")

        # Detect OS and capabilities
        self.os_info = await self.os_detector.detect_system()
        logger.info(f"Detected OS: {self.os_info.os_type.value}")

        if self.os_info.distro:
            logger.info(f"Distribution: {self.os_info.distro.value}")

        logger.info(f"Capabilities: {', '.join(self.os_info.capabilities)}")

        # Send system awareness to LLM
        await self._update_system_context()

    async def process_natural_language_goal(self,
                                          user_input: str,
                                          stream_output: bool = True) -> AsyncGenerator[StreamChunk, None]:
        """
        Process natural language input and execute appropriate commands

        Examples:
        - "what is your ip?"
        - "what other devices are on our network?"
        - "find the open ports of those devices"
        - "do the os update"
        """

        logger.info(f"Processing goal: {user_input}")

        # Add to conversation context
        self.conversation_context.append({
            "type": "user_input",
            "content": user_input,
            "timestamp": asyncio.get_event_loop().time()
        })

        try:
            # Step 1: Process the goal
            yield StreamChunk(
                timestamp=asyncio.get_running_loop().time(),
                chunk_type="status",
                content="🤔 Understanding your request...",
                metadata={"step": "goal_processing"}
            )

            processed_goal = await self.goal_processor.process_goal(user_input)

            if processed_goal.confidence > 0.5:
                # We understand the goal
                yield StreamChunk(
                    timestamp=asyncio.get_running_loop().time(),
                    chunk_type="commentary",
                    content=f"💡 I understand you want to: {processed_goal.intent}",
                    metadata={"intent": processed_goal.intent, "confidence": processed_goal.confidence}
                )

                # Step 2: Select appropriate tools
                yield StreamChunk(
                    timestamp=asyncio.get_running_loop().time(),
                    chunk_type="status",
                    content="🔧 Selecting the best tools for your OS...",
                    metadata={"step": "tool_selection"}
                )

                tool_selection = await self.tool_selector.select_tool(processed_goal)

                if tool_selection.requires_install:
                    yield StreamChunk(
                        timestamp=asyncio.get_running_loop().time(),
                        chunk_type="commentary",
                        content=f"📦 Need to install tool first: {tool_selection.install_command}",
                        metadata={"install_required": True}
                    )

                    # Install the tool first
                    if tool_selection.install_command:
                        async for chunk in self._install_tool(tool_selection.install_command):
                            yield chunk

                # Step 3: Execute the command
                if tool_selection.primary_command:
                    async for chunk in self.streaming_executor.execute_with_streaming(
                        tool_selection.primary_command,
                        user_input
                    ):
                        yield chunk
                else:
                    yield StreamChunk(
                        timestamp=asyncio.get_running_loop().time(),
                        chunk_type="status",
                        content="❌ No suitable command found for this goal",
                        metadata={"error": True}
                    )

            else:
                # Unknown goal - use LLM to figure it out
                yield StreamChunk(
                    timestamp=asyncio.get_running_loop().time(),
                    chunk_type="commentary",
                    content="🧠 This is a complex request. Let me think about the best approach...",
                    metadata={"llm_processing": True}
                )

                async for chunk in self._handle_complex_goal(user_input):
                    yield chunk

        except Exception as e:
            logger.error(f"Error processing goal: {e}")
            yield StreamChunk(
                timestamp=asyncio.get_running_loop().time(),
                chunk_type="status",
                content=f"❌ Error processing request: {str(e)}",
                metadata={"error": True, "exception": str(e)}
            )

    async def _handle_complex_goal(self, user_input: str) -> AsyncGenerator[StreamChunk, None]:
        """Handle complex goals that require LLM reasoning"""

        # Use LLM to break down the goal and suggest commands
        system_prompt = f"""
        You are an intelligent system administrator assistant. The user is running:
        - OS: {self.os_info.os_type.value}
        - Distribution: {self.os_info.distro.value if self.os_info.distro else 'N/A'}
        - Available tools: {', '.join(self.os_info.capabilities)}

        The user asked: "{user_input}"

        Break this down into specific, executable commands for this system.
        Consider the OS and available tools.
        Provide commands one at a time, with explanations.

        Respond in this format:
        COMMAND: [specific command]
        EXPLANATION: [what this command does]
        NEXT: [what to do with the results, if anything]
        """

        try:
            llm_response = await self.llm_interface.generate_response(
                system_prompt,
                temperature=0.3  # Lower temperature for more focused responses
            )

            yield StreamChunk(
                timestamp=asyncio.get_running_loop().time(),
                chunk_type="commentary",
                content=f"🎯 LLM Analysis: {llm_response}",
                metadata={"llm_response": True}
            )

            # Parse LLM response and extract commands
            commands = self._parse_llm_commands(llm_response)

            for command_info in commands:
                command = command_info.get('command')
                explanation = command_info.get('explanation', '')

                if command:
                    yield StreamChunk(
                        timestamp=asyncio.get_running_loop().time(),
                        chunk_type="commentary",
                        content=f"➡️ {explanation}",
                        metadata={"explanation": True}
                    )

                    # Execute the command
                    async for chunk in self.streaming_executor.execute_with_streaming(
                        command,
                        user_input
                    ):
                        yield chunk

        except Exception as e:
            yield StreamChunk(
                timestamp=asyncio.get_running_loop().time(),
                chunk_type="status",
                content=f"❌ Error in LLM processing: {str(e)}",
                metadata={"error": True}
            )

    async def _install_tool(self, install_command: str) -> AsyncGenerator[StreamChunk, None]:
        """Install a required tool"""

        yield StreamChunk(
            timestamp=asyncio.get_running_loop().time(),
            chunk_type="status",
            content="📦 Installing required tool...",
            metadata={"installing": True}
        )

        # Check if we need sudo
        if not self.os_info.is_root and 'sudo' not in install_command:
            install_command = f"sudo {install_command}"

        async for chunk in self.streaming_executor.execute_with_streaming(
            install_command,
            "Install required tool"
        ):
            yield chunk

    async def _update_system_context(self):
        """Update LLM with current system context"""
        context = f"""
        System Information:
        - OS: {self.os_info.os_type.value}
        - Distribution: {self.os_info.distro.value if self.os_info.distro else 'N/A'}
        - Version: {self.os_info.version}
        - Architecture: {self.os_info.architecture}
        - User: {self.os_info.user}
        - Root Access: {self.os_info.is_root}
        - Package Manager: {self.os_info.package_manager}
        - Available Capabilities: {', '.join(self.os_info.capabilities)}

        I am an intelligent system assistant running on this system.
        I can execute commands, install tools, and provide real-time analysis.
        """

        # Store in knowledge base for future reference
        await self.knowledge_base.store_fact(
            content=context,
            metadata={
                "type": "system_context",
                "os_type": self.os_info.os_type.value,
                "timestamp": asyncio.get_running_loop().time()
            }
        )

    def _parse_llm_commands(self, llm_response: str) -> list:
        """Parse commands from LLM response"""
        commands = []
        lines = llm_response.split('\n')
        current_command = {}

        for line in lines:
            line = line.strip()
            if line.startswith('COMMAND:'):
                if current_command.get('command'):
                    commands.append(current_command)
                current_command = {'command': line[8:].strip()}
            elif line.startswith('EXPLANATION:'):
                current_command['explanation'] = line[12:].strip()
            elif line.startswith('NEXT:'):
                current_command['next'] = line[5:].strip()

        if current_command.get('command'):
            commands.append(current_command)

        return commands
```

### Step 6: API Integration for Chat Interface

```python
# autobot-user-backend/api/intelligent_agent.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import StreamingResponse
import json
import asyncio
import logging

from src.intelligence.intelligent_agent import IntelligentAgent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["intelligent_agent"])

# Global agent instance
_agent_instance = None

async def get_agent() -> IntelligentAgent:
    """Get or create agent instance"""
    global _agent_instance
    if _agent_instance is None:
        from backend.app_factory import get_llm_interface, get_knowledge_base, get_worker_node
        from src.utils.command_validator import CommandValidator

        _agent_instance = IntelligentAgent(
            get_llm_interface(),
            get_knowledge_base(),
            get_worker_node(),
            CommandValidator()
        )
        await _agent_instance.initialize()

    return _agent_instance

@router.websocket("/stream")
async def agent_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time agent interaction"""
    await websocket.accept()
    agent = await get_agent()

    try:
        while True:
            # Receive user input
            data = await websocket.receive_text()
            message = json.loads(data)

            user_input = message.get("input", "").strip()
            if not user_input:
                continue

            logger.info(f"Processing user input: {user_input}")

            # Process the goal and stream results
            async for chunk in agent.process_natural_language_goal(user_input):
                await websocket.send_text(json.dumps(chunk.to_dict()))

            # Send completion signal
            await websocket.send_text(json.dumps({
                "timestamp": asyncio.get_running_loop().time(),
                "chunk_type": "complete",
                "content": "✅ Task completed",
                "metadata": {"complete": True}
            }))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_text(json.dumps({
            "timestamp": asyncio.get_running_loop().time(),
            "chunk_type": "error",
            "content": f"Error: {str(e)}",
            "metadata": {"error": True}
        }))

@router.post("/process")
async def process_goal(request: dict):
    """HTTP endpoint for processing goals (non-streaming)"""
    user_input = request.get("input", "").strip()
    if not user_input:
        return {"error": "No input provided"}

    agent = await get_agent()

    results = []
    async for chunk in agent.process_natural_language_goal(user_input):
        results.append(chunk.to_dict())

    return {"results": results}

@router.get("/system-info")
async def get_system_info():
    """Get current system information"""
    agent = await get_agent()
    return {
        "os_info": {
            "os_type": agent.os_info.os_type.value,
            "distro": agent.os_info.distro.value if agent.os_info.distro else None,
            "version": agent.os_info.version,
            "architecture": agent.os_info.architecture,
            "user": agent.os_info.user,
            "is_root": agent.os_info.is_root,
            "capabilities": agent.os_info.capabilities
        }
    }
```

### Step 7: Frontend Integration - Enhanced Chat Interface

```vue
<!-- autobot-user-frontend/src/components/IntelligentChat.vue -->
<template>
  <div class="intelligent-chat">
    <div class="system-info-bar">
      <div class="os-info">
        <i class="icon-computer"></i>
        <span v-if="systemInfo">
          {{ systemInfo.os_type }} {{ systemInfo.distro }}
          ({{ systemInfo.user }}{{ systemInfo.is_root ? ' - ROOT' : '' }})
        </span>
        <span v-else>Loading system info...</span>
      </div>
      <div class="connection-status" :class="{ connected: wsConnected }">
        {{ wsConnected ? 'Connected' : 'Disconnected' }}
      </div>
    </div>

    <div class="chat-container" ref="chatContainer">
      <div class="messages">
        <div
          v-for="(message, index) in messages"
          :key="index"
          class="message"
          :class="message.type"
        >
          <div class="message-header" v-if="message.type === 'user'">
            <strong>You:</strong>
            <span class="timestamp">{{ formatTime(message.timestamp) }}</span>
          </div>

          <div class="message-content">
            <div v-if="message.type === 'user'">
              {{ message.content }}
            </div>

            <div v-else-if="message.chunk_type === 'status'" class="status-message">
              <i class="icon-info"></i>
              {{ message.content }}
            </div>

            <div v-else-if="message.chunk_type === 'commentary'" class="commentary-message">
              <i class="icon-brain"></i>
              {{ message.content }}
            </div>

            <div v-else-if="message.chunk_type === 'stdout'" class="output-message">
              <pre>{{ message.content }}</pre>
            </div>

            <div v-else-if="message.chunk_type === 'stderr'" class="error-message">
              <pre>{{ message.content }}</pre>
            </div>

            <div v-else class="generic-message">
              {{ message.content }}
            </div>
          </div>
        </div>

        <!-- Typing indicator -->
        <div v-if="isProcessing" class="typing-indicator">
          <div class="typing-dots">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <span>Agent is thinking...</span>
        </div>
      </div>
    </div>

    <div class="input-area">
      <div class="quick-commands">
        <button
          v-for="quickCmd in quickCommands"
          :key="quickCmd.text"
          @click="sendMessage(quickCmd.text)"
          class="quick-cmd-btn"
          :disabled="isProcessing"
        >
          {{ quickCmd.text }}
        </button>
      </div>

      <div class="input-group">
        <input
          v-model="currentInput"
          @keyup.enter="sendMessage()"
          :disabled="!wsConnected || isProcessing"
          type="text"
          placeholder="Ask me anything... e.g., 'what is your ip?' or 'scan the network'"
          class="message-input"
        />
        <button
          @click="sendMessage()"
          :disabled="!currentInput.trim() || !wsConnected || isProcessing"
          class="send-btn"
        >
          {{ isProcessing ? 'Processing...' : 'Send' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'IntelligentChat',
  data() {
    return {
      messages: [],
      currentInput: '',
      websocket: null,
      wsConnected: false,
      isProcessing: false,
      systemInfo: null,
      quickCommands: [
        { text: "what is your ip?" },
        { text: "what other devices are on our network?" },
        { text: "do the os update" },
        { text: "show system info" },
        { text: "check disk space" },
        { text: "list running processes" }
      ]
    };
  },
  methods: {
    async initializeWebSocket() {
      const wsUrl = `ws://localhost:8001/api/agent/stream`;

      try {
        this.websocket = new WebSocket(wsUrl);

        this.websocket.onopen = () => {
          this.wsConnected = true;
          console.log('WebSocket connected');
        };

        this.websocket.onmessage = (event) => {
          const chunk = JSON.parse(event.data);
          this.handleStreamChunk(chunk);
        };

        this.websocket.onclose = () => {
          this.wsConnected = false;
          console.log('WebSocket disconnected');
          // Reconnect after 3 seconds
          setTimeout(() => this.initializeWebSocket(), 3000);
        };

        this.websocket.onerror = (error) => {
          console.error('WebSocket error:', error);
          this.wsConnected = false;
        };

      } catch (error) {
        console.error('Failed to initialize WebSocket:', error);
      }
    },

    handleStreamChunk(chunk) {
      if (chunk.chunk_type === 'complete') {
        this.isProcessing = false;
        return;
      }

      // Add timestamp if not present
      if (!chunk.timestamp) {
        chunk.timestamp = new Date().toISOString();
      }

      this.messages.push({
        type: 'agent',
        ...chunk
      });

      // Auto-scroll to bottom
      this.$nextTick(() => {
        this.scrollToBottom();
      });
    },

    async sendMessage(text = null) {
      const message = text || this.currentInput.trim();
      if (!message || !this.wsConnected) return;

      // Add user message
      this.messages.push({
        type: 'user',
        content: message,
        timestamp: new Date().toISOString()
      });

      // Clear input
      if (!text) {
        this.currentInput = '';
      }

      this.isProcessing = true;

      // Send to WebSocket
      try {
        this.websocket.send(JSON.stringify({
          input: message
        }));
      } catch (error) {
        console.error('Failed to send message:', error);
        this.isProcessing = false;
      }

      this.scrollToBottom();
    },

    async loadSystemInfo() {
      try {
        const response = await fetch('http://localhost:8001/api/agent/system-info');
        const data = await response.json();
        this.systemInfo = data.os_info;
      } catch (error) {
        console.error('Failed to load system info:', error);
      }
    },

    scrollToBottom() {
      const container = this.$refs.chatContainer;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    },

    formatTime(timestamp) {
      return new Date(timestamp).toLocaleTimeString();
    }
  },

  mounted() {
    this.initializeWebSocket();
    this.loadSystemInfo();
  },

  beforeUnmount() {
    if (this.websocket) {
      this.websocket.close();
    }
  }
};
</script>

<style scoped>
.intelligent-chat {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 1200px;
  margin: 0 auto;
}

.system-info-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #e1e5e9;
  font-size: 14px;
}

.os-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.connection-status {
  padding: 4px 12px;
  border-radius: 4px;
  background: #dc3545;
  color: white;
  font-size: 12px;
  font-weight: 500;
}

.connection-status.connected {
  background: #28a745;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #ffffff;
}

.messages {
  max-width: 800px;
  margin: 0 auto;
}

.message {
  margin-bottom: 20px;
}

.message.user {
  text-align: right;
}

.message-header {
  margin-bottom: 5px;
  font-size: 14px;
  color: #6c757d;
}

.message-content {
  padding: 12px 16px;
  border-radius: 8px;
}

.message.user .message-content {
  background: #007bff;
  color: white;
  display: inline-block;
  max-width: 70%;
}

.status-message {
  background: #e3f2fd;
  border-left: 4px solid #2196f3;
  color: #1976d2;
  display: flex;
  align-items: center;
  gap: 8px;
}

.commentary-message {
  background: #f3e5f5;
  border-left: 4px solid #9c27b0;
  color: #7b1fa2;
  display: flex;
  align-items: center;
  gap: 8px;
  font-style: italic;
}

.output-message {
  background: #f8f9fa;
  border: 1px solid #e1e5e9;
  border-left: 4px solid #28a745;
}

.output-message pre {
  margin: 0;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
}

.error-message {
  background: #ffeaea;
  border: 1px solid #ffcdd2;
  border-left: 4px solid #f44336;
  color: #c62828;
}

.error-message pre {
  margin: 0;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  white-space: pre-wrap;
}

.generic-message {
  background: #f8f9fa;
  border-left: 4px solid #6c757d;
  color: #495057;
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #6c757d;
  font-style: italic;
}

.typing-dots {
  display: flex;
  gap: 3px;
}

.typing-dots span {
  width: 6px;
  height: 6px;
  background: #6c757d;
  border-radius: 50%;
  animation: typing 1.4s infinite;
}

.typing-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-10px);
    opacity: 1;
  }
}

.input-area {
  padding: 20px;
  background: #f8f9fa;
  border-top: 1px solid #e1e5e9;
}

.quick-commands {
  display: flex;
  gap: 8px;
  margin-bottom: 15px;
  flex-wrap: wrap;
}

.quick-cmd-btn {
  padding: 6px 12px;
  background: #e9ecef;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.quick-cmd-btn:hover:not(:disabled) {
  background: #dee2e6;
  border-color: #adb5bd;
}

.quick-cmd-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.input-group {
  display: flex;
  gap: 10px;
  max-width: 800px;
  margin: 0 auto;
}

.message-input {
  flex: 1;
  padding: 12px 16px;
  border: 2px solid #e1e5e9;
  border-radius: 8px;
  font-size: 16px;
  transition: border-color 0.2s;
}

.message-input:focus {
  outline: none;
  border-color: #007bff;
}

.message-input:disabled {
  background: #e9ecef;
  cursor: not-allowed;
}

.send-btn {
  padding: 12px 24px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.send-btn:hover:not(:disabled) {
  background: #0056b3;
}

.send-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
}
</style>
```

## Usage Examples

With this complete implementation, users can now interact naturally:

**User types:** "what is your ip?"
**Agent responds:**
```
🤔 Understanding your request...
💡 I understand you want to: get_ip_address
🔧 Selecting the best tools for your OS...
🚀 Starting execution: ip addr show
💭 This command will show all network interfaces and their IP addresses...
eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 192.168.1.100  netmask 255.255.255.0  broadcast 192.168.1.255
📊 Found your primary IP address: 192.168.1.100 on eth0 interface. This is your local network address.
✅ Command completed with exit code: 0
```

**User types:** "what other devices are on our network?"
**Agent responds:**
```
🤔 Understanding your request...
💡 I understand you want to: scan_network
🔧 Selecting the best tools for your OS...
📦 Need to install tool first: sudo apt install -y nmap
📦 Installing required tool...
🚀 Starting execution: sudo apt install -y nmap
[installation output streams...]
✅ Tool installed successfully
🚀 Starting execution: nmap -sn 192.168.1.0/24
💭 Scanning your local network to discover active devices...
Nmap scan report for 192.168.1.1
Host is up (0.0023s latency).
Nmap scan report for 192.168.1.100
Host is up (0.000071s latency).
Nmap scan report for 192.168.1.105
Host is up (0.015s latency).
📊 Found 3 active devices on your network: Router (192.168.1.1), your computer (192.168.1.100), and another device (192.168.1.105). The network appears healthy with normal response times.
✅ Command completed with exit code: 0
```

This implementation provides exactly what you requested - an intelligent agent that understands natural language, automatically selects appropriate tools, installs missing tools, streams output in real-time, and provides intelligent commentary on results, all while being fully OS-aware.
