# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SQL identifier allowlist validator (#2845, #13393).

SQLite/other engines cannot bind table or column names as query parameters,
so identifiers that must be interpolated into an f-string query need an
allowlist check first. This is the single shared implementation - previously
three verbatim, module-private copies existed in the backend (#13393).

Usage:
    from autobot_shared.security.sql_identifier import validate_sql_identifier

    safe_table = validate_sql_identifier(table_name, "table name")
    query = f"SELECT COUNT(*) FROM {safe_table}"  # nosec B608  # identifier allowlisted
"""

from __future__ import annotations

import re

# `\Z` (not `$`) anchors strictly to end-of-string: Python's `$` also matches
# immediately before a trailing newline, so "users\n" would otherwise pass
# this allowlist despite containing a character outside [A-Za-z0-9_] (#13393).
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\Z")


def validate_sql_identifier(name: str, label: str = "identifier") -> str:
    """Validate a SQL identifier (table or column name) against an allowlist pattern.

    Only permits names composed of ASCII letters, digits, and underscores, starting
    with a letter or underscore. Prevents SQL injection via identifier interpolation. (#2845)

    Args:
        name: The identifier to validate.
        label: Human-readable label used in the error message.

    Returns:
        The validated name unchanged.

    Raises:
        ValueError: If the name contains characters outside the allowed set.
    """
    if not _SQL_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL {label} '{name}': only letters, digits, and underscores allowed")
    return name
