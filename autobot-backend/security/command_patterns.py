# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized Command Security Patterns for AutoBot
==================================================

Single Source of Truth for dangerous command detection and safe command lists.

Issue #765: Consolidates duplicate patterns from:
- src/agents/system_command_agent.py
- src/agents/overseer/step_executor_agent.py
- src/secure_command_executor.py

Usage:
    from security.command_patterns import (
        is_dangerous_command,
        is_safe_command,
        check_dangerous_patterns,
        DANGEROUS_PATTERNS,
        SAFE_COMMANDS,
    )

    # Check if command is dangerous
    is_dangerous, reason = is_dangerous_command("rm -rf /")

    # Check if base command is safe
    if is_safe_command("ls"):
        ...
"""

import re
from dataclasses import dataclass
from typing import FrozenSet, List, Optional, Tuple

# =============================================================================
# DANGEROUS COMMAND PATTERNS - STRING-BASED (Simple Matching)
# =============================================================================
# Used for quick substring checks. These are the patterns from system_command_agent.py

DANGEROUS_SUBSTRINGS: FrozenSet[str] = frozenset(
    {
        "rm -rf /",
        "rm -rf /*",
        "dd if=/dev/zero",
        "mkfs",
        "format",
        "> /dev/sda",
        "fork bomb",
        ":(){ :|:& };:",
        "chmod -R 777 /",
        "chown -R",
        "shutdown",
        "reboot",
        "init 0",
        "systemctl poweroff",
    }
)


# =============================================================================
# DANGEROUS COMMAND PATTERNS - REGEX-BASED (Precise Matching)
# =============================================================================
# Compiled regex patterns with descriptions for detailed security checking.
# Consolidated from step_executor_agent.py and secure_command_executor.py


@dataclass(frozen=True)
class DangerousPattern:
    """A dangerous command pattern with its regex and description."""

    pattern: re.Pattern
    description: str
    severity: str = "high"  # "high", "critical", "forbidden"


# Issue #765: Unified regex patterns from all sources
DANGEROUS_REGEX_PATTERNS: Tuple[DangerousPattern, ...] = (
    # Recursive delete patterns
    DangerousPattern(
        re.compile(r"\brm\s+(-[rf]+\s+)*(/|~|\$HOME)", re.IGNORECASE),
        "Recursive delete on root/home",
        "critical",
    ),
    DangerousPattern(
        re.compile(r"\brm\s+-rf\s+\*", re.IGNORECASE),
        "Recursive delete all files",
        "critical",
    ),
    DangerousPattern(
        re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
        "rm -rf / pattern",
        "forbidden",
    ),
    # Fork bomb
    DangerousPattern(
        re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|"),
        "Fork bomb pattern",
        "forbidden",
    ),
    DangerousPattern(
        re.compile(r":\(\)\{\s*:\|:&\s*\};:"),
        "Fork bomb variant",
        "forbidden",
    ),
    # Filesystem operations
    DangerousPattern(
        re.compile(r"\bmkfs\b", re.IGNORECASE),
        "Filesystem format",
        "critical",
    ),
    DangerousPattern(
        re.compile(r"\bdd\s+.*of=/dev/", re.IGNORECASE),
        "Direct disk write with dd",
        "critical",
    ),
    DangerousPattern(
        re.compile(r">\s*/dev/sd[a-z]", re.IGNORECASE),
        "Write to disk device",
        "critical",
    ),
    # Permission changes
    DangerousPattern(
        re.compile(r"\bchmod\s+-R\s+777\s+/", re.IGNORECASE),
        "Recursive chmod 777 on root",
        "critical",
    ),
    DangerousPattern(
        re.compile(r"\bchown\s+-R\s+.*\s+/\s*$", re.IGNORECASE),
        "Recursive chown on root",
        "critical",
    ),
    # System control
    DangerousPattern(
        re.compile(r"\bshutdown\b|\breboot\b|\bpoweroff\b", re.IGNORECASE),
        "System shutdown/reboot",
        "high",
    ),
    DangerousPattern(
        re.compile(r"\bsystemctl\s+(stop|disable)\s+", re.IGNORECASE),
        "Stop/disable system service",
        "high",
    ),
    # Process control
    DangerousPattern(
        re.compile(r"\bkill\s+-9\s+-1\b", re.IGNORECASE),
        "Kill all processes",
        "critical",
    ),
    # Network/Firewall
    DangerousPattern(
        re.compile(r"\biptables\s+-F\b", re.IGNORECASE),
        "Flush firewall rules",
        "high",
    ),
    # Sensitive file access
    DangerousPattern(
        re.compile(r"/etc/passwd", re.IGNORECASE),
        "Password file access",
        "high",
    ),
    DangerousPattern(
        re.compile(r"/etc/shadow", re.IGNORECASE),
        "Shadow file access",
        "critical",
    ),
    # Command injection patterns
    DangerousPattern(
        re.compile(r"\$\(.*\)"),
        "Command substitution",
        "high",
    ),
    DangerousPattern(
        re.compile(r"`.*`"),
        "Backtick command substitution",
        "high",
    ),
    # Chained dangerous commands
    DangerousPattern(
        re.compile(r";\s*rm\s+-r", re.IGNORECASE),
        "Command chaining with rm",
        "critical",
    ),
    DangerousPattern(
        re.compile(r"&&\s*rm\s+-r", re.IGNORECASE),
        "Conditional rm",
        "critical",
    ),
    DangerousPattern(
        re.compile(r"\|\s*rm\s+-r", re.IGNORECASE),
        "Piped to rm",
        "critical",
    ),
)


# =============================================================================
# SAFE COMMAND LISTS
# =============================================================================
# Commands that are generally safe to execute without special approval.

SAFE_COMMANDS: FrozenSet[str] = frozenset(
    {
        # Basic filesystem inspection
        "ls",
        "pwd",
        "whoami",
        "hostname",
        "date",
        "uptime",
        "uname",
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "wc",
        "sort",
        "uniq",
        "file",
        "stat",
        "which",
        "whereis",
        "type",
        "tree",
        # Text processing (read-only)
        "grep",
        "awk",
        "sed",
        "cut",
        "tr",
        "find",
        "locate",
        # System monitoring
        "df",
        "du",
        "free",
        "top",
        "htop",
        "ps",
        "pgrep",
        # Network diagnostics
        "ip",
        "ifconfig",
        "netstat",
        "ss",
        "ping",
        "traceroute",
        "dig",
        "nslookup",
        "host",
        "nmap",
        "arp",
        "route",
        "curl",
        "wget",
        # Output and environment
        "echo",
        "printf",
        "env",
        "printenv",
        # User info
        "id",
        "groups",
        "w",
        "who",
        "last",
        # Development tools
        "git",
        "npm",
        "python",
        "pip",
    }
)

# Commands that need approval for certain arguments
MODERATE_RISK_COMMANDS: FrozenSet[str] = frozenset(
    {
        "cp",
        "mv",
        "mkdir",
        "touch",
        "chmod",
        "chown",
        "tar",
        "zip",
        "unzip",
        "gzip",
        "gunzip",
        "sed",
        "awk",
        "cut",
        "paste",
        "join",
    }
)

# High-risk commands that always need approval
HIGH_RISK_COMMANDS: FrozenSet[str] = frozenset(
    {
        "rm",
        "rmdir",
        "dd",
        "mkfs",
        "fdisk",
        "parted",
        "mount",
        "umount",
        "chroot",
        "sudo",
        "su",
        "systemctl",
        "service",
        "apt",
        "apt-get",
        "dpkg",
        "yum",
        "dnf",
        "zypper",
        "pacman",
    }
)

# Forbidden commands that should never run
FORBIDDEN_COMMANDS: FrozenSet[str] = frozenset(
    {
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "init",
        "telinit",
        "kill",
        "killall",
        "pkill",
    }
)

# Commands that start persistent sessions (Issue #380)
PERSISTENT_SESSION_COMMANDS: Tuple[str, ...] = (
    "ssh",
    "screen",
    "tmux",
    "docker exec",
    "kubectl exec",
)

# Unrestricted root access commands (Issue #380)
UNRESTRICTED_ROOT_COMMANDS: FrozenSet[str] = frozenset({"sudo su", "sudo -i"})


# =============================================================================
# PATH CONSTANTS FOR SECURITY CHECKS
# =============================================================================

# System paths that require elevated permissions
SYSTEM_PATHS: FrozenSet[str] = frozenset(
    {
        "/etc",
        "/usr",
        "/bin",
        "/sbin",
        "/lib",
    }
)

# Paths where output redirection is dangerous
SENSITIVE_REDIRECT_PATHS: FrozenSet[str] = frozenset(
    {
        "/etc/",
        "/boot/",
        "/sys/",
        "/dev/",
    }
)

# Dangerous paths for recursive operations
DANGEROUS_RECURSIVE_PATHS: FrozenSet[str] = frozenset(
    {
        "/",
        "/*",
        "~",
        "$HOME",
    }
)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def is_dangerous_substring(command: str) -> Tuple[bool, Optional[str]]:
    """
    Check if command contains any dangerous substrings (fast check).

    Args:
        command: The command string to check

    Returns:
        Tuple of (is_dangerous, matched_pattern_or_none)
    """
    command_lower = command.lower()
    for pattern in DANGEROUS_SUBSTRINGS:
        if pattern.lower() in command_lower:
            return True, pattern
    return False, None


def check_dangerous_patterns(command: str) -> List[Tuple[str, str, str]]:
    """
    Check command against all dangerous regex patterns.

    Args:
        command: The command string to check

    Returns:
        List of tuples (pattern_description, severity, matched_text)
        for all patterns that matched
    """
    matches = []
    for dp in DANGEROUS_REGEX_PATTERNS:
        match = dp.pattern.search(command)
        if match:
            matches.append((dp.description, dp.severity, match.group(0)))
    return matches


def is_dangerous_command(command: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a command is dangerous using both substring and regex checks.

    This is the primary function for security validation.

    Args:
        command: The command string to check

    Returns:
        Tuple of (is_dangerous, reason_or_none)
    """
    # Fast substring check first
    is_dangerous, pattern = is_dangerous_substring(command)
    if is_dangerous:
        return True, f"Dangerous pattern: {pattern}"

    # Detailed regex check
    matches = check_dangerous_patterns(command)
    if matches:
        # Return the most severe match
        for desc, severity, _ in matches:
            if severity == "forbidden":
                return True, f"Forbidden: {desc}"
        for desc, severity, _ in matches:
            if severity == "critical":
                return True, f"Critical: {desc}"
        # Return first high severity match
        return True, f"Dangerous: {matches[0][0]}"

    return False, None


