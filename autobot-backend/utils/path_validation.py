# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Path Validation Utilities - Shared security validation for paths and identifiers.

This module provides reusable validation functions for detecting path traversal
attacks and invalid characters in filenames, directory names, and identifiers.

CONSOLIDATES PATTERNS FROM (Issue #328):
========================================
- backend/api/files.py:709 (rename validation)
- backend/api/files.py:945 (create directory validation)
- backend/api/knowledge_models.py:63 (fact_id validation)
- backend/api/knowledge_models.py:236 (tag validation)
- backend/api/knowledge_models.py:311 (bulk fact_id validation)
- backend/api/knowledge_models.py:482 (bulk delete fact_id validation)

BENEFITS:
=========
✅ Single source of truth for path security validation
✅ Consistent behavior across all modules
✅ Easier to update security rules in one place
✅ Replaces complex inline conditionals with named functions
✅ Self-documenting code through function names

USAGE:
======
from utils.path_validation import contains_path_traversal, is_invalid_name

# In files.py
if is_invalid_name(new_name):
    raise HTTPException(status_code=400, detail="Invalid name")

# In Pydantic validators
if contains_path_traversal(v):
    raise ValueError("Path traversal not allowed")
"""

from typing import FrozenSet

# Characters that indicate path traversal attacks
# Using frozenset for O(1) membership testing
PATH_TRAVERSAL_PATTERNS: FrozenSet[str] = frozenset({"..", "/", "\\"})

# Extended patterns including null byte (for session IDs and identifiers)
INJECTION_PATTERNS: FrozenSet[str] = frozenset({"..", "/", "\\", "\0"})

# Patterns for validating file paths (absolute paths) — only dotdot and null byte.
# Forward-slash is intentionally excluded: absolute paths legitimately contain "/".
# Use this instead of contains_path_traversal() when the value being checked is a
# full filesystem path (e.g. a backup file path) rather than a bare filename or
# identifier.  (#9670)
DOTDOT_TRAVERSAL_PATTERNS: FrozenSet[str] = frozenset({"..", "\0"})


def contains_path_traversal(value: str) -> bool:
    """
    Check if a string contains path traversal attack patterns.

    Detects common path traversal sequences that could be used to
    access files outside intended directories.

    Args:
        value: String to check (filename, identifier, etc.)

    Returns:
        True if path traversal patterns are detected, False otherwise

    Examples:
        >>> contains_path_traversal("../etc/passwd")
        True
        >>> contains_path_traversal("normal_file.txt")
        False
        >>> contains_path_traversal("path/to/file")
        True
        >>> contains_path_traversal("path\\\\to\\\\file")
        True
    """
    return any(pattern in value for pattern in PATH_TRAVERSAL_PATTERNS)


def contains_dotdot_traversal(value: str) -> bool:
    """
    Check if a file path contains dotdot traversal sequences or null bytes.

    Use this function when *value* is a full filesystem path (e.g. an absolute
    backup file path like ``/opt/autobot/backups/kb_backup.json``).  Unlike
    ``contains_path_traversal``, forward-slash is **not** treated as suspicious
    because absolute paths legitimately contain ``/``.  (#9670)

    Args:
        value: File path string to check.

    Returns:
        True if dotdot traversal or null bytes are detected, False otherwise.

    Examples:
        >>> contains_dotdot_traversal("/opt/autobot/backups/kb_backup.json")
        False
        >>> contains_dotdot_traversal("/opt/autobot/backups/../../../etc/passwd")
        True
        >>> contains_dotdot_traversal("/tmp/file\\x00.txt")
        True
    """
    return any(pattern in value for pattern in DOTDOT_TRAVERSAL_PATTERNS)


def is_invalid_name(name: str) -> bool:
    """
    Validate that a filename or directory name is safe for filesystem operations.

    Combines empty check with path traversal detection for common validation
    pattern used in file/directory creation and renaming.

    Args:
        name: Filename or directory name to validate

    Returns:
        True if the name is invalid (empty or contains path traversal), False if safe

    Examples:
        >>> is_invalid_name("")
        True
        >>> is_invalid_name("../parent")
        True
        >>> is_invalid_name("valid_name.txt")
        False
        >>> is_invalid_name("file/name")
        True
    """
    return not name or contains_path_traversal(name)


def is_safe_identifier(identifier: str) -> bool:
    """
    Check if an identifier is safe (non-empty and no path traversal).

    Inverse of is_invalid_name, provided for semantic clarity when
    checking for validity rather than invalidity.

    Args:
        identifier: Identifier string to validate

    Returns:
        True if identifier is safe, False otherwise

    Examples:
        >>> is_safe_identifier("fact_123")
        True
        >>> is_safe_identifier("../escape")
        False
        >>> is_safe_identifier("")
        False
    """
    return bool(identifier) and not contains_path_traversal(identifier)


def contains_injection_patterns(value: str) -> bool:
    """
    Check if a string contains injection attack patterns (path traversal + null byte).

    More comprehensive than contains_path_traversal, includes null byte detection
    for session IDs and identifiers where null byte injection could be a concern.

    Args:
        value: String to check (session ID, identifier, etc.)

    Returns:
        True if injection patterns are detected, False otherwise

    Examples:
        >>> contains_injection_patterns("session\\x00malicious")
        True
        >>> contains_injection_patterns("../parent")
        True
        >>> contains_injection_patterns("valid_session_id")
        False
    """
    return any(pattern in value for pattern in INJECTION_PATTERNS)


__all__ = [
    "PATH_TRAVERSAL_PATTERNS",
    "INJECTION_PATTERNS",
    "DOTDOT_TRAVERSAL_PATTERNS",
    "contains_path_traversal",
    "contains_dotdot_traversal",
    "contains_injection_patterns",
    "is_invalid_name",
    "is_safe_identifier",
]
