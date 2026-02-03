# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Command Validation and Sanitization Utility

This module provides secure command execution by implementing whitelisting,
sanitization, and safe execution patterns to prevent shell injection attacks
from LLM-generated commands.

Security Features:
- Whitelist-based command validation
- Shell injection pattern detection
- Safe argument parsing and validation
- shell=False execution where possible
- Comprehensive audit logging
"""

import logging
import re
import shlex
from dataclasses import dataclass
from typing import Dict, List, Pattern, Union

# Issue #380: Pre-compiled dangerous patterns for command validation
_DANGEROUS_PATTERNS: List[Pattern] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"rm\s+-r",
        r"rm\s.*/",
        r";\s*rm",
        r"&&\s*rm",
        r"\|\s*rm",  # rm patterns
        r">\s*/dev/",
        r"curl.*\|\s*sh",
        r"wget.*\|\s*sh",  # Dangerous redirects/downloads
        r"eval\s*\(",
        r"exec\s*\(",
        r"system\s*\(",  # Dangerous function calls
        r"`.*`",
        r"\$\(",  # Command substitution
        r">\s*/etc/",
        r">\s*/usr/",
        r">\s*/var/",  # System directory writes
        r"chmod.*777",
        r"chown.*root",
        r"sudo\s+",
        r"su\s+",  # Privilege changes
    ]
]


@dataclass
class CommandPattern:
    """Represents a whitelisted command pattern with validation rules."""

    command: str
    allowed_args: List[str]
    arg_patterns: Dict[str, str]  # arg_name -> regex pattern
    max_args: int
    description: str
    shell_required: bool = False  # Some commands may require shell=True


class CommandValidator:
    """
    Validates and sanitizes commands before execution to prevent injection
    attacks.
    """

    def __init__(self):
        """Initialize command validator with security whitelist."""
        self.logger = logging.getLogger(__name__)
        self._init_whitelist()

    def _get_system_commands(self) -> Dict[str, CommandPattern]:
        """Get system information command patterns."""
        return {
            "ps": CommandPattern(
                command="ps",
                allowed_args=["aux", "e", "-e", "-aux", "axf"],
                arg_patterns={"aux": r"^aux$", "e": r"^-?ef$", "ax": r"^axf$"},
                max_args=1,
                description="Process status listing",
            ),
            "ls": CommandPattern(
                command="ls",
                allowed_args=[
                    "-l",
                    "-la",
                    "-al",
                    "-a",
                    "--all",
                    "-h",
                    "--human-readable",
                ],
                arg_patterns={
                    "-l": r"^-l$",
                    "-la": r"^-la$",
                    "-al": r"^-al$",
                    "-a": r"^-a$",
                    "--all": r"^--all$",
                    "-h": r"^-h$",
                    "--human-readable": r"^--human-readable$",
                },
                max_args=3,
                description="Directory listing",
            ),
            "pwd": CommandPattern(
                command="pwd",
                allowed_args=[],
                arg_patterns={},
                max_args=0,
                description="Print working directory",
            ),
            "whoami": CommandPattern(
                command="whoami",
                allowed_args=[],
                arg_patterns={},
                max_args=0,
                description="Current user identification",
            ),
            "id": CommandPattern(
                command="id",
                allowed_args=["-u", "-g", "-G"],
                arg_patterns={"-u": r"^-u$", "-g": r"^-g$", "-G": r"^-G$"},
                max_args=1,
                description="User and group ID information",
            ),
            "uname": CommandPattern(
                command="uname",
                allowed_args=["-a", "-r", "-s"],
                arg_patterns={"-a": r"^-a$", "-r": r"^-r$", "-s": r"^-s$"},
                max_args=1,
                description="System information",
            ),
            "uptime": CommandPattern(
                command="uptime",
                allowed_args=[],
                arg_patterns={},
                max_args=0,
                description="System uptime and load",
            ),
            "date": CommandPattern(
                command="date",
                allowed_args=[],
                arg_patterns={},
                max_args=0,
                description="Current date and time",
            ),
            "d": CommandPattern(
                command="d",
                allowed_args=["-h", "--human-readable"],
                arg_patterns={"-h": r"^-h$", "--human-readable": r"^--human-readable$"},
                max_args=1,
                description="Disk space usage",
            ),
            "free": CommandPattern(
                command="free",
                allowed_args=["-h", "-m"],
                arg_patterns={"-h": r"^-h$", "-m": r"^-m$"},
                max_args=1,
                description="Memory usage information",
            ),
        }

    def _get_network_commands(self) -> Dict[str, CommandPattern]:
        """Get network information command patterns."""
        return {
            "ifconfig": CommandPattern(
                command="ifconfig",
                allowed_args=[],
                arg_patterns={},
                max_args=0,
                description="Network interface configuration",
            ),
            "ip": CommandPattern(
                command="ip",
                allowed_args=["addr", "show", "route"],
                arg_patterns={
                    "addr": r"^addr$",
                    "show": r"^show$",
                    "route": r"^route$",
                },
                max_args=2,
                description="Network configuration tool",
            ),
            "netstat": CommandPattern(
                command="netstat",
                allowed_args=["-tuln", "-rn"],
                arg_patterns={"-tuln": r"^-tuln$", "-rn": r"^-rn$"},
                max_args=1,
                description="Network connections and routing",
            ),
            "ss": CommandPattern(
                command="ss",
                allowed_args=["-tuln", "-rn"],
                arg_patterns={"-tuln": r"^-tuln$", "-rn": r"^-rn$"},
                max_args=1,
                description="Socket statistics",
            ),
        }

    def _get_file_commands(self) -> Dict[str, CommandPattern]:
        """Get safe file operation command patterns."""
        return {
            "cat": CommandPattern(
                command="cat",
                allowed_args=[],
                arg_patterns={},
                max_args=1,
                description="Display file contents",
                shell_required=True,
            ),
            "head": CommandPattern(
                command="head",
                allowed_args=["-n"],
                arg_patterns={"-n": r"^-n$"},
                max_args=3,
                description="Display first lines of file",
                shell_required=True,
            ),
            "tail": CommandPattern(
                command="tail",
                allowed_args=["-n"],
                arg_patterns={"-n": r"^-n$"},
                max_args=3,
                description="Display last lines of file",
                shell_required=True,
            ),
        }

    def _init_whitelist(self) -> None:
        """Initialize the whitelist of allowed commands and their patterns."""
        self.whitelist: Dict[str, CommandPattern] = {}
        self.whitelist.update(self._get_system_commands())
        self.whitelist.update(self._get_network_commands())
        self.whitelist.update(self._get_file_commands())

    def _invalid_result(self, reason: str) -> Dict[str, Union[bool, str, List[str]]]:
        """Create an invalid validation result."""
        return {
            "valid": False,
            "reason": reason,
            "parsed_command": [],
            "use_shell": False,
        }

    def _parse_command(self, command_string: str) -> tuple:
        """Parse command string safely. Returns (command_parts, error_result or None)."""
        try:
            command_parts = shlex.split(command_string.strip())
        except ValueError as e:
            return [], self._invalid_result(f"Command parsing failed: {str(e)}")
        if not command_parts:
            return [], self._invalid_result("Empty command")
        return command_parts, None

    def _validate_whitelist_and_args(self, command_parts: List[str]) -> tuple:
        """Validate command against whitelist and check arguments. Returns (pattern, error_result or None)."""
        base_command = command_parts[0]
        if base_command not in self.whitelist:
            return None, self._invalid_result(
                f"Command '{base_command}' not in whitelist"
            )

        pattern = self.whitelist[base_command]
        args = command_parts[1:] if len(command_parts) > 1 else []

        if len(args) > pattern.max_args:
            return None, self._invalid_result(
                f"Too many arguments for '{base_command}' (max: {pattern.max_args}, got: {len(args)})"
            )

        arg_validation = self._validate_arguments(args, pattern)
        if not arg_validation["valid"]:
            return None, self._invalid_result(arg_validation["reason"])

        return pattern, None

    def validate_command(
        self, command_string: str
    ) -> Dict[str, Union[bool, str, List[str]]]:
        """Validate a command string against security policies."""
        try:
            # Check for dangerous patterns
            dangerous_check = self._check_dangerous_patterns(command_string)
            if not dangerous_check["safe"]:
                return self._invalid_result(
                    f"Dangerous pattern detected: {dangerous_check['pattern']}"
                )

            # Parse command
            command_parts, error = self._parse_command(command_string)
            if error:
                return error

            # Validate against whitelist and arguments
            pattern, error = self._validate_whitelist_and_args(command_parts)
            if error:
                return error

            # Success
            self.logger.info(
                "Command validated successfully: %s with %s args",
                command_parts[0],
                len(command_parts) - 1,
            )
            return {
                "valid": True,
                "reason": f"Command '{command_parts[0]}' validated successfully",
                "parsed_command": command_parts,
                "use_shell": pattern.shell_required,
            }

        except Exception as e:
            self.logger.error("Command validation error: %s", str(e))
            return self._invalid_result(f"Validation error: {str(e)}")

    def _check_dangerous_patterns(self, command: str) -> Dict[str, Union[bool, str]]:
        """Check if command contains dangerous patterns."""
        # Issue #380: Use pre-compiled patterns from module level
        for compiled_pattern in _DANGEROUS_PATTERNS:
            if compiled_pattern.search(command):
                self.logger.warning(
                    f"Dangerous pattern detected: {compiled_pattern.pattern} in command: "
                    f"{command}"
                )
                return {"safe": False, "pattern": compiled_pattern.pattern}
        return {"safe": True, "pattern": ""}

    def _validate_arguments(
        self, args: List[str], pattern: CommandPattern
    ) -> Dict[str, Union[bool, str]]:
        """Validate command arguments against allowed patterns."""
        for arg in args:
            # Check if argument is in allowed list
            if pattern.allowed_args and arg not in pattern.allowed_args:
                # Check if it matches any allowed patterns
                valid_pattern = False
                for allowed_arg, regex_pattern in pattern.arg_patterns.items():
                    if re.match(regex_pattern, arg):
                        valid_pattern = True
                        break

                if not valid_pattern:
                    return {
                        "valid": False,
                        "reason": (
                            f"Argument '{arg}' not allowed for command "
                            f"'{pattern.command}'"
                        ),
                    }

            # Check for injection attempts in arguments
            injection_patterns = [";", "&&", "||", "|", "`", "$", ">", "<", "&"]
            for injection_char in injection_patterns:
                if injection_char in arg:
                    return {
                        "valid": False,
                        "reason": (
                            "Potential injection character "
                            f"'{injection_char}' "
                            f"in argument '{arg}'"
                        ),
                    }

        return {"valid": True, "reason": "Arguments validated successfully"}

    def get_whitelist_info(
        self,
    ) -> Dict[str, Dict[str, Union[str, List[str], int]]]:
        """
        Get information about whitelisted commands for debugging/admin
        purposes.
        """
        return {
            cmd: {
                "description": pattern.description,
                "allowed_args": pattern.allowed_args,
                "max_args": pattern.max_args,
                "shell_required": pattern.shell_required,
            }
            for cmd, pattern in self.whitelist.items()
        }

    def add_to_whitelist(self, command_pattern: CommandPattern) -> bool:
        """
        Add a new command to the whitelist (for runtime configuration).

        Args:
            command_pattern: CommandPattern to add

        Returns:
            bool: True if added successfully
        """
        try:
            self.whitelist[command_pattern.command] = command_pattern
            self.logger.info("Added '%s' to command whitelist", command_pattern.command)
            return True
        except Exception as e:
            self.logger.error("Failed to add command to whitelist: %s", str(e))
            return False


# Global instance for use throughout the application
command_validator = CommandValidator()