def is_safe_command(base_command: str) -> bool:
    """
    Check if a base command name is in the safe commands list.

    Args:
        base_command: The base command name (e.g., "ls", not "ls -la")

    Returns:
        True if the command is generally safe
    """
    return base_command in SAFE_COMMANDS


def get_command_risk_level(base_command: str) -> str:
    """
    Get the risk level for a base command.

    Args:
        base_command: The base command name

    Returns:
        Risk level: "safe", "moderate", "high", "forbidden", or "unknown"
    """
    if base_command in FORBIDDEN_COMMANDS:
        return "forbidden"
    if base_command in HIGH_RISK_COMMANDS:
        return "high"
    if base_command in MODERATE_RISK_COMMANDS:
        return "moderate"
    if base_command in SAFE_COMMANDS:
        return "safe"
    return "unknown"


def is_persistent_session_command(command: str) -> bool:
    """
    Check if command starts a persistent session.

    Args:
        command: The full command string

    Returns:
        True if command starts a persistent session
    """
    return any(command.startswith(cmd) for cmd in PERSISTENT_SESSION_COMMANDS)


def is_unrestricted_root_command(command: str) -> bool:
    """
    Check if command requests unrestricted root access.

    Args:
        command: The full command string

    Returns:
        True if command requests unrestricted root
    """
    return command.strip() in UNRESTRICTED_ROOT_COMMANDS


def has_system_path(command: str) -> bool:
    """
    Check if command operates on system paths.

    Args:
        command: The full command string

    Returns:
        True if command involves system paths
    """
    return any(path in command for path in SYSTEM_PATHS)


def has_sensitive_redirect(command: str) -> bool:
    """
    Check if command redirects output to sensitive locations.

    Args:
        command: The full command string

    Returns:
        True if command redirects to sensitive paths
    """
    if ">" not in command and ">>" not in command:
        return False
    return any(path in command for path in SENSITIVE_REDIRECT_PATHS)


# =============================================================================
# LEGACY COMPATIBILITY - Tuple format for step_executor_agent.py
# =============================================================================
# The step_executor_agent uses List[Tuple[re.Pattern, str]] format


def get_dangerous_patterns_as_tuples() -> List[Tuple[re.Pattern, str]]:
    """
    Get dangerous patterns in the legacy tuple format.

    Returns:
        List of (compiled_pattern, description) tuples
    """
    return [(dp.pattern, dp.description) for dp in DANGEROUS_REGEX_PATTERNS]


# Legacy alias for backward compatibility
DANGEROUS_PATTERNS = get_dangerous_patterns_as_tuples()
