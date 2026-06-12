# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for path_validation utilities.

Regression tests for #9670 — basename file checks fail for subdirectory
files.  The defect was that contains_path_traversal() included "/" in its
pattern set, causing it to reject all absolute file paths (which legitimately
contain forward-slashes) as "path traversal attempts".  The fix introduces
contains_dotdot_traversal() for full-path validation contexts.
"""

from utils.path_validation import (
    contains_dotdot_traversal,
    contains_path_traversal,
    is_invalid_name,
    is_safe_identifier,
)


class TestContainsPathTraversal:
    """Tests for contains_path_traversal — used on bare filenames/identifiers."""

    def test_bare_safe_filename(self):
        assert contains_path_traversal("document.txt") is False

    def test_bare_safe_identifier(self):
        assert contains_path_traversal("fact_abc123") is False

    def test_dotdot_rejected(self):
        assert contains_path_traversal("../etc/passwd") is True

    def test_forward_slash_rejected(self):
        # For bare filenames/identifiers a slash is always wrong.
        assert contains_path_traversal("subdir/file.txt") is True

    def test_backslash_rejected(self):
        assert contains_path_traversal("subdir\\file.txt") is True

    def test_empty_string(self):
        assert contains_path_traversal("") is False


class TestContainsDotdotTraversal:
    """Tests for contains_dotdot_traversal — used on full filesystem paths.

    #9670: absolute backup file paths contain "/" but are NOT traversal attacks.
    """

    # --- legitimate absolute paths that MUST pass (the bug repro) ---

    def test_absolute_backup_path_accepted(self):
        """Absolute path to a backup file must NOT be flagged.

        This was the failing case in #9670: contains_path_traversal returned
        True for any absolute path because "/" was in PATH_TRAVERSAL_PATTERNS.
        """
        path = "/opt/autobot/backups/kb_backup_2026-06-12.json"
        assert contains_dotdot_traversal(path) is False

    def test_absolute_path_in_subdirectory_accepted(self):
        """Path with multiple directory components must be accepted."""
        path = "/opt/autobot/backups/2026/june/kb_backup.json.gz"
        assert contains_dotdot_traversal(path) is False

    def test_relative_safe_path_accepted(self):
        """Relative path without dotdot must be accepted."""
        assert contains_dotdot_traversal("subdir/kb_backup.json") is False

    # --- real traversal attacks that MUST be rejected ---

    def test_dotdot_absolute_rejected(self):
        path = "/opt/autobot/backups/../../../etc/shadow"
        assert contains_dotdot_traversal(path) is True

    def test_dotdot_at_start_rejected(self):
        assert contains_dotdot_traversal("../../etc/passwd") is True

    def test_dotdot_embedded_rejected(self):
        assert contains_dotdot_traversal("/opt/safe/../../../etc/passwd") is True

    def test_null_byte_rejected(self):
        assert contains_dotdot_traversal("/opt/autobot/backup\x00.json") is True

    # --- contrast with contains_path_traversal ---

    def test_slash_not_flagged_by_dotdot_check(self):
        """Forward-slash is NOT a traversal attack for full paths."""
        assert contains_dotdot_traversal("/opt/autobot/file.json") is False

    def test_slash_IS_flagged_by_path_traversal_check(self):
        """contains_path_traversal does flag slashes — correct for filenames."""
        assert contains_path_traversal("/opt/autobot/file.json") is True


class TestIsInvalidName:
    """Tests for is_invalid_name — used on bare filenames/dir names."""

    def test_valid_name(self):
        assert is_invalid_name("valid_name.txt") is False

    def test_empty_is_invalid(self):
        assert is_invalid_name("") is True

    def test_dotdot_is_invalid(self):
        assert is_invalid_name("../parent") is True

    def test_slash_is_invalid(self):
        assert is_invalid_name("sub/dir") is True


class TestIsSafeIdentifier:
    """Tests for is_safe_identifier."""

    def test_safe_id(self):
        assert is_safe_identifier("fact_abc123") is True

    def test_empty_is_unsafe(self):
        assert is_safe_identifier("") is False

    def test_dotdot_is_unsafe(self):
        assert is_safe_identifier("../escape") is False
