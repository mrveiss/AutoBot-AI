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
from src.constants.network_constants import NetworkConstants
from src.event_manager import event_manager
from src.security_layer import SecurityLayer

logger = logging.getLogger(__name__)


class SystemCommandAgent:
    """Agent capable of running any system command with safety checks and
    terminal streaming"""

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

    # Dangerous commands that require confirmation
    DANGEROUS_PATTERNS = [
        "rm -rf /",
        "rm -rf /*",
        "dd if=/dev/zero",
        "mkfs",
        "format",
        "> /dev/sda",
        "fork bomb",
        ":(){ :|:& };:",
        "chmod -R 777 /",
        "chown -R",
        "shutdown",
        "reboot",
        "init 0",
        "systemctl poweroff",
    ]

    def __init__(self):
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
                logger.debug(f"Check command failed: {cmd}, error: {e}")
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
                    logger.info(f"Detected package manager: {pm_name}")
                    return pm_name
            except Exception:
                continue

        return None

    async def install_tool(self, tool_info: dict, chat_id: str) -> Dict[str, Any]:
        """Install a tool based on instructions from KB"""
        tool_name = tool_info.get("name", "")
        package_name = tool_info.get("package_name", tool_name)
        install_method = tool_info.get("install_method", "auto")
        custom_command = tool_info.get("custom_command", "")

        # Check if already installed
        check_result = await self.check_tool_installed(tool_name)
        if check_result["installed"]:
            return {
                "status": "already_installed",
                "message": f"{tool_name} is already installed",
            }

        # Determine installation command
        if custom_command:
            install_command = custom_command
        elif install_method == "auto":
            # Detect package manager
            pm = await self.detect_package_manager()
            if not pm:
                return {
                    "status": "error",
                    "message": "Could not detect package manager",
                }

            pm_info = self.PACKAGE_MANAGERS[pm]

            # Update package manager first (optional)
            if tool_info.get("update_first", True):
                update_cmd = pm_info["update"]
                await self.execute_interactive_command(
                    update_cmd, chat_id, description=f"Updating {pm} package lists"
                )

            # Install the package
            install_command = pm_info["install"].format(package=package_name)
        else:
            # Use specific package manager
            pm_info = self.PACKAGE_MANAGERS.get(install_method)
            if not pm_info:
                return {
                    "status": "error",
                    "message": f"Unknown install method: {install_method}",
                }
            install_command = pm_info["install"].format(package=package_name)

        # Execute installation
        result = await self.execute_interactive_command(
            install_command,
            chat_id,
            description=f"Installing {tool_name}",
            require_confirmation=False,  # User already approved installation
        )

        # Verify installation
        if result["status"] == "success":
            verify_result = await self.check_tool_installed(tool_name)
            if verify_result["installed"]:
                return {
                    "status": "success",
                    "message": f"{tool_name} installed successfully",
                    "exit_code": result.get("exit_code", 0),
                }
            else:
                return {
                    "status": "warning",
                    "message": (
                        f"Installation completed but {tool_name} not found in PATH"
                    ),
                    "exit_code": result.get("exit_code", 0),
                }
        else:
            return result

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
        """Execute command with full terminal interaction"""

        # Safety check
        if require_confirmation and self._is_dangerous_command(command):
            confirmed = await self._request_user_confirmation(command, chat_id)
            if not confirmed:
                return {"status": "cancelled", "message": "Command cancelled by user"}

        # Log command execution
        self._log_command(command, chat_id)

        # Create or reuse terminal session
        session_id = f"{chat_id}_terminal"
        if session_id in self.active_sessions:
            terminal = self.active_sessions[session_id]
        else:
            terminal = InteractiveTerminalAgent(chat_id)
            self.active_sessions[session_id] = terminal

        try:
            # Notify start of execution
            await event_manager.publish(
                "command_execution",
                {
                    "chat_id": chat_id,
                    "command": command,
                    "description": description or f"Executing: {command}",
                    "status": "started",
                    "timestamp": datetime.now().isoformat(),
                },
            )

            # Start command execution
            await terminal.start_session(command, env=env, cwd=cwd)

            # Wait for completion or timeout
            result = await terminal.wait_for_completion(timeout=timeout)

            # Notify completion
            await event_manager.publish(
                "command_execution",
                {
                    "chat_id": chat_id,
                    "command": command,
                    "status": "completed",
                    "exit_code": result["exit_code"],
                    "duration": result["duration"],
                    "timestamp": datetime.now().isoformat(),
                },
            )

            return {
                "status": "success" if result["exit_code"] == 0 else "error",
                "exit_code": result["exit_code"],
                "duration": result["duration"],
                "output_lines": result["line_count"],
                "message": (
                    "Command completed successfully"
                    if result["exit_code"] == 0
                    else f"Command failed with exit code {result['exit_code']}"
                ),
            }

        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"Command execution failed: {str(e)}",
            }
        finally:
            # Clean up session if it's a one-off command
            if session_id in self.active_sessions and not self._is_persistent_session(
                command
            ):
                del self.active_sessions[session_id]

    async def execute_command_with_output(
        self, command: str, chat_id: str, stream_output: bool = True
    ) -> Dict[str, Any]:
        """Execute command and return output (simpler non-interactive version)"""
        return await self.execute_interactive_command(
            command,
            chat_id,
            require_confirmation=False,
            timeout=300,  # 5 minute timeout for non-interactive commands
        )

    def _is_dangerous_command(self, command: str) -> bool:
        """Check if command is potentially dangerous"""
        command_lower = command.lower()
        return any(pattern in command_lower for pattern in self.DANGEROUS_PATTERNS)

    def _is_persistent_session(self, command: str) -> bool:
        """Check if command starts a persistent session (like ssh, screen, etc)"""
        persistent_commands = ["ssh", "screen", "tmux", "docker exec", "kubectl exec"]
        return any(command.startswith(cmd) for cmd in persistent_commands)

    async def _request_user_confirmation(self, command: str, chat_id: str) -> bool:
        """Request user confirmation for dangerous commands"""
        await event_manager.publish(
            "command_confirmation",
            {
                "chat_id": chat_id,
                "command": command,
                "warning": (
                    "⚠️ This command may be dangerous. Please confirm execution."
                ),
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
            confirmed = await asyncio.wait_for(confirmation_future, timeout=30.0)
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
        """Validate command safety before execution"""
        issues = []
        risk_level = "low"

        # Check for dangerous patterns
        if self._is_dangerous_command(command):
            issues.append("Command contains potentially dangerous operations")
            risk_level = "high"

        # Check for sudo without specific command
        if command.strip() == "sudo su" or command.strip() == "sudo -i":
            issues.append("Unrestricted root access requested")
            risk_level = "high"

        # Check for output redirection that might overwrite important files
        dangerous_paths = ["/etc/", "/boot/", "/usr/", "/bin/"]
        if ">" in command and any(path in command for path in dangerous_paths):
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
