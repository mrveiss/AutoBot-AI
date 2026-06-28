# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
System Command Agent for AutoBot
Handles tool installation, command execution, and system operations with full
terminal streaming
"""

import asyncio
import json
import re
import shlex
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List

from agents.interactive_terminal_agent import InteractiveTerminalAgent
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import (
    config,
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from constants.threshold_constants import LLMDefaults, TimingConstants
from events.bus import PersistStrategy, publish_event
from security.command_patterns import (
    SENSITIVE_REDIRECT_PATHS,
    UNRESTRICTED_ROOT_COMMANDS,
    is_dangerous_command,
    is_persistent_session_command,
)
from security_layer import SecurityLayer
from services.llm_service import get_llm_service

from .base_agent import AgentRequest
from .payloads import AgentStatus, CommandPayload
from .standardized_agent import ActionHandler, StandardizedAgent

# Issue #380: Module-level frozenset for dangerous rm flags
_DANGEROUS_RM_FLAGS: FrozenSet[str] = frozenset({"-r", "-rf", "-f"})

logger = get_logger(__name__)


class SystemCommandAgent(StandardizedAgent):
    """Agent capable of running any system command with safety checks and
    terminal streaming.

    Issue #765: Uses centralized command patterns from security.command_patterns
    Inherits StandardizedAgent for standardized action routing and metrics.
    """

    # List of package managers and their install commands
    PACKAGE_MANAGERS = {
        "apt": {
            "check": "which apt-get",
            "update": "sudo apt-get update",
            "install": "sudo apt-get install -y {package}",
            "search": "apt-cache search {package}",
            "info": "apt-cache show {package}",
        },
        "yum": {
            "check": "which yum",
            "update": "sudo yum check-update",
            "install": "sudo yum install -y {package}",
            "search": "yum search {package}",
            "info": "yum info {package}",
        },
        "dnf": {
            "check": "which dn",
            "update": "sudo dnf check-update",
            "install": "sudo dnf install -y {package}",
            "search": "dnf search {package}",
            "info": "dnf info {package}",
        },
        "pacman": {
            "check": "which pacman",
            "update": "sudo pacman -Sy",
            "install": "sudo pacman -S --noconfirm {package}",
            "search": "pacman -Ss {package}",
            "info": "pacman -Si {package}",
        },
        "brew": {
            "check": "which brew",
            "update": "brew update",
            "install": "brew install {package}",
            "search": "brew search {package}",
            "info": "brew info {package}",
        },
        "pip": {
            "check": "which pip",
            "update": "pip install --upgrade pip",
            "install": "pip install {package}",
            "search": "pip search {package}",
            "info": "pip show {package}",
        },
        "npm": {
            "check": "which npm",
            "update": "npm update -g npm",
            "install": "npm install -g {package}",
            "search": "npm search {package}",
            "info": "npm info {package}",
        },
    }

    # Agent identifier used for SSOT LLM config lookup (mirrors EnhancedSystemCommandsAgent)
    AGENT_ID = "system_commands"

    def __init__(self):
        """Initialize system command agent with security layer and session tracking."""
        super().__init__("system_command")
        self.security_layer = SecurityLayer()
        self.active_sessions: Dict[str, InteractiveTerminalAgent] = {}
        self.command_history: List[Dict[str, Any]] = []

        # LLM interface for command generation (merged from EnhancedSystemCommandsAgent #10571)
        self.llm_interface = get_llm_service()
        try:
            self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
            self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
            self.model_name = get_agent_model_explicit(self.AGENT_ID)
        except Exception:
            self.llm_provider = None
            self.llm_endpoint = None
            self.model_name = None

        # Allowed-command set and dangerous patterns for LLM-generated command validation
        self._allowed_commands = self._init_allowed_commands()
        self._dangerous_patterns = self._init_dangerous_patterns()

        self.register_actions(
            {
                "execute": ActionHandler(
                    handler_method="handle_execute",
                    required_params=["command", "chat_id"],
                    description="Execute a system command with interactive terminal streaming",
                ),
                "install_tool": ActionHandler(
                    handler_method="handle_install_tool",
                    required_params=["tool_info", "chat_id"],
                    description="Install a system tool using the detected package manager",
                ),
                "check_tool": ActionHandler(
                    handler_method="handle_check_tool",
                    required_params=["tool_name"],
                    description="Check whether a tool is installed on the system",
                ),
                "validate_command": ActionHandler(
                    handler_method="handle_validate_command",
                    required_params=["command"],
                    description="Validate command safety before execution",
                ),
                "send_input": ActionHandler(
                    handler_method="handle_send_input",
                    required_params=["chat_id", "user_input"],
                    description="Send input to an active terminal session",
                ),
                "send_signal": ActionHandler(
                    handler_method="handle_send_signal",
                    required_params=["chat_id", "signal_type"],
                    description="Send a signal to an active terminal session",
                ),
                "take_control": ActionHandler(
                    handler_method="handle_take_control",
                    required_params=["chat_id"],
                    description="Transfer terminal session control to the user",
                ),
                "return_control": ActionHandler(
                    handler_method="handle_return_control",
                    required_params=["chat_id"],
                    description="Return terminal session control to the agent",
                ),
                "get_sessions": ActionHandler(
                    handler_method="handle_get_sessions",
                    description="List all active terminal sessions",
                ),
            }
        )

    def _get_system_prompt(self) -> str:
        """Return agent system prompt."""
        return (
            "You are a system command execution agent. "
            "Run validated shell commands safely, manage terminal sessions, "
            "and install tools using the appropriate package manager."
        )

    def get_capabilities(self) -> List[str]:
        """Return list of supported agent capabilities."""
        return [
            "command_execution",
            "tool_installation",
            "package_management",
            "terminal_sessions",
            "command_validation",
            "interactive_terminal",
        ]

    async def handle_execute(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle execute action."""
        command = request.payload["command"]
        chat_id = request.payload["chat_id"]
        description = request.payload.get("description")
        require_confirmation = request.payload.get("require_confirmation", True)
        env = request.payload.get("env")
        cwd = request.payload.get("cwd")
        timeout = request.payload.get("timeout")
        return await self.execute_interactive_command(
            command,
            chat_id,
            description=description,
            require_confirmation=require_confirmation,
            env=env,
            cwd=cwd,
            timeout=timeout,
        )

    async def handle_install_tool(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle install_tool action."""
        tool_info = request.payload["tool_info"]
        chat_id = request.payload["chat_id"]
        return await self.install_tool(tool_info, chat_id)

    async def handle_check_tool(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle check_tool action."""
        tool_name = request.payload["tool_name"]
        return await self.check_tool_installed(tool_name)

    async def handle_validate_command(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle validate_command action."""
        command = request.payload["command"]
        return await self.validate_command_safety(command)

    async def handle_send_input(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle send_input action."""
        chat_id = request.payload["chat_id"]
        user_input = request.payload["user_input"]
        is_password = request.payload.get("is_password", False)
        await self.send_input_to_session(chat_id, user_input, is_password=is_password)
        return {"status": "sent"}

    async def handle_send_signal(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle send_signal action."""
        chat_id = request.payload["chat_id"]
        signal_type = request.payload["signal_type"]
        await self.send_signal_to_session(chat_id, signal_type)
        return {"status": "sent", "signal_type": signal_type}

    async def handle_take_control(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle take_control action."""
        chat_id = request.payload["chat_id"]
        await self.take_control_of_session(chat_id)
        return {"status": "user_control", "chat_id": chat_id}

    async def handle_return_control(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle return_control action."""
        chat_id = request.payload["chat_id"]
        await self.return_control_of_session(chat_id)
        return {"status": "agent_control", "chat_id": chat_id}

    async def handle_get_sessions(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle get_sessions action."""
        sessions = await self.get_active_sessions()
        return {"sessions": sessions}

    async def check_tool_installed(self, tool_name: str) -> Dict[str, Any]:
        """Check if a tool is installed on the system"""
        check_commands = [
            f"which {tool_name}",
            f"command -v {tool_name}",
            f"{tool_name} --version",
            f"{tool_name} -v",
        ]

        for cmd in check_commands:
            try:
                # Create a temporary terminal session for checking
                terminal = InteractiveTerminalAgent(f"check_{tool_name}")
                await terminal.start_session(cmd)
                result = await terminal.wait_for_completion(timeout=5.0)

                if result["exit_code"] == 0:
                    return {
                        "installed": True,
                        "command": cmd,
                        "message": f"{tool_name} is installed",
                    }
            except Exception as e:
                logger.debug("Check command failed: %s, error: %s", cmd, e)
                continue

        return {"installed": False, "message": f"{tool_name} is not installed"}

    async def detect_package_manager(self) -> str | None:
        """Detect which package manager is available on the system"""
        for pm_name, pm_info in self.PACKAGE_MANAGERS.items():
            check_cmd = pm_info["check"]
            try:
                terminal = InteractiveTerminalAgent("detect_pm")
                await terminal.start_session(check_cmd)
                result = await terminal.wait_for_completion(timeout=3.0)

                if result["exit_code"] == 0:
                    logger.info("Detected package manager: %s", pm_name)
                    return pm_name
            except Exception:  # nosec B112 - intentional: skip failing PMs
                continue

        return None

    async def _determine_install_command(self, tool_info: dict, chat_id: str) -> tuple:
        """Determine installation command (Issue #398: extracted)."""
        package_name = tool_info.get("package_name", tool_info.get("name", ""))
        install_method = tool_info.get("install_method", "auto")
        custom_command = tool_info.get("custom_command", "")

        if custom_command:
            return custom_command, None

        if install_method == "auto":
            pm = await self.detect_package_manager()
            if not pm:
                return None, {
                    "status": AgentStatus.ERROR.value,
                    "message": "Could not detect package manager",
                }
            pm_info = self.PACKAGE_MANAGERS[pm]
            if tool_info.get("update_first", True):
                await self.execute_interactive_command(
                    pm_info["update"],
                    chat_id,
                    description=f"Updating {pm} package lists",
                )
            return pm_info["install"].format(package=package_name), None

        pm_info = self.PACKAGE_MANAGERS.get(install_method)
        if not pm_info:
            return None, {
                "status": AgentStatus.ERROR.value,
                "message": f"Unknown install method: {install_method}",
            }
        return pm_info["install"].format(package=package_name), None

    async def _verify_installation(self, tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Verify tool installation success (Issue #398: extracted)."""
        if result["status"] != "success":
            return result
        verify_result = await self.check_tool_installed(tool_name)
        if verify_result["installed"]:
            return {
                "status": AgentStatus.SUCCESS.value,
                "message": f"{tool_name} installed successfully",
                "exit_code": result.get("exit_code", 0),
            }
        return {
            "status": "warning",
            "exit_code": result.get("exit_code", 0),
            "message": f"Installation completed but {tool_name} not found in PATH",
        }

    async def install_tool(self, tool_info: dict, chat_id: str) -> Dict[str, Any]:
        """Install a tool based on instructions (Issue #398: refactored)."""
        tool_name = tool_info.get("name", "")
        check_result = await self.check_tool_installed(tool_name)
        if check_result["installed"]:
            return {
                "status": "already_installed",
                "message": f"{tool_name} is already installed",
            }

        install_command, error = await self._determine_install_command(tool_info, chat_id)
        if error:
            return error

        result = await self.execute_interactive_command(
            install_command,
            chat_id,
            description=f"Installing {tool_name}",
            require_confirmation=False,
        )
        return await self._verify_installation(tool_name, result)

    async def _publish_execution_event(
        self,
        chat_id: str,
        command: str,
        status: str,
        description: str = None,
        result: dict = None,
    ) -> None:
        """Publish command execution event (Issue #398: extracted)."""
        event_data = {
            "chat_id": chat_id,
            "command": command,
            "status": status,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        if status == "started":
            event_data["description"] = description or f"Executing: {command}"
        elif result:
            event_data["exit_code"] = result["exit_code"]
            event_data["duration"] = result["duration"]
        await publish_event("global", "command_execution", event_data, persist=PersistStrategy.NONE)

    def _build_execution_result(self, result: dict) -> Dict[str, Any]:
        """Build execution result dict (Issue #398: extracted)."""
        exit_code = result["exit_code"]
        return {
            "status": (AgentStatus.SUCCESS.value if exit_code == 0 else AgentStatus.ERROR.value),
            "exit_code": exit_code,
            "duration": result["duration"],
            "output_lines": result["line_count"],
            "message": (
                "Command completed successfully" if exit_code == 0 else f"Command failed with exit code {exit_code}"
            ),
        }

    def _get_or_create_terminal(self, chat_id: str) -> tuple:
        """Get or create terminal session (Issue #398: extracted)."""
        session_id = f"{chat_id}_terminal"
        if session_id in self.active_sessions:
            return self.active_sessions[session_id], session_id
        terminal = InteractiveTerminalAgent(chat_id)
        self.active_sessions[session_id] = terminal
        return terminal, session_id

    async def execute_interactive_command(
        self,
        command: str,
        chat_id: str,
        description: str = None,
        require_confirmation: bool = True,
        env: Dict[str, str] = None,
        cwd: str = None,
        timeout: float | None = None,
    ) -> Dict[str, Any]:
        """Execute command with terminal interaction (Issue #398: refactored)."""
        if require_confirmation and self._is_dangerous_command(command):
            if not await self._request_user_confirmation(command, chat_id):
                return {"status": "cancelled", "message": "Command cancelled by user"}

        self._log_command(command, chat_id)
        terminal, session_id = self._get_or_create_terminal(chat_id)

        try:
            await self._publish_execution_event(chat_id, command, "started", description)
            await terminal.start_session(command, env=env, cwd=cwd)
            result = await terminal.wait_for_completion(timeout=timeout)
            await self._publish_execution_event(chat_id, command, "completed", result=result)
            return self._build_execution_result(result)
        except Exception as e:
            logger.error("Error executing command: %s", e)
            return {
                "status": AgentStatus.ERROR.value,
                "error": "Command execution failed",
                "message": "Command execution failed",
            }
        finally:
            if session_id in self.active_sessions and not self._is_persistent_session(command):
                del self.active_sessions[session_id]

    async def execute_command_with_output(
        self, command: str, chat_id: str, stream_output: bool = True
    ) -> Dict[str, Any]:
        """Execute command and return output (simpler non-interactive version)"""
        # 5 minute timeout for non-interactive commands
        return await self.execute_interactive_command(
            command,
            chat_id,
            require_confirmation=False,
            timeout=TimingConstants.VERY_LONG_TIMEOUT,
        )

    def _is_dangerous_command(self, command: str) -> bool:
        """Check if command is potentially dangerous.

        Issue #765: Delegates to centralized is_dangerous_command function.
        """
        is_dangerous, _ = is_dangerous_command(command)
        return is_dangerous

    def _is_persistent_session(self, command: str) -> bool:
        """Check if command starts a persistent session.

        Issue #765: Delegates to centralized is_persistent_session_command function.
        """
        return is_persistent_session_command(command)

    async def _request_user_confirmation(self, command: str, chat_id: str) -> bool:
        """Request user confirmation for dangerous commands"""
        await publish_event(
            "global",
            "command_confirmation",
            {
                "chat_id": chat_id,
                "command": command,
                "warning": "⚠️ This command may be dangerous. Please confirm execution.",
                "requires_confirmation": True,
            },
            persist=PersistStrategy.NONE,
        )

        # Wait for user response (this would be handled by the frontend)
        # For now, we'll implement a timeout-based approach
        confirmation_future = asyncio.Future()

        # This would be stored in a shared state that the frontend can access
        # For now, we'll use a timeout-based approach

        try:
            # Wait for confirmation with timeout
            confirmed = await asyncio.wait_for(confirmation_future, timeout=TimingConstants.SHORT_TIMEOUT)
            return confirmed
        except asyncio.TimeoutError:
            return False  # Default to not executing dangerous commands

    def _log_command(self, command: str, chat_id: str):
        """Log command execution for audit trail"""
        log_entry = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "chat_id": chat_id,
            "command": command,
            "user": config.user,
        }
        self.command_history.append(log_entry)

        # Also log to security layer
        self.security_layer.audit_log(
            "command_execution",
            "user",
            "initiated",
            {"command": command, "chat_id": chat_id},
        )

    async def validate_command_safety(self, command: str) -> Dict[str, Any]:
        """Validate command safety before execution.

        Issue #765: Uses centralized patterns from security.command_patterns.
        """
        issues = []
        risk_level = "low"

        # Check for dangerous patterns using centralized function
        is_dangerous, reason = is_dangerous_command(command)
        if is_dangerous:
            issues.append(reason or "Command contains potentially dangerous operations")
            risk_level = "high"

        # Check for sudo without specific command (Issue #765: use centralized constant)
        if command.strip() in UNRESTRICTED_ROOT_COMMANDS:
            issues.append("Unrestricted root access requested")
            risk_level = "high"

        # Check for output redirection using centralized paths (Issue #765)
        if ">" in command and any(path in command for path in SENSITIVE_REDIRECT_PATHS):
            issues.append("Output redirection to system directory detected")
            risk_level = "high"

        # Check for recursive operations on root
        if "-r" in command and "/" in command and command.count("/") == 1:
            issues.append("Recursive operation on root or near-root directory")
            risk_level = "high"

        return {
            "safe": risk_level != "high",
            "risk_level": risk_level,
            "issues": issues,
            "recommendation": ("Proceed with caution" if issues else "Command appears safe"),
        }

    async def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get list of active terminal sessions"""
        sessions = []
        for session_id, terminal in self.active_sessions.items():
            sessions.append(
                {
                    "session_id": session_id,
                    "chat_id": terminal.chat_id,
                    "active": terminal.session_active,
                    "mode": terminal.input_mode,
                }
            )
        return sessions

    async def send_input_to_session(self, chat_id: str, user_input: str, is_password: bool = False):
        """Send input to an active terminal session"""
        session_id = f"{chat_id}_terminal"
        if session_id in self.active_sessions:
            terminal = self.active_sessions[session_id]
            await terminal.send_input(user_input, is_password=is_password)
        else:
            raise ValueError(f"No active terminal session for chat {chat_id}")

    async def take_control_of_session(self, chat_id: str):
        """Allow user to take control of terminal session"""
        session_id = f"{chat_id}_terminal"
        if session_id in self.active_sessions:
            terminal = self.active_sessions[session_id]
            await terminal.take_control()
        else:
            raise ValueError(f"No active terminal session for chat {chat_id}")

    async def return_control_of_session(self, chat_id: str):
        """Return control of terminal session to agent"""
        session_id = f"{chat_id}_terminal"
        if session_id in self.active_sessions:
            terminal = self.active_sessions[session_id]
            await terminal.return_control()
        else:
            raise ValueError(f"No active terminal session for chat {chat_id}")

    async def send_signal_to_session(self, chat_id: str, signal_type: str):
        """Send signal to terminal session (interrupt, quit, etc)"""
        session_id = f"{chat_id}_terminal"
        if session_id in self.active_sessions:
            terminal = self.active_sessions[session_id]
            await terminal.send_signal(signal_type)
        else:
            raise ValueError(f"No active terminal session for chat {chat_id}")

    # =========================================================================
    # LLM command-generation methods (merged from EnhancedSystemCommandsAgent #10571)
    # =========================================================================

    def _init_allowed_commands(self) -> set:
        """Initialize allowed command set for LLM-generated command validation."""
        return (
            {"ls", "dir", "pwd", "cd", "cat", "head", "tail", "grep", "find"}
            | {
                "ps",
                "top",
                "htop",
                "df",
                "du",
                "free",
                "lscpu",
                "lsblk",
                "uname",
                "whoami",
                "which",
                "whereis",
                "file",
                "stat",
            }
            | {"ifconfig", "ip", "netstat", "ss", "ping", "curl", "wget"}
            | {"systemctl", "service", "journalctl", "dmesg"}
            | {"chmod", "chown", "mkdir", "rmdir", "cp", "mv", "touch", "ln", "tar", "gzip", "gunzip", "zip", "unzip"}
            | {"sort", "uniq", "wc", "awk", "sed", "cut"}
        )

    def _init_dangerous_patterns(self) -> list:
        """Initialize dangerous command pattern list for LLM-generated command validation."""
        return [
            r"rm\s+-rf\s+/",
            r"rm\s+-rf\s+\*",
            r":(){ :|:& };:",
            r"dd\s+.*of=/dev/",
            r"mkfs",
            r"fdisk",
            r"cfdisk",
            r"iptables\s+-F",
            r"ufw\s+disable",
            r"firewall-cmd",
            r"passwd",
            r"usermod",
            r"userdel",
            r"groupdel",
            r"chmod\s+777",
            r"chmod\s+-R\s+777",
            r"curl.*\|\s*bash",
            r"wget.*\|\s*sh",
            r"sudo\s+su\s*-",
            r"su\s+-",
        ]

    def _get_system_commands_prompt(self) -> str:
        """Security-focused system prompt for LLM command generation."""
        return (
            "You are a system command generation assistant focused on security and safety.\n\n"
            "CRITICAL SECURITY RULES:\n"
            "1. NEVER generate commands that could harm the system\n"
            "2. AVOID commands that modify system files, users, or permissions\n"
            "3. PREFER read-only commands when possible\n"
            "4. Always explain what the command does\n"
            "5. If a request is dangerous, suggest a safer alternative\n\n"
            "RESPONSE FORMAT:\n"
            "Generate responses in this exact JSON format:\n"
            '{"command": "...", "explanation": "...", "safety_level": "safe/caution/dangerous", '
            '"alternative": "..."}'
        )

    def _build_command_messages(self, request: str, context: Dict[str, Any] | None) -> List[Dict[str, str]]:
        """Build LLM messages for command generation."""
        system_prompt = self._get_system_commands_prompt()
        if context:
            parts = []
            if "os_info" in context:
                oi = context["os_info"]
                if "name" in oi:
                    parts.append(f"OS: {oi['name']}")
                if "version" in oi:
                    parts.append(f"Version: {oi['version']}")
            if "current_directory" in context:
                parts.append(f"Current Directory: {context['current_directory']}")
            if "user" in context:
                parts.append(f"User: {context['user']}")
            if parts:
                system_prompt = f"{system_prompt}\n\nContext: {' | '.join(parts)}"
        return [{"role": "system", "content": system_prompt}, {"role": "user", "content": request}]

    def _extract_command_from_text(self, text: str) -> str:
        """Extract a command from unstructured LLM text response."""
        for pattern in [
            r"```(?:bash|sh|shell)?\n(.*?)\n```",
            r"`([^`]+)`",
            r"^([\w\-]+(?:\s+[\w\-\.\/\=]+)*)",
        ]:
            match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
            if match:
                cmd = match.group(1).strip()
                if cmd and not cmd.startswith("#"):
                    return cmd
        return text.strip()

    def _extract_response_content(self, response: Any) -> str:
        """Extract text content from an LLM response object."""
        try:
            if hasattr(response, "content") and not isinstance(response, dict):
                content = getattr(response, "content", None)
                if content and isinstance(content, str):
                    return content.strip()
            if isinstance(response, dict):
                if "message" in response and isinstance(response["message"], dict):
                    c = response["message"].get("content")
                    if c:
                        return c.strip()
                if "choices" in response and response["choices"]:
                    c = response["choices"][0].get("message", {}).get("content")
                    if c:
                        return c.strip()
                if "content" in response:
                    return response["content"].strip()
            if isinstance(response, str):
                return response.strip()
            return str(response)
        except Exception as exc:
            logger.error("Error extracting response content: %s", exc)
            return "Error extracting command response"

    def _extract_and_validate_command(self, response: Any) -> Dict[str, Any]:
        """Parse LLM response into a structured command dict."""
        try:
            content = self._extract_response_content(response)
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "command" in parsed:
                    return {
                        "command": parsed.get("command", "").strip(),
                        "explanation": parsed.get("explanation", "No explanation provided"),
                        "safety_level": parsed.get("safety_level", "unknown"),
                        "alternative": parsed.get("alternative", ""),
                        "is_structured": True,
                    }
            except json.JSONDecodeError as exc:
                logger.debug("JSON decode failed, using fallback extraction: %s", exc)
            return {
                "command": self._extract_command_from_text(content),
                "explanation": content,
                "safety_level": "unknown",
                "alternative": "",
                "is_structured": False,
            }
        except Exception as exc:
            logger.error("Error extracting command: %s", exc)
            return {
                "command": "",
                "explanation": f"Failed to extract command: {exc}",
                "safety_level": "dangerous",
                "alternative": "",
                "is_structured": False,
            }

    def _llm_security_validate_command(self, command: str) -> Dict[str, Any]:
        """Validate a LLM-generated command against known dangerous patterns and allowed list."""
        if not command:
            return {"is_safe": False, "security_warning": "Empty command"}
        for pattern in self._dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return {
                    "is_safe": False,
                    "security_warning": f"Dangerous pattern: {pattern}",
                    "recommended_action": "reject",
                }
        try:
            parts = shlex.split(command)
            if not parts:
                return {"is_safe": False, "security_warning": "Unable to parse command"}
            main_cmd = parts[0].split("/")[-1]
            if main_cmd not in self._allowed_commands:
                return {
                    "is_safe": False,
                    "security_warning": f"Command '{main_cmd}' not in allowed list",
                    "recommended_action": "review_manually",
                }
            if main_cmd == "rm" and any(f in parts for f in _DANGEROUS_RM_FLAGS):
                return {"is_safe": False, "security_warning": "rm with dangerous flags", "recommended_action": "reject"}
            return {"is_safe": True, "security_warning": None, "main_command": main_cmd}
        except Exception as exc:
            return {
                "is_safe": False,
                "security_warning": f"Failed to parse command: {exc}",
                "recommended_action": "reject",
            }

    def _build_command_payload(self, command_info: Dict[str, Any]) -> Dict[str, Any]:
        """Build a typed CommandPayload dict from LLM command info."""
        status = AgentStatus.SUCCESS if command_info.get("is_safe", False) else AgentStatus.WARNING
        return CommandPayload(
            status=status,
            agent_type="system_commands",
            model_used=self.model_name,
            command=command_info.get("command", ""),
            explanation=command_info.get("explanation", ""),
            is_safe=command_info.get("is_safe", False),
            security_concerns=command_info.get("security_concerns", []),
            suggested_alternatives=command_info.get("suggested_alternatives", []),
            metadata={"agent": "SystemCommandAgent", "security_checked": True, "validation_level": "strict"},
            **{
                k: v
                for k, v in command_info.items()
                if k not in {"command", "explanation", "is_safe", "security_concerns", "suggested_alternatives"}
            },
        ).model_dump()

    async def process_command_request(self, request: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Generate and validate a system command via LLM (merged from EnhancedSystemCommandsAgent #10571)."""
        try:
            logger.info("SystemCommandAgent LLM generation: %s...", request[:50])
            messages = self._build_command_messages(request, context)
            response = await self.llm_interface.chat(
                messages=messages,
                llm_type="system_commands",
                temperature=0.3,
                max_tokens=LLMDefaults.CONCISE_MAX_TOKENS,
                top_p=0.8,
            )
            command_info = self._extract_and_validate_command(response)
            command_info.update(self._llm_security_validate_command(command_info.get("command", "")))
            return self._build_command_payload(command_info)
        except Exception as exc:
            logger.error("SystemCommandAgent LLM generation error: %s", exc)
            return {
                "status": AgentStatus.ERROR.value,
                "command": "",
                "explanation": "Failed to process command request",
                "is_safe": False,
                "error": str(exc),
                "agent_type": "system_commands",
                "model_used": self.model_name,
            }

    def is_system_command_request(self, message: str) -> bool:
        """Return True if the message looks like a system command request."""
        patterns = [
            "run",
            "execute",
            "command",
            "shell",
            "bash",
            "terminal",
            "system",
            "list files",
            "show processes",
            "check disk",
            "memory usage",
            "network",
            "ifconfig",
            "ps",
            "ls",
            "df",
            "free",
            "top",
            "netstat",
            "ip addr",
            "system info",
            "os info",
            "uptime",
            "users",
            "who",
            "w",
        ]
        msg_lower = message.lower()
        return any(p in msg_lower for p in patterns)


# Singleton accessor — keep the name used by the MCP registry and other callers
get_system_command_agent = lazy_singleton(SystemCommandAgent)

# Alias for backward compatibility with any imports of get_enhanced_system_commands_agent
get_enhanced_system_commands_agent = get_system_command_agent
