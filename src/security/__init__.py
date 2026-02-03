# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security module for AutoBot.
Provides secure command validation and other security utilities.
"""

from .command_patterns import (
    DANGEROUS_PATTERNS,
    FORBIDDEN_COMMANDS,
    HIGH_RISK_COMMANDS,
    MODERATE_RISK_COMMANDS,
    SAFE_COMMANDS,
    check_dangerous_patterns,
    get_command_risk_level,
    is_dangerous_command,
    is_safe_command,
)
from .command_validator import CommandValidator, get_command_validator

__all__ = [
    # Command validator
    "CommandValidator",
    "get_command_validator",
    # Command patterns (Issue #765)
    "DANGEROUS_PATTERNS",
    "SAFE_COMMANDS",
    "MODERATE_RISK_COMMANDS",
    "HIGH_RISK_COMMANDS",
    "FORBIDDEN_COMMANDS",
    "is_dangerous_command",
    "is_safe_command",
    "check_dangerous_patterns",
    "get_command_risk_level",
]
