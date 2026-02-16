# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced System Commands Agent - Specialized for system command generation.

Uses lightweight Llama 3.2 1B model for efficient command generation with security.
Handles system operations, shell commands, and system administration tasks.
"""

import json
import logging
import re
import shlex
from typing import Any, Dict, FrozenSet, List, Optional

from autobot_shared.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from backend.constants.threshold_constants import LLMDefaults
from llm_interface import LLMInterface

from .base_agent import AgentRequest
from .standardized_agent import StandardizedAgent

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for dangerous rm flags
_DANGEROUS_RM_FLAGS: FrozenSet[str] = frozenset({"-r", "-rf", "-f"})


class EnhancedSystemCommandsAgent(StandardizedAgent):
    """System commands agent with security-focused prompting and validation."""

    # Agent identifier for SSOT config lookup
    AGENT_ID = "system_commands"

    def _init_allowed_commands(self) -> set:
        """Initialize set of allowed commands (Issue #398: extracted)."""
        commands = set()
        commands.update(self._get_filesystem_commands())
        commands.update(self._get_system_info_commands())
        commands.update(self._get_network_commands())
        commands.update(self._get_service_commands())
        commands.update(self._get_file_operation_commands())
        commands.update(self._get_text_processing_commands())
        return commands

    def _get_filesystem_commands(self) -> set:
        """Return filesystem navigation and viewing commands. Issue #620."""
        return {"ls", "dir", "pwd", "cd", "cat", "head", "tail", "grep", "find"}

    def _get_system_info_commands(self) -> set:
        """Return system information commands. Issue #620."""
        return {
            "ps",
            "top",
            "htop",
            "d",
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

    def _get_network_commands(self) -> set:
        """Return network-related commands. Issue #620."""
        return {"ifconfig", "ip", "netstat", "ss", "ping", "curl", "wget"}

    def _get_service_commands(self) -> set:
        """Return service management commands. Issue #620."""
        return {"systemctl", "service", "journalctl", "dmesg"}

    def _get_file_operation_commands(self) -> set:
        """Return file operation commands. Issue #620."""
        return {
            "chmod",
            "chown",
            "mkdir",
            "rmdir",
            "cp",
            "mv",
            "touch",
            "ln",
            "tar",
            "gzip",
            "gunzip",
            "zip",
            "unzip",
        }

    def _get_text_processing_commands(self) -> set:
        """Return text processing commands. Issue #620."""
        return {"sort", "uniq", "wc", "awk", "sed", "cut"}

    def _init_dangerous_patterns(self) -> list:
        """Initialize list of dangerous command patterns (Issue #398: extracted)."""
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

    def __init__(self):
        """Initialize the System Commands Agent with explicit LLM configuration."""
        super().__init__("enhanced_system_commands")
        self.llm_interface = LLMInterface()

        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)

        self.capabilities = [
            "command_generation",
            "security_validation",
            "shell_operations",
            "system_administration",
            "command_explanation",
        ]
        self.allowed_commands = self._init_allowed_commands()
        self.dangerous_patterns = self._init_dangerous_patterns()
        logger.info(
            "System Commands Agent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider,
            self.llm_endpoint,
            self.model_name,
        )

    async def action_process_command(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle process_command action."""
        task = request.payload.get("task", "")
        context = request.context or {}
        return await self.process_command_request(task, context)

    async def action_validate_command(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle validate_command action."""
        command = request.payload.get("command", "")
        result = self.validate_command_safety(command)
        return {"is_safe": result, "command": command}

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    def _build_command_messages(
        self, request: str, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """Build messages for command generation (Issue #398: extracted)."""
        messages = [{"role": "system", "content": self._get_system_commands_prompt()}]
        if context:
            context_str = self._build_context_string(context)
            messages.append({"role": "system", "content": f"Context: {context_str}"})
        messages.append({"role": "user", "content": request})
        return messages

    def _build_success_response(self, command_info: Dict[str, Any]) -> Dict[str, Any]:
        """Build success response with metadata (Issue #398: extracted)."""
        return {
            "status": "success" if command_info.get("is_safe", False) else "warning",
            **command_info,
            "agent_type": "system_commands",
            "model_used": self.model_name,
            "metadata": {
                "agent": "EnhancedSystemCommandsAgent",
                "security_checked": True,
                "validation_level": "strict",
            },
        }

    def _build_error_response(self, error: Exception) -> Dict[str, Any]:
        """Build error response (Issue #398: extracted)."""
        return {
            "status": "error",
            "command": "",
            "explanation": "Failed to process command request",
            "is_safe": False,
            "error": str(error),
            "agent_type": "system_commands",
            "model_used": self.model_name,
        }

    async def process_command_request(
        self, request: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a command request (Issue #398: refactored)."""
        try:
            logger.info("System Commands Agent processing: %s...", request[:50])
            messages = self._build_command_messages(request, context)
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="system_commands",
                temperature=0.3,
                max_tokens=LLMDefaults.CONCISE_MAX_TOKENS,
                top_p=0.8,
            )
            command_info = self._extract_and_validate_command(response)
            security_check = self._security_validate_command(
                command_info.get("command", "")
            )
            command_info.update(security_check)
            return self._build_success_response(command_info)
        except Exception as e:
            logger.error("System Commands Agent error: %s", e)
            return self._build_error_response(e)

    def _get_system_commands_prompt(self) -> str:
        """Get security-focused system prompt for command generation."""
        return """You are a system command generation assistant focused on security
        and safety.

CRITICAL SECURITY RULES:
1. NEVER generate commands that could harm the system
2. AVOID commands that modify system files, users, or permissions
3. PREFER read-only commands when possible
4. Always explain what the command does
5. If a request is dangerous, suggest a safer alternative

RESPONSE FORMAT:
Generate responses in this exact JSON format:
{
    "command": "the actual shell command",
    "explanation": "clear explanation of what this command does",
    "safety_level": "safe/caution/dangerous",
    "alternative": "suggest safer alternative if original is risky"
}

PREFERRED COMMANDS:
- Information gathering: ls, ps, df, free, netstat, ip addr
- File viewing: cat, head, tail, less
- System monitoring: top, htop, systemctl status
- Network diagnostics: ping, curl (with safe URLs)

AVOID:
- File deletion (rm, especially rm -rf)
- Permission changes (chmod, chown)
- User management (passwd, usermod, userdel)
- System modifications (iptables, firewall changes)
- Dangerous disk operations (dd, fdisk, mkfs)
- Pipe to shell operations (curl | bash, wget | sh)

If asked to do something potentially harmful, explain why it's risky
and suggest alternatives."""

    def _build_context_string(self, context: Dict[str, Any]) -> str:
        """Build context string for better command generation."""
        context_parts = []

        if "os_info" in context:
            os_info = context["os_info"]
            if "name" in os_info:
                context_parts.append(f"OS: {os_info['name']}")
            if "version" in os_info:
                context_parts.append(f"Version: {os_info['version']}")

        if "current_directory" in context:
            context_parts.append(f"Current Directory: {context['current_directory']}")

        if "user" in context:
            context_parts.append(f"User: {context['user']}")

        return " | ".join(context_parts)

    def _extract_and_validate_command(self, response: Any) -> Dict[str, Any]:
        """Extract and perform basic validation of generated command."""
        try:
            # Extract response content
            content = self._extract_response_content(response)

            # Try to parse as JSON first
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "command" in parsed:
                    return {
                        "command": parsed.get("command", "").strip(),
                        "explanation": parsed.get(
                            "explanation", "No explanation provided"
                        ),
                        "safety_level": parsed.get("safety_level", "unknown"),
                        "alternative": parsed.get("alternative", ""),
                        "is_structured": True,
                    }
            except json.JSONDecodeError as e:
                logger.debug("JSON decode failed, using fallback extraction: %s", e)

            # Fallback: try to extract command from text
            command = self._extract_command_from_text(content)

            return {
                "command": command,
                "explanation": content,
                "safety_level": "unknown",
                "alternative": "",
                "is_structured": False,
            }

        except Exception as e:
            logger.error("Error extracting command: %s", e)
            return {
                "command": "",
                "explanation": f"Failed to extract command: {e}",
                "safety_level": "dangerous",
                "alternative": "",
                "is_structured": False,
            }

    def _extract_command_from_text(self, text: str) -> str:
        """Extract command from unstructured text response."""
        # Look for common command patterns
        patterns = [
            r"```(?:bash|sh|shell)?\n(.*?)\n```",  # Code blocks
            r"`([^`]+)`",  # Inline code
            r"^([\w\-]+(?:\s+[\w\-\.\/\=]+)*)",  # Command at start of line
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
            if match:
                command = match.group(1).strip()
                if command and not command.startswith("#"):  # Skip comments
                    return command

        return text.strip()

    def _check_dangerous_patterns(self, command: str) -> Optional[Dict[str, Any]]:
        """Check command against dangerous patterns (Issue #398: extracted)."""
        for pattern in self.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return {
                    "is_safe": False,
                    "security_warning": f"Command contains dangerous pattern: {pattern}",
                    "recommended_action": "reject",
                }
        return None

    def _validate_parsed_command(
        self, parts: list, main_command: str
    ) -> Dict[str, Any]:
        """Validate parsed command parts (Issue #398: extracted)."""
        if main_command not in self.allowed_commands:
            return {
                "is_safe": False,
                "security_warning": f"Command '{main_command}' not in allowed commands list",
                "recommended_action": "review_manually",
            }
        if main_command == "rm" and any(flag in parts for flag in _DANGEROUS_RM_FLAGS):
            return {
                "is_safe": False,
                "security_warning": "rm command with potentially dangerous flags",
                "recommended_action": "reject",
            }
        return {"is_safe": True, "security_warning": None, "main_command": main_command}

    def _security_validate_command(self, command: str) -> Dict[str, Any]:
        """Perform security validation (Issue #398: refactored)."""
        if not command:
            return {"is_safe": False, "security_warning": "Empty command"}

        danger_result = self._check_dangerous_patterns(command)
        if danger_result:
            return danger_result

        try:
            parts = shlex.split(command)
            if not parts:
                return {"is_safe": False, "security_warning": "Unable to parse command"}
            main_command = parts[0].split("/")[-1]
            return self._validate_parsed_command(parts, main_command)
        except Exception as e:
            return {
                "is_safe": False,
                "security_warning": f"Failed to parse command: {e}",
                "recommended_action": "reject",
            }

    def _try_extract_message_content(self, response: Dict) -> Optional[str]:
        """Try to extract content from message dict (Issue #334 - extracted helper)."""
        if "message" not in response or not isinstance(response["message"], dict):
            return None
        content = response["message"].get("content")
        return content.strip() if content else None

    def _try_extract_choices_content(self, response: Dict) -> Optional[str]:
        """Try to extract content from choices list (Issue #334 - extracted helper)."""
        if "choices" not in response or not isinstance(response["choices"], list):
            return None
        if not response["choices"]:
            return None
        choice = response["choices"][0]
        if "message" not in choice or "content" not in choice["message"]:
            return None
        return choice["message"]["content"].strip()

    def _extract_response_content(self, response: Any) -> str:
        """Extract the actual text content from LLM response."""
        try:
            if isinstance(response, dict):
                content = self._try_extract_message_content(response)
                if content:
                    return content
                content = self._try_extract_choices_content(response)
                if content:
                    return content
                if "content" in response:
                    return response["content"].strip()

            if isinstance(response, str):
                return response.strip()

            return str(response)

        except Exception as e:
            logger.error("Error extracting response content: %s", e)
            return "Error extracting command response"

    def is_system_command_request(self, message: str) -> bool:
        """
        Determine if a message is a system command request.

        Args:
            message: The user's message

        Returns:
            bool: True if system commands agent should handle it
        """
        command_patterns = [
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
            "d",
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

        message_lower = message.lower()
        return any(pattern in message_lower for pattern in command_patterns)


# Singleton instance (thread-safe)
import threading

_enhanced_system_commands_agent_instance = None
_enhanced_system_commands_agent_lock = threading.Lock()


def get_enhanced_system_commands_agent() -> EnhancedSystemCommandsAgent:
    """Get the singleton Enhanced System Commands Agent instance (thread-safe)."""
    global _enhanced_system_commands_agent_instance
    if _enhanced_system_commands_agent_instance is None:
        with _enhanced_system_commands_agent_lock:
            # Double-check after acquiring lock
            if _enhanced_system_commands_agent_instance is None:
                _enhanced_system_commands_agent_instance = EnhancedSystemCommandsAgent()
    return _enhanced_system_commands_agent_instance
