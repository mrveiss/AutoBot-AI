# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Command Detector for AutoBot

This module provides intelligent command detection and suggestion capabilities
using the command manual knowledge base for better command understanding.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from command_manual_manager import CommandManualManager

logger = logging.getLogger(__name__)

# Issue #281: Intent patterns extracted from _load_intent_patterns
INTENT_PATTERNS = {
    "network_info": {
        "keywords": ["ip", "address", "network", "interface", "connection"],
        "questions": ["what is my ip", "show network", "network config"],
        "primary_commands": ["ifconfig", "ip addr", "hostname -I"],
        "description": "Display network interface information",
        "category": "network",
    },
    "disk_space": {
        "keywords": ["disk", "space", "storage", "filesystem", "d", "free space"],
        "questions": ["disk space", "how much space", "storage usage"],
        "primary_commands": ["df -h", "du -sh"],
        "description": "Check disk space and usage",
        "category": "system_info",
    },
    "memory_usage": {
        "keywords": ["memory", "ram", "free", "memory usage", "available"],
        "questions": ["memory usage", "how much ram", "free memory"],
        "primary_commands": ["free -h", "cat /proc/meminfo"],
        "description": "Display memory usage information",
        "category": "system_info",
    },
    "process_list": {
        "keywords": ["process", "running", "ps", "programs", "tasks"],
        "questions": ["what processes", "running programs", "list processes"],
        "primary_commands": ["ps aux", "top", "htop"],
        "description": "List running processes",
        "category": "process_management",
    },
    "system_info": {
        "keywords": ["system", "info", "version", "kernel", "os", "uptime"],
        "questions": ["system info", "what system", "kernel version"],
        "primary_commands": ["uname -a", "lsb_release -a", "uptime"],
        "description": "Display system information",
        "category": "system_info",
    },
    "file_operations": {
        "keywords": ["list", "files", "directory", "folder", "contents"],
        "questions": ["list files", "show contents", "what files"],
        "primary_commands": ["ls -la", "ls -lh"],
        "description": "List files and directories",
        "category": "file_operations",
    },
    "find_files": {
        "keywords": ["find", "search", "locate", "where is"],
        "questions": ["find file", "search for", "locate file"],
        "primary_commands": ["find", "locate", "which"],
        "description": "Find files and programs",
        "category": "file_operations",
    },
    "network_test": {
        "keywords": ["ping", "test", "connection", "reachable", "connectivity"],
        "questions": ["test connection", "ping", "is reachable"],
        "primary_commands": ["ping", "traceroute", "curl"],
        "description": "Test network connectivity",
        "category": "network",
    },
    "package_operations": {
        "keywords": ["install", "update", "upgrade", "package", "software"],
        "questions": ["install package", "update system", "install software"],
        "primary_commands": ["apt install", "apt update", "yum install"],
        "description": "Package management operations",
        "category": "package_management",
    },
}

# Issue #281: Command alternatives extracted from get_alternative_commands
COMMAND_ALTERNATIVES = {
    "ifconfig": ["ip addr", "ip link", "hostname -I"],
    "netstat": ["ss", "lsof -i"],
    "ps": ["top", "htop", "pgrep"],
    "ls": ["ll", "dir", "find"],
    "cat": ["less", "more", "head", "tail"],
    "grep": ["awk", "sed", "ripgrep"],
    "find": ["locate", "which", "whereis"],
}

# Issue #281: Risk explanations extracted from explain_command_risk
RISK_LEVEL_EXPLANATIONS = {
    "LOW": (
        "The command '{}' is considered safe - it only reads "
        "information and doesn't modify your system."
    ),
    "MEDIUM": (
        "The command '{}' may modify files or system settings. "
        "Please review what it will do before approving."
    ),
    "HIGH": (
        "⚠️ The command '{}' can make significant system changes "
        "or delete data. Use with extreme caution!"
    ),
}


