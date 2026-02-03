# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Command Agent for AutoBot
Handles tool installation, command execution, and system operations with full
terminal streaming
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.interactive_terminal_agent import InteractiveTerminalAgent
from src.constants.threshold_constants import TimingConstants
from src.event_manager import event_manager
from src.security.command_patterns import (
    SENSITIVE_REDIRECT_PATHS,
    UNRESTRICTED_ROOT_COMMANDS,
    is_dangerous_command,
    is_persistent_session_command,
)
from src.security_layer import SecurityLayer

logger = logging.getLogger(__name__)


class SystemCommandAgent:
    """Agent capable of running any system command with safety checks and
    terminal streaming.

    Issue #765: Uses centralized command patterns from src.security.command_patterns
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

    def __init__(self):
        """Initialize system command agent with security layer and session tracking."""
        self.security_layer = SecurityLayer()
        self.active_sessions: Dict[str, InteractiveTerminalAgent] = {}
        self.command_history: List[Dict[str, Any]] = []

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

    async def detect_package_manager(self) -> Optional[str]:
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
                    "status": "error",
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
                "status": "error",
                "message": f"Unknown install method: {install_method}",
            }
        return pm_info["install"].format(package=package_name), None

    async def _verify_installation(
        self, tool_name: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify tool installation success (Issue #398: extracted)."""
        if result["status"] != "success":
            return result
        verify_result = await self.check_tool_installed(tool_name)
        if verify_result["installed"]:
            return {
                "status": "success",
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

        install_command, error = await self._determine_install_command(
            tool_info, chat_id
        )
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
            "timestamp": datetime.now().isoformat(),
        }
        if status == "started":
            event_data["description"] = description or f"Executing: {command}"
        elif result:
            event_data["exit_code"] = result["exit_code"]
            event_data["duration"] = result["duration"]
        await event_manager.publish("command_execution", event_data)

    def _build_execution_result(self, result: dict) -> Dict[str, Any]:
        """Build execution result dict (Issue #398: extracted)."""
        exit_code = result["exit_code"]
        return {
            "status": "success" if exit_code == 0 else "error",
            "exit_code": exit_code,
            "duration": result["duration"],
            "output_lines": result["line_count"],
            "message": "Command completed successfully"
            if exit_code == 0
            else f"Command failed with exit code {exit_code}",
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
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execute command with terminal interaction (Issue #398: refactored)."""
        if require_confirmation and self._is_dangerous_command(command):
            if not await self._request_user_confirmation(command, chat_id):
                return {"status": "cancelled", "message": "Command cancelled by user"}

        self._log_command(command, chat_id)
        terminal, session_id = self._get_or_create_terminal(chat_id)

        try:
            await self._publish_execution_event(
                chat_id, command, "started", description
            )
            await terminal.start_session(command, env=env, cwd=cwd)
            result = await terminal.wait_for_completion(timeout=timeout)
            await self._publish_execution_event(
                chat_id, command, "completed", result=result
            )
            return self._build_execution_result(result)
        except Exception as e:
            logger.error("Error executing command: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "message": f"Command execution failed: {e}",
            }
        finally:
            if session_id in self.active_sessions and not self._is_persistent_session(
                command
            ):
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
        await event_manager.publish(
            "command_confirmation",
            {
                "chat_id": chat_id,
                "command": command,
                "warning": "⚠️ This command may be dangerous. Please confirm execution.",
                "requires_confirmation": True,
            },
        )

        # Wait for user response (this would be handled by the frontend)
        # For now, we'll implement a timeout-based approach
        confirmation_future = asyncio.Future()

        # This would be stored in a shared state that the frontend can access
        # For now, we'll use a timeout-based approach

        try:
            # Wait for confirmation with timeout
            confirmed = await asyncio.wait_for(
                confirmation_future, timeout=TimingConstants.SHORT_TIMEOUT
            )
            return confirmed
        except asyncio.TimeoutError:
            return False  # Default to not executing dangerous commands

    def _log_command(self, command: str, chat_id: str):
        """Log command execution for audit trail"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "chat_id": chat_id,
            "command": command,
            "user": os.getenv("USER", "unknown"),
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

        Issue #765: Uses centralized patterns from src.security.command_patterns.
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
            "recommendation": (
                "Proceed with caution" if issues else "Command appears safe"
            ),
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

    async def send_input_to_session(
        self, chat_id: str, user_input: str, is_password: bool = False
    ):
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
