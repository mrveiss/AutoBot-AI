# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for path_validator security utilities (#2162).

Covers validate_path() and validate_relative_path() — security-critical
functions used across 16+ backend files for path injection prevention.
"""

from pathlib import Path

import pytest

from autobot_shared.security.path_validator import (
    _DEFAULT_ALLOWED_ROOTS,
    validate_path,
    validate_relative_path,
)

# =============================================================================
# validate_path
# =============================================================================


class TestValidatePath:
    """Tests for validate_path()."""

    def test_valid_path_under_default_root(self, tmp_path) -> None:
        """Path under /tmp (a default root) resolves successfully."""
        result = validate_path(str(tmp_path / "file.txt"))
        assert isinstance(result, Path)

    def test_valid_path_under_custom_root(self, tmp_path) -> None:
        """Path under a custom allowed root resolves successfully."""
        result = validate_path(
            str(tmp_path / "data.json"),
            allowed_roots=[str(tmp_path)],
        )
        assert result == (tmp_path / "data.json").resolve()

    def test_traversal_escapes_all_roots(self, tmp_path) -> None:
        """Path traversal escaping all allowed roots raises ValueError."""
        with pytest.raises(ValueError, match="outside allowed directories"):
            validate_path(
                "../../etc/passwd",
                allowed_roots=[str(tmp_path)],
            )

    def test_empty_path_raises(self) -> None:
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="empty or contains null bytes"):
            validate_path("")

    def test_null_byte_raises(self) -> None:
        """Null byte in path raises ValueError."""
        with pytest.raises(ValueError, match="empty or contains null bytes"):
            validate_path("/tmp/file\x00.txt")  # nosec B108 - test/controlled code uses tmpdir intentionally

    def test_must_exist_with_nonexistent_path(self, tmp_path) -> None:
        """must_exist=True with nonexistent path raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            validate_path(
                str(tmp_path / "nonexistent.txt"),
                allowed_roots=[str(tmp_path)],
                must_exist=True,
            )

    def test_must_exist_with_existing_path(self, tmp_path) -> None:
        """must_exist=True with existing path succeeds."""
        target = tmp_path / "exists.txt"
        target.write_text("data", encoding="utf-8")
        result = validate_path(
            str(target),
            allowed_roots=[str(tmp_path)],
            must_exist=True,
        )
        assert result == target.resolve()

    def test_multiple_roots_second_matches(self, tmp_path) -> None:
        """Path under the second of two allowed roots succeeds."""
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        target = root_b / "file.txt"

        result = validate_path(
            str(target),
            allowed_roots=[str(root_a), str(root_b)],
        )
        assert result == target.resolve()

    def test_path_outside_all_roots_no_path_leakage(self, tmp_path) -> None:
        """Error message does not leak the resolved path."""
        with pytest.raises(ValueError) as exc_info:
            validate_path(
                "/etc/shadow",
                allowed_roots=[str(tmp_path)],
            )
        assert "/etc/shadow" not in str(exc_info.value)

    def test_absolute_path_outside_roots(self, tmp_path) -> None:
        """Absolute path outside allowed roots raises."""
        with pytest.raises(ValueError, match="outside allowed directories"):
            validate_path(
                "/etc/passwd",
                allowed_roots=[str(tmp_path)],
            )

    def test_default_allowed_roots_used_when_none(self) -> None:
        """When allowed_roots is None, _DEFAULT_ALLOWED_ROOTS is used."""
        assert "/tmp" in _DEFAULT_ALLOWED_ROOTS  # nosec B108 - test/controlled code uses tmpdir intentionally
        result = validate_path(
            "/tmp/test_path_validator_check"
        )  # nosec B108 - test/controlled code uses tmpdir intentionally
        assert str(result).startswith("/tmp")  # nosec B108 - test/controlled code uses tmpdir intentionally

    def test_symlink_escape(self, tmp_path) -> None:
        """Symlink pointing outside base directory is caught by realpath."""
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        link = allowed / "escape"
        link.symlink_to("/etc")

        with pytest.raises(ValueError, match="outside allowed directories"):
            validate_path(
                str(link / "passwd"),
                allowed_roots=[str(allowed)],
            )


# =============================================================================
# validate_relative_path
# =============================================================================


class TestValidateRelativePath:
    """Tests for validate_relative_path()."""

    def test_normal_filename(self, tmp_path) -> None:
        """Simple filename resolves to base_dir / filename."""
        result = validate_relative_path("file.txt", tmp_path)
        assert result == (tmp_path / "file.txt").resolve()

    def test_subdirectory_path(self, tmp_path) -> None:
        """Relative sub-path stays within base."""
        result = validate_relative_path("sub/dir/file.txt", tmp_path)
        expected = (tmp_path / "sub" / "dir" / "file.txt").resolve()
        assert result == expected

    def test_traversal_raises(self, tmp_path) -> None:
        """../../etc/passwd raises ValueError."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_relative_path("../../etc/passwd", tmp_path)

    def test_empty_segment_raises(self) -> None:
        """Empty segment raises ValueError."""
        with pytest.raises(ValueError, match="empty or contains null bytes"):
            validate_relative_path("", "/tmp/base")  # nosec B108 - test/controlled code uses tmpdir intentionally

    def test_null_byte_in_segment_raises(self) -> None:
        """Null byte in segment raises ValueError."""
        with pytest.raises(ValueError, match="empty or contains null bytes"):
            validate_relative_path(
                "file\x00.txt", "/tmp/base"
            )  # nosec B108 - test/controlled code uses tmpdir intentionally

    def test_absolute_path_as_segment(self, tmp_path) -> None:
        """Absolute path as segment escapes base and raises."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_relative_path("/etc/passwd", tmp_path)

    def test_must_exist_nonexistent(self, tmp_path) -> None:
        """must_exist=True with nonexistent file raises."""
        with pytest.raises(ValueError, match="does not exist"):
            validate_relative_path("ghost.txt", tmp_path, must_exist=True)

    def test_must_exist_existing(self, tmp_path) -> None:
        """must_exist=True with existing file succeeds."""
        target = tmp_path / "real.txt"
        target.write_text("content", encoding="utf-8")
        result = validate_relative_path("real.txt", tmp_path, must_exist=True)
        assert result == target.resolve()

    def test_symlink_escape_from_base(self, tmp_path) -> None:
        """Symlink inside base pointing outside is caught."""
        base = tmp_path / "base"
        base.mkdir()
        link = base / "escape_link"
        link.symlink_to("/etc")

        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_relative_path("escape_link/passwd", base)

    def test_base_dir_as_path_object(self, tmp_path) -> None:
        """base_dir can be a Path object (not just str)."""
        result = validate_relative_path("file.txt", Path(tmp_path))
        assert isinstance(result, Path)

    def test_dot_segment_stays_in_base(self, tmp_path) -> None:
        """'./file.txt' resolves within base."""
        result = validate_relative_path("./file.txt", tmp_path)
        assert result == (tmp_path / "file.txt").resolve()
