# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Security Module

Command risk assessment and security enforcement for terminal operations.
"""

import logging
from typing import Set

from api.terminal_models import (
    MODERATE_RISK_PATTERNS,
    RISKY_COMMAND_PATTERNS,
    CommandRiskLevel,
    SecurityLevel,
)

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for shell operators (Issue #326)
SHELL_OPERATORS: Set[str] = {">", ">>", "|", "&&", "||"}

# Performance optimization: O(1) lookup for security levels requiring logging (Issue #326)
LOGGING_SECURITY_LEVELS: Set[SecurityLevel] = {
    SecurityLevel.ELEVATED,
    SecurityLevel.RESTRICTED,
}

# Performance optimization: O(1) lookup for high-risk command levels (Issue #326)
HIGH_RISK_COMMAND_LEVELS: Set[CommandRiskLevel] = {
    CommandRiskLevel.DANGEROUS,
    CommandRiskLevel.HIGH,
}


class CommandSecurityAssessor:
    """Assesses command security risks and enforces security policies"""

    def assess_command_risk(self, command: str) -> CommandRiskLevel:
        """Assess the security risk level of a command"""
        command_lower = command.lower().strip()

        # Check for dangerous patterns
        for pattern in RISKY_COMMAND_PATTERNS:
            if pattern in command_lower:
                return CommandRiskLevel.DANGEROUS

        # Check for moderate risk patterns
        for pattern in MODERATE_RISK_PATTERNS:
            if pattern in command_lower:
                return CommandRiskLevel.MODERATE

        # Special checks for high-risk operations (Issue #326: O(1) lookups)
        if any(x in command_lower for x in SHELL_OPERATORS):
            return CommandRiskLevel.HIGH

        return CommandRiskLevel.SAFE

    def should_block_command(
        self,
        command: str,
        risk_level: CommandRiskLevel,
        security_level: SecurityLevel,
    ) -> bool:
        """Determine if command should be blocked based on security level"""
        if security_level == SecurityLevel.RESTRICTED:
            return risk_level in HIGH_RISK_COMMAND_LEVELS
        elif security_level == SecurityLevel.ELEVATED:
            return risk_level == CommandRiskLevel.DANGEROUS

        return False  # STANDARD level allows most commands

    def should_enable_logging(self, security_level: SecurityLevel) -> bool:
        """Check if logging should be enabled for this security level"""
        return security_level in LOGGING_SECURITY_LEVELS


# Singleton instance for convenience
command_assessor = CommandSecurityAssessor()
