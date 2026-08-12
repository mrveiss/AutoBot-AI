# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the shared SQL identifier allowlist validator (#2845, #13393).

Moved from ``autobot-backend/utils/sql_injection_hardening_test.py`` when
``validate_sql_identifier`` was consolidated into a single public helper
(#13393). Covers CodeQL/semgrep ``autobot-sql-string-format`` alerts: identifiers
that cannot be bound as parameters are validated against a strict allowlist
before f-string interpolation.
"""

import pytest

from autobot_shared.security.sql_identifier import validate_sql_identifier

# Payload containing SQL metacharacters that must never be executed.
INJECTION = "widgets; DROP TABLE widgets;--"


def test_validate_sql_identifier_rejects_metacharacters():
    """The allowlist validator raises on any non-identifier character."""
    with pytest.raises(ValueError):
        validate_sql_identifier(INJECTION, "table name")
    assert validate_sql_identifier("valid_name_1", "table name") == "valid_name_1"


def test_validate_sql_identifier_rejects_trailing_newline():
    """A trailing newline must be rejected, not accepted via `$` end-of-string
    semantics (#13393): Python's `$` matches before a final newline, so a
    `$`-anchored pattern would let "users\\n" through despite the newline
    falling outside [A-Za-z0-9_]. The validator uses `\\Z` instead.
    """
    with pytest.raises(ValueError):
        validate_sql_identifier("users\n", "table name")
    with pytest.raises(ValueError):
        validate_sql_identifier("users\n\n", "table name")
