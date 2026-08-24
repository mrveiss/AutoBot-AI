# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Terminal Security Module

Command risk assessment and security enforcement for terminal operations.
"""

from typing import Set

from api.schemas_terminal import SecurityLevel
from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import CommandRisk
from constants.terminal_constants import MODERATE_RISK_PATTERNS, RISKY_COMMAND_PATTERNS

logger = get_logger(__name__)

# Performance optimization: O(1) lookup for shell operators (Issue #326)
SHELL_OPERATORS: Set[str] = {">", ">>", "|", "&&", "||"}

# Performance optimization: O(1) lookup for security levels requiring logging (Issue #326)
LOGGING_SECURITY_LEVELS: Set[SecurityLevel] = {
    SecurityLevel.ELEVATED,
    SecurityLevel.RESTRICTED,
}

# Performance optimization: O(1) lookup for high-risk command levels (Issue #326).
# #13845: derived from ``CommandRisk.blocks`` plus HIGH rather than listed by
# hand, so a blocking member added later cannot be missed here.
HIGH_RISK_COMMAND_LEVELS: Set[CommandRisk] = {
    risk for risk in CommandRisk if risk.blocks
} | {CommandRisk.HIGH}


class CommandSecurityAssessor:
    """Assesses command security risks and enforces security policies"""

    def assess_command_risk(self, command: str) -> CommandRisk:
        """Assess the security risk level of a command"""
        command_lower = command.lower().strip()

        # Check for dangerous patterns
        for pattern in RISKY_COMMAND_PATTERNS:
            if pattern in command_lower:
                return CommandRisk.DANGEROUS

        # Check for moderate risk patterns
        for pattern in MODERATE_RISK_PATTERNS:
            if pattern in command_lower:
                return CommandRisk.MODERATE

        # Special checks for high-risk operations (Issue #326: O(1) lookups)
        if any(x in command_lower for x in SHELL_OPERATORS):
            return CommandRisk.HIGH

        return CommandRisk.SAFE

    def should_block_command(
        self,
        command: str,
        risk_level: CommandRisk,
        security_level: SecurityLevel,
    ) -> bool:
        """Determine if command should be blocked based on security level"""
        if security_level == SecurityLevel.RESTRICTED:
            return risk_level in HIGH_RISK_COMMAND_LEVELS
        elif security_level == SecurityLevel.ELEVATED:
            # #13845: ``.blocks`` also covers FORBIDDEN, which the unioned enum
            # can now carry into this path.
            return risk_level.blocks

        return False  # STANDARD level allows most commands

    def should_enable_logging(self, security_level: SecurityLevel) -> bool:
        """Check if logging should be enabled for this security level"""
        return security_level in LOGGING_SECURITY_LEVELS


# Singleton instance for convenience
command_assessor = CommandSecurityAssessor()
