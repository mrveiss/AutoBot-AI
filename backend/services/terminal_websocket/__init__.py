# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal WebSocket Module

Extracted components from terminal_handlers.py for better modularity.
This module provides security, audit, and chat integration components
that support the main terminal WebSocket handler.

Note: The main ConsolidatedTerminalWebSocket and ConsolidatedTerminalManager
classes remain in backend/api/terminal_handlers.py as they are tightly
coupled to the WebSocket lifecycle and PTY management.
"""

from .audit import TerminalAuditLogger
from .chat_integration import TerminalChatIntegrator
from .security import (
    HIGH_RISK_COMMAND_LEVELS,
    LOGGING_SECURITY_LEVELS,
    SHELL_OPERATORS,
    CommandSecurityAssessor,
    command_assessor,
)

__all__ = [
    # Security
    "CommandSecurityAssessor",
    "command_assessor",
    "SHELL_OPERATORS",
    "LOGGING_SECURITY_LEVELS",
    "HIGH_RISK_COMMAND_LEVELS",
    # Audit
    "TerminalAuditLogger",
    # Chat Integration
    "TerminalChatIntegrator",
]
