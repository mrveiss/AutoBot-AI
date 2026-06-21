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

Also covers the directory-containment helper _resolve_backup_path added to
BulkOperationsMixin as part of the #9670 security amendment: dotdot-stripping
alone is insufficient — an attacker can supply /etc/passwd directly without
any dotdot sequence.  Tests use a thin mixin stub so no Redis/Chroma fixtures
are required.
"""

import os
import tempfile

from utils.path_validation import (
    contains_dotdot_traversal,
    contains_path_traversal,
    is_invalid_name,
    is_safe_identifier,
)

# ---------------------------------------------------------------------------
# Minimal stub for _resolve_backup_path — mirrors the production logic in
# BulkOperationsMixin without requiring a full KnowledgeBase instance.
# ---------------------------------------------------------------------------


class _BackupPathStub:
    """Minimal stub exposing _resolve_backup_path with a configurable root."""

    def __init__(self, backup_root: str) -> None:
        self._backup_root = backup_root

    def _get_backup_dir(self, backup_dir):  # noqa: D102
        return self._backup_root

    def _resolve_backup_path(self, backup_file: str):
        """Mirrors BulkOperationsMixin._resolve_backup_path exactly."""
        allowed_root = os.path.realpath(self._get_backup_dir(None))
        resolved = os.path.realpath(backup_file)
        if resolved == allowed_root or resolved.startswith(allowed_root + os.sep):
            return resolved
        return None


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


class TestResolveBackupPath:
    """Tests for _resolve_backup_path containment logic (#9670 amendment).

    Uses _BackupPathStub to exercise the same realpath-containment algorithm
    as BulkOperationsMixin._resolve_backup_path without requiring a live KB.
    """

    # ------------------------------------------------------------------
    # accept: file inside the backup dir
    # ------------------------------------------------------------------

    def test_file_inside_backups_dir_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            stub = _BackupPathStub(root)
            target = os.path.join(root, "kb_backup_20260612.json")
            result = stub._resolve_backup_path(target)
            assert result == os.path.realpath(target)

    def test_nested_file_inside_backups_dir_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            subdir = os.path.join(root, "2026", "june")
            os.makedirs(subdir, exist_ok=True)
            stub = _BackupPathStub(root)
            target = os.path.join(subdir, "kb_backup_nested.json")
            result = stub._resolve_backup_path(target)
            assert result == os.path.realpath(target)

    # ------------------------------------------------------------------
    # reject: absolute path outside the backup dir
    # ------------------------------------------------------------------

    def test_etc_passwd_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            stub = _BackupPathStub(root)
            result = stub._resolve_backup_path("/etc/passwd")
            assert result is None

    def test_kb_backup_named_file_in_tmp_rejected(self):
        """A file named kb_backup_* in /tmp must be rejected by containment.

        Previously the basename `kb_backup_` check was the only guard in
        delete_backup; this test proves that check alone is not sufficient —
        containment must be applied first.
        """
        with tempfile.TemporaryDirectory() as root:
            stub = _BackupPathStub(root)
            # Craft a path that passes the basename guard but escapes containment.
            evil_path = "/tmp/kb_backup_evil.json"
            result = stub._resolve_backup_path(evil_path)
            assert result is None

    def test_sibling_directory_rejected(self):
        with tempfile.TemporaryDirectory() as parent:
            backup_dir = os.path.join(parent, "backups")
            os.makedirs(backup_dir)
            sibling = os.path.join(parent, "secrets", "kb_backup_steal.json")
            os.makedirs(os.path.dirname(sibling), exist_ok=True)
            stub = _BackupPathStub(backup_dir)
            result = stub._resolve_backup_path(sibling)
            assert result is None

    # ------------------------------------------------------------------
    # reject: prefix-collision — a dir whose name starts with the root path
    # but is not actually under it (e.g. /backup vs /backup-evil).
    # ------------------------------------------------------------------

    def test_prefix_collision_rejected(self):
        with tempfile.TemporaryDirectory() as parent:
            backup_dir = os.path.join(parent, "backup")
            evil_dir = os.path.join(parent, "backup-evil")
            os.makedirs(backup_dir)
            os.makedirs(evil_dir)
            stub = _BackupPathStub(backup_dir)
            evil_file = os.path.join(evil_dir, "kb_backup_x.json")
            result = stub._resolve_backup_path(evil_file)
            assert result is None

    # ------------------------------------------------------------------
    # reject: symlink inside the backup dir pointing outside (escape).
    # realpath() resolves the symlink target, so the containment check
    # compares against the real destination — which is outside the root.
    # ------------------------------------------------------------------

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with tempfile.TemporaryDirectory() as outside:
                # Create a real file outside the backup directory.
                outside_file = os.path.join(outside, "secret.json")
                with open(outside_file, "w", encoding="utf-8") as fh:
                    fh.write("{}")

                # Create a symlink inside the backup dir → outside file.
                link_path = os.path.join(root, "kb_backup_via_symlink.json")
                os.symlink(outside_file, link_path)

                stub = _BackupPathStub(root)
                result = stub._resolve_backup_path(link_path)
                # realpath() resolves the link to outside_file which is not
                # under root, so the result must be None.
                assert result is None
