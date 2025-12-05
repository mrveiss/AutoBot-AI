# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Terminal Utilities

Helper functions for agent terminal operations.
"""

import re
from typing import TYPE_CHECKING, Optional

from backend.models.command_execution import CommandExecution, CommandState, RiskLevel
from src.secure_command_executor import CommandRisk

if TYPE_CHECKING:
    from .models import AgentTerminalSession


def map_risk_to_level(risk: CommandRisk) -> RiskLevel:
    """
    Convert CommandRisk to RiskLevel enum.

    REUSABLE PRINCIPLE: Single function, clear responsibility, reusable across codebase.

    CommandRisk enum values: SAFE, MODERATE, HIGH, CRITICAL, FORBIDDEN
    RiskLevel enum values: LOW, MEDIUM, HIGH, CRITICAL

    Args:
        risk: CommandRisk from security assessment

    Returns:
        Corresponding RiskLevel enum
    """
    risk_mapping = {
        CommandRisk.SAFE: RiskLevel.LOW,  # Safe commands → Low risk
        CommandRisk.MODERATE: RiskLevel.MEDIUM,  # Moderate commands → Medium risk
        CommandRisk.HIGH: RiskLevel.HIGH,  # High risk commands → High risk
        CommandRisk.CRITICAL: RiskLevel.CRITICAL,  # Critical commands → Critical risk
        CommandRisk.FORBIDDEN: (
            RiskLevel.CRITICAL
        ),  # Forbidden commands → Critical risk (blocked)
    }
    return risk_mapping.get(risk, RiskLevel.MEDIUM)


def extract_terminal_and_chat_ids(session: "AgentTerminalSession") -> tuple[str, str]:
    """
    Extract terminal session ID and chat ID from agent session.

    REUSABLE PRINCIPLE: DRY - centralize ID extraction logic.

    Args:
        session: Agent terminal session

    Returns:
        Tuple of (terminal_session_id, chat_id)
    """
    terminal_session_id = session.pty_session_id or session.session_id
    chat_id = session.conversation_id or ""
    return terminal_session_id, chat_id


def create_command_execution(
    session: "AgentTerminalSession",
    command: str,
    description: str,
    risk: "CommandRisk",
    risk_reasons: list[str],
    is_interactive: bool = False,
    interactive_reasons: Optional[list[str]] = None,
) -> CommandExecution:
    """
    Create CommandExecution object from session and command details.

    REUSABLE PRINCIPLE: Factory function - encapsulates object creation logic.
    Single responsibility: Create CommandExecution, nothing else.

    Args:
        session: Agent terminal session
        command: Command to execute
        description: Command purpose/description
        risk: CommandRisk level
        risk_reasons: List of risk reasons
        is_interactive: Whether command requires stdin input (Issue #33)
        interactive_reasons: Why command is interactive (pattern matches)

    Returns:
        CommandExecution object ready to add to queue
    """
    # Use helper functions (DRY principle)
    terminal_session_id, chat_id = extract_terminal_and_chat_ids(session)
    risk_level = map_risk_to_level(risk)

    # Build metadata with interactive command info (Issue #33)
    metadata = {}
    if is_interactive:
        metadata["is_interactive"] = True
        metadata["interactive_reasons"] = interactive_reasons or []

    return CommandExecution(
        terminal_session_id=terminal_session_id,
        chat_id=chat_id,
        command=command,
        purpose=description,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        state=CommandState.PENDING_APPROVAL,
        metadata=metadata,
    )


# ============================================================================
# INTERACTIVE COMMAND DETECTION (Issue #33)
# ============================================================================

# Patterns for detecting commands that require stdin input
INTERACTIVE_COMMAND_PATTERNS = [
    r"^\s*sudo\s+",  # sudo commands (password)
    r"^\s*ssh\s+",  # SSH connections (host verification, password)
    r"\bmysql\s+.*-p\b",  # MySQL with password flag
    r"\bmysql\s+--password\b",  # MySQL with --password flag
    r"^\s*passwd\b",  # Password change commands
    r"\b--interactive\b",  # Explicit interactive flag
    r"^\s*python.*input\(",  # Python scripts with input()
    r"^\s*read\s+",  # Bash read command
    r"^\s*select\s+",  # Bash select menu
    r"^\s*apt\s+install\b",  # APT with confirmations
    r"^\s*yum\s+install\b",  # YUM with confirmations
    r"^\s*docker\s+login\b",  # Docker login (username/password)
    r"^\s*git\s+clone.*@",  # Git clone with SSH (password)
    r"^\s*psql\s+",  # PostgreSQL client
    r"^\s*ftp\s+",  # FTP client
    r"^\s*telnet\s+",  # Telnet client
]

# Compile patterns for performance
_INTERACTIVE_PATTERNS_COMPILED = [
    re.compile(pattern, re.IGNORECASE) for pattern in INTERACTIVE_COMMAND_PATTERNS
]


def is_interactive_command(command: str) -> tuple[bool, list[str]]:
    """
    Detect if a command requires interactive stdin input.

    REUSABLE PRINCIPLE: Single responsibility - only detects interactive commands.

    Args:
        command: Shell command to analyze

    Returns:
        Tuple of (is_interactive, matched_patterns)
        - is_interactive: True if command requires stdin
        - matched_patterns: List of pattern descriptions that matched

    Examples:
        >>> is_interactive_command("sudo apt update")
        (True, ["sudo commands (password)"])

        >>> is_interactive_command("ls -la")
        (False, [])

        >>> is_interactive_command("ssh user@host")
        (True, ["SSH connections (host verification, password)"])
    """
    matched_patterns = []

    for pattern, description in zip(
        _INTERACTIVE_PATTERNS_COMPILED,
        [
            "sudo commands (password)",
            "SSH connections (host verification, password)",
            "MySQL with password flag",
            "MySQL with --password flag",
            "Password change commands",
            "Explicit interactive flag",
            "Python scripts with input()",
            "Bash read command",
            "Bash select menu",
            "APT with confirmations",
            "YUM with confirmations",
            "Docker login (username/password)",
            "Git clone with SSH (password)",
            "PostgreSQL client",
            "FTP client",
            "Telnet client",
        ],
    ):
        if pattern.search(command):
            matched_patterns.append(description)

    return (len(matched_patterns) > 0, matched_patterns)
