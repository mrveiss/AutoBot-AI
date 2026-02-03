#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Elevation Wrapper
Provides secure sudo command execution with GUI elevation dialogs
"""

import asyncio
import logging
import re
import subprocess
from typing import Dict, Tuple


logger = logging.getLogger(__name__)

# Pattern to detect sudo commands
SUDO_PATTERN = re.compile(r"^\s*sudo\s+(.+)$", re.IGNORECASE)

# Commands that require immediate elevation
ELEVATION_REQUIRED_COMMANDS = [
    "apt",
    "apt-get",
    "yum",
    'dn", "zypper',
    "pacman",
    "systemctl",
    "service",
    "ufw",
    "iptables",
    "usermod",
    "groupmod",
    "passwd",
    "chown",
    "chmod",
    "mount",
    "umount",
    "fdisk",
    "parted",
]


class ElevationWrapper:
    """Handles command elevation through GUI dialogs instead of terminal prompts"""

    def __init__(self, elevation_client=None):
        """Initialize elevation wrapper with optional client and session management."""
        self.elevation_client = elevation_client
        self.active_session = None
        self.session_commands = {}

    async def execute_command(
        self,
        command: str,
        operation: str = None,
        reason: str = None,
        risk_level: str = "MEDIUM",
    ) -> Dict:
        """Execute a command, requesting elevation if needed"""

        # Check if command requires sudo
        needs_elevation, clean_command = self._check_elevation_needed(command)

        if not needs_elevation:
            # Execute normally
            return await self._execute_normal(command)

        # Check if we have an active session
        if self.active_session and self._is_session_valid():
            # Use existing session
            return await self._execute_elevated(clean_command, self.active_session)

        # Request elevation through GUI
        if not self.elevation_client:
            logger.error("No elevation client configured - cannot request elevation")
            return {
                "success": False,
                "error": "Elevation required but no GUI client available",
                "needs_elevation": True,
            }

        # Prepare elevation request
        if not operation:
            operation = "Execute system command"
        if not reason:
            reason = f"This command requires administrator privileges: {clean_command[:50]}..."

        try:
            # Request elevation
            elevation_result = await self.elevation_client.request_elevation(
                operation=operation,
                command=clean_command,
                reason=reason,
                risk_level=risk_level,
            )

            if elevation_result.get("approved"):
                self.active_session = elevation_result.get("session_token")
                return await self._execute_elevated(clean_command, self.active_session)
            else:
                return {
                    "success": False,
                    "error": "Elevation request denied by user",
                    "cancelled": True,
                }

        except Exception as e:
            logger.error("Elevation request failed: %s", e)
            return {
                "success": False,
                "error": f"Failed to request elevation: {str(e)}",
                "needs_elevation": True,
            }

    def _check_elevation_needed(self, command: str) -> Tuple[bool, str]:
        """Check if command needs elevation and extract clean command"""

        # Check for explicit sudo
        sudo_match = SUDO_PATTERN.match(command)
        if sudo_match:
            return True, sudo_match.group(1).strip()

        # Check for commands that typically need elevation
        command_parts = command.strip().split()
        if command_parts:
            base_command = command_parts[0]
            if base_command in ELEVATION_REQUIRED_COMMANDS:
                return True, command

        return False, command

    def _is_session_valid(self) -> bool:
        """Check if current elevation session is still valid"""
        if not self.active_session:
            return False

        # In real implementation, check session expiry
        # For now, assume sessions are valid for 15 minutes
        return True

    async def _execute_normal(self, command: str) -> Dict:
        """Execute command without elevation"""
        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            return {
                "success": process.returncode == 0,
                "output": stdout.decode(),
                "error": stderr.decode(),
                "return_code": process.returncode,
            }

        except Exception as e:
            return {"success": False, "error": str(e), "return_code": -1}

    async def _execute_elevated(self, command: str, session_token: str) -> Dict:
        """Execute command with elevation using session token"""

        # In production, this would use the elevation API
        # For now, we'll simulate the execution
        try:
            # Call elevation API to execute command
            if self.elevation_client:
                result = await self.elevation_client.execute_elevated_command(
                    command, session_token
                )
                return result
            else:
                # Fallback to direct sudo (should not happen in production)
                return await self._execute_normal(f"sudo {command}")

        except Exception as e:
            logger.error("Elevated execution failed: %s", e)
            return {"success": False, "error": str(e), "return_code": -1}

    def clear_session(self):
        """Clear the current elevation session"""
        self.active_session = None
        self.session_commands.clear()


# Global instance
elevation_wrapper = ElevationWrapper()


def wrap_sudo_command(command: str) -> str:
    """Convert sudo command to elevation-aware command"""
    sudo_match = SUDO_PATTERN.match(command)
    if sudo_match:
        return sudo_match.group(1).strip()
    return command


async def execute_with_elevation(command: str, **kwargs):
    """Convenience function to execute command with elevation if needed"""
    return await elevation_wrapper.execute_command(command, **kwargs)


# Monkey-patch subprocess to intercept sudo calls
_original_popen = subprocess.Popen


def _elevation_aware_popen(cmd, *args, **kwargs):
    """Intercept subprocess calls and handle sudo"""
    if isinstance(cmd, str) and "sudo" in cmd:
        logger.warning("Direct sudo call intercepted: %s", cmd)
        # In production, this should trigger elevation dialog
        # For now, pass through with warning
    elif isinstance(cmd, list) and "sudo" in cmd:
        logger.warning("Direct sudo call intercepted: %s", ' '.join(cmd))

    return _original_popen(cmd, *args, **kwargs)


# Enable interception (commented out by default)
# subprocess.Popen = _elevation_aware_popen
