# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secure command validation to prevent prompt injection attacks.
This module replaces LLM-based command extraction with a safelist approach.
"""

import json
import logging
import os
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozensets to avoid repeated list creation
_COMMAND_REQUEST_KEYWORDS = frozenset({"run", "execute", "command"})
_DANGEROUS_CHARS = frozenset({"&", ";", "|", ">", "<", "`", "$"})


class CommandValidator:
    """Validates and sanitizes system commands using a predefined safelist."""

    def __init__(self, config_path: str = None):
        """Initialize the command validator with a config file."""
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), "../../config/allowed_commands.json"
            )

        self.allowed_commands = self._load_config(config_path)
        self.blocked_patterns = self.allowed_commands.get("blocked_patterns", [])

    def _load_config(self, config_path: str) -> Dict:
        """Load the allowed commands configuration."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load command config: %s", e)
            # Return minimal safe defaults
            return {
                "commands": {
                    "system_info": {
                        "commands": ["uname -a"],
                        "description": "Get system information",
                        "risk_level": "LOW",
                    }
                },
                "blocked_patterns": ["rm ", "sudo ", "> ", "| "],
            }

    def is_command_blocked(self, command: str) -> Tuple[bool, str]:
        """Check if a command contains blocked patterns."""
        command_lower = command.lower().strip()

        for pattern in self.blocked_patterns:
            if pattern in command_lower:
                return True, f"Contains blocked pattern: {pattern}"

        # Additional safety checks - Issue #380: Use module-level frozenset
        for char in _DANGEROUS_CHARS:
            if char in command:
                return True, f"Contains dangerous character: {char}"

        return False, ""

    def get_allowed_command(self, query_type: str, message: str) -> Optional[Dict]:
        """
        Get an allowed command for a specific query type.
        This replaces the vulnerable LLM-based extraction.
        """
        commands_config = self.allowed_commands.get("commands", {})

        if query_type not in commands_config:
            return None

        config = commands_config[query_type]
        command = config["commands"][0]  # Use first command as default

        # Security check - ensure command is not blocked
        is_blocked, reason = self.is_command_blocked(command)
        if is_blocked:
            logger.warning(
                "Allowed command blocked by safety check: %s - %s", command, reason
            )
            return None

        return {
            "type": query_type,
            "command": command,
            "description": config["description"],
            "risk_level": config["risk_level"],
            "alternatives": (
                config["commands"][1:] if len(config["commands"]) > 1 else []
            ),
        }

    def detect_query_type(self, message: str) -> Optional[str]:
        """
        Detect what type of system query the user is asking for.
        Uses keyword matching instead of LLM extraction.
        """
        message_lower = message.lower().strip()

        # Define keyword mappings for each query type
        keyword_mappings = {
            "system_info": [
                "system",
                "info",
                "uname",
                "version",
                "kernel",
                "os",
                "operating system",
            ],
            "network_info": ["ip", "address", "network", "interface", "hostname"],
            "disk_usage": ["disk", "space", "storage", "filesystem", "df", "drive"],
            "memory_usage": ["memory", "ram", "free", "memory usage", "mem"],
            "process_list": ["process", "running", "ps", "top", "cpu", "processes"],
            "uptime_info": ["uptime", "running time", "boot", "load"],
            "date_time": ["date", "time", "clock", "timezone"],
        }

        # Score each query type based on keyword matches
        scores = {}
        for query_type, keywords in keyword_mappings.items():
            score = sum(1 for keyword in keywords if keyword in message_lower)
            if score > 0:
                scores[query_type] = score

        # Return the query type with the highest score
        if scores:
            return max(scores, key=scores.get)

        return None

    def validate_command_request(self, message: str) -> Optional[Dict]:
        """
        Main validation method that replaces the vulnerable LLM extraction.
        Returns command info if valid, None otherwise.
        """
        try:
            # Detect what the user is asking for
            query_type = self.detect_query_type(message)

            if query_type:
                # Get the allowed command for this query type
                command_info = self.get_allowed_command(query_type, message)

                if command_info:
                    logger.info("Validated command request: %s -> ", query_type)
                    return command_info

            # Check for explicit command requests (but don't execute them)
            # Issue #380: Use module-level frozenset
            if any(word in message.lower() for word in _COMMAND_REQUEST_KEYWORDS):
                logger.warning("Blocked explicit command request: %s", message)
                return {
                    "type": "blocked",
                    "command": "BLOCKED",
                    "description": "Explicit command execution blocked for security",
                    "risk_level": "HIGH",
                }

            return None

        except Exception as e:
            logger.error("Command validation error: %s", e)
            return None

    def get_available_commands(self) -> Dict:
        """Get list of available command types and their descriptions."""
        commands_config = self.allowed_commands.get("commands", {})
        return {
            query_type: {
                "description": config["description"],
                "risk_level": config["risk_level"],
                "example_commands": config["commands"][:2],  # Show first 2 as examples
            }
            for query_type, config in commands_config.items()
        }


# Global instance (thread-safe)
import threading

_command_validator = None
_command_validator_lock = threading.Lock()


def get_command_validator() -> CommandValidator:
    """Get the global command validator instance (thread-safe)."""
    global _command_validator
    if _command_validator is None:
        with _command_validator_lock:
            # Double-check after acquiring lock
            if _command_validator is None:
                _command_validator = CommandValidator()
    return _command_validator