class EnhancedCommandDetector:
    """Enhanced command detection with knowledge base integration."""

    def __init__(self, db_path: str = "data/knowledge_base.db"):
        """Initialize the enhanced command detector.

        Args:
            db_path: Path to the knowledge base database
        """
        self.manual_manager = CommandManualManager(db_path)
        self.intent_patterns = self._load_intent_patterns()

    def _load_intent_patterns(self) -> Dict[str, Dict]:
        """Load patterns for detecting user intents.

        Issue #281: Refactored to use module-level constant.
        Reduced from 77 to 5 lines (94% reduction).

        Returns:
            Dictionary of intent patterns and their associated information
        """
        return INTENT_PATTERNS

    def detect_intent(self, message: str) -> Optional[str]:
        """Detect user intent from message.

        Args:
            message: User message

        Returns:
            Intent name or None if not detected
        """
        message_lower = message.lower()

        # Check for direct matches with questions
        for intent, data in self.intent_patterns.items():
            for question in data.get("questions", []):
                if question in message_lower:
                    return intent

        # Check for keyword matches
        best_intent = None
        best_score = 0

        for intent, data in self.intent_patterns.items():
            score = 0
            for keyword in data.get("keywords", []):
                if keyword in message_lower:
                    score += 1

            # Boost score for multiple keyword matches
            if score > 1:
                score = score * 1.5

            if score > best_score and score >= 1:
                best_score = score
                best_intent = intent

        return best_intent

    def extract_command_from_message(self, message: str) -> Optional[str]:
        """Extract explicit command from user message.

        Args:
            message: User message

        Returns:
            Command name if found, None otherwise
        """
        # Look for patterns like "use command", "run command", "execute command"
        command_patterns = [
            r"(?:use|run|execute|try)\s+(?:the\s+)?([a-zA-Z][a-zA-Z0-9_-]+)",
            r"(?:with|using)\s+([a-zA-Z][a-zA-Z0-9_-]+)",
            r"`([a-zA-Z][a-zA-Z0-9_-]+)",  # Commands in backticks
            r"([a-zA-Z][a-zA-Z0-9_-]+)\s+(?:command|tool)",
        ]

        for pattern in command_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def get_command_info_from_kb(self, command_name: str) -> Optional[Dict]:
        """Get command information from knowledge base.

        Args:
            command_name: Name of the command

        Returns:
            Dictionary with command information or None
        """
        manual = self.manual_manager.get_manual(command_name)
        if manual:
            return {
                "command": manual.command_name,
                "description": manual.description,
                "syntax": manual.syntax,
                "purpose": manual.description,
                "explanation": (
                    f"Use {manual.command_name} to {manual.description.lower()}"
                ),
                "risk_level": manual.risk_level,
                "category": manual.category,
                "examples": manual.examples[:3],  # Top 3 examples
                "common_options": manual.common_options[:5],  # Top 5 options
                "related_commands": manual.related_commands[:3],  # Top 3 related
                "from_knowledge_base": True,
            }
        return None

    def suggest_command_with_manual(self, command_name: str) -> Dict:
        """Suggest a command with manual lookup if not in KB.

        Args:
            command_name: Name of the command

        Returns:
            Command suggestion dictionary
        """
        # First check knowledge base
        kb_info = self.get_command_info_from_kb(command_name)
        if kb_info:
            return kb_info

        # If not in KB, suggest manual lookup
        return {
            "command": f"man {command_name}",
            "description": f"Display manual page for {command_name}",
            "syntax": f"man {command_name}",
            "purpose": f"Learn about the {command_name} command",
            "explanation": f"Look up manual for {command_name} to understand its usage",
            "risk_level": "LOW",
            "category": "documentation",
            "manual_lookup": True,
            "target_command": command_name,
            "from_knowledge_base": False,
        }

    def enhance_command_suggestion(self, intent: str, message: str) -> Optional[Dict]:
        """Enhance command suggestion using knowledge base.

        Args:
            intent: Detected intent
            message: Original user message

        Returns:
            Enhanced command suggestion or None
        """
        if intent not in self.intent_patterns:
            return None

        intent_data = self.intent_patterns[intent]
        primary_commands = intent_data.get("primary_commands", [])

        if not primary_commands:
            return None

        # Check each primary command in knowledge base
        for cmd in primary_commands:
            cmd_name = cmd.split()[0]  # Get base command name
            kb_info = self.get_command_info_from_kb(cmd_name)

            if kb_info:
                # Use knowledge base information
                return {
                    **kb_info,
                    "command": cmd,  # Use full command with options
                    "intent": intent,
                    "enhanced": True,
                }

        # Fallback to basic suggestion
        return {
            "command": primary_commands[0],
            "description": intent_data["description"],
            "purpose": intent_data["description"],
            "explanation": f"To {intent_data['description'].lower()}",
            "risk_level": "LOW",
            "category": intent_data["category"],
            "intent": intent,
            "from_knowledge_base": False,
        }

    def search_commands_by_functionality(
        self, query: str
    ) -> List[Tuple[str, str, str]]:
        """Search for commands by functionality.

        Args:
            query: Functionality query

        Returns:
            List of (command_name, description, risk_level) tuples
        """
        return self.manual_manager.get_command_suggestions(query)

    async def detect_command_needed(
        self, message: str, llm_interface=None
    ) -> Optional[Dict]:
        """Enhanced command detection with knowledge base integration.

        Args:
            message: User message
            llm_interface: LLM interface (for compatibility)

        Returns:
            Command suggestion dictionary or None
        """
        # 1. Check for explicit command mention
        explicit_command = self.extract_command_from_message(message)
        if explicit_command:
            return self.suggest_command_with_manual(explicit_command)

        # 2. Detect intent from message
        intent = self.detect_intent(message)
        if intent:
            suggestion = self.enhance_command_suggestion(intent, message)
            if suggestion:
                return suggestion

        # 3. Search knowledge base for relevant commands
        kb_suggestions = self.search_commands_by_functionality(message)
        if kb_suggestions:
            cmd_name, description, risk_level = kb_suggestions[0]  # Best match
            kb_info = self.get_command_info_from_kb(cmd_name)
            if kb_info:
                return {**kb_info, "search_match": True, "query": message}

        # 4. Handle generic "how to use X" questions
        how_to_match = re.search(
            r"how\s+(?:do\s+i\s+|to\s+)?(?:use\s+)?(?:the\s+)?([a-zA-Z][a-zA-Z0-9_-]+)",
            message,
            re.IGNORECASE,
        )
        if how_to_match:
            command_name = how_to_match.group(1)
            return self.suggest_command_with_manual(command_name)

        return None

    def get_alternative_commands(self, command_name: str) -> List[str]:
        """Get alternative commands for a given command.

        Issue #281: Refactored to use module-level constant.
        Reduced from 24 to 12 lines (50% reduction).

        Args:
            command_name: Name of the command

        Returns:
            List of alternative command names
        """
        manual = self.manual_manager.get_manual(command_name)
        if manual and manual.related_commands:
            return manual.related_commands

        # Fallback to predefined alternatives (Issue #281: Use module constant)
        return COMMAND_ALTERNATIVES.get(command_name, [])

    def explain_command_risk(self, command_info: Dict) -> str:
        """Explain why a command has a certain risk level.

        Issue #281: Refactored to use module-level constant.
        Reduced from 24 to 12 lines (50% reduction).

        Args:
            command_info: Command information dictionary

        Returns:
            Risk explanation string
        """
        risk_level = command_info.get("risk_level", "LOW")
        command = command_info.get("command", "unknown")

        # Issue #281: Use module-level constant with format placeholder
        template = RISK_LEVEL_EXPLANATIONS.get(risk_level)
        if template:
            return template.format(command)
        return "Risk level unknown for this command."


async def main():
    """Test the enhanced command detector."""
    detector = EnhancedCommandDetector()

    test_messages = [
        "what is my ip address?",
        "how do I use nmap?",
        "show me disk space",
        "list running processes",
        "find files named config",
        "use curl to test connection",
    ]

    logger.debug("Testing Enhanced Command Detector")
    logger.debug("=" * 50)

    for message in test_messages:
        logger.debug("\nMessage: %s", message)
        result = await detector.detect_command_needed(message)
        if result:
            logger.debug("Command: %s", result['command'])
            logger.debug("Purpose: %s", result['purpose'])
            logger.debug("Risk: %s", result['risk_level'])
            logger.debug(f"From KB: {result.get('from_knowledge_base', False)}")
        else:
            logger.debug("No command detected")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
