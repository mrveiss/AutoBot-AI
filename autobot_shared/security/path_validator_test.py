# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for path_validator security utilities (#2162).

Covers validate_path() and validate_relative_path() — security-critical
functions used across 16+ backend files for path injection prevention.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autobot_shared.security.path_validator import (
    _DEFAULT_ALLOWED_ROOTS,
    PROJECT_ALLOWED_ROOTS,
    SandboxPathError,
    require_path_string,
    resolve_within_sandbox,
    validate_path,
    validate_relative_path,
)

# =============================================================================
# validate_path
# =============================================================================


class TestValidatePath:
    """Tests for validate_path()."""

    def test_tmp_path_rejected_by_default(self, tmp_path) -> None:
        """#15238: a path under a world-writable shared root (/tmp, and
        pytest's tmp_path lives under it on Linux) is rejected when the
        caller passes no explicit allowed_roots.

        Contrast: reintroducing "/tmp" into _DEFAULT_ALLOWED_ROOTS makes
        this pass again -- that regression is exactly what this test pins.
        """
        with pytest.raises(ValueError, match="outside allowed directories"):
            validate_path(str(tmp_path / "file.txt"))

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
            validate_path("/tmp/file\x00.txt")  # nosec B108  # test/controlled code uses tmpdir intentionally

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

    def test_default_allowed_roots_excludes_tmp(self) -> None:
        """#15238: /tmp is world-writable and shared with every other
        process on the host, so it must never be a default fallback root --
        only an explicit, deliberate choice at a call site.
        """
        assert "/tmp" not in _DEFAULT_ALLOWED_ROOTS  # nosec B108

    def test_project_allowed_roots_excludes_tmp(self) -> None:
        """#15238: the shared "inside the AutoBot project" root that
        call sites opt into explicitly must never resolve to /tmp either.
        """
        assert "/tmp" not in PROJECT_ALLOWED_ROOTS  # nosec B108
        assert len(PROJECT_ALLOWED_ROOTS) == 1

    def test_default_allowed_roots_used_when_none(self) -> None:
        """When allowed_roots is None, _DEFAULT_ALLOWED_ROOTS is used."""
        with pytest.raises(ValueError, match="outside allowed directories"):
            # Test/controlled code uses tmpdir intentionally.
            validate_path("/tmp/test_path_validator_check")  # nosec B108

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


class TestValidatePathEncodedTraversal:
    """#14050: os.path.realpath never decodes or Unicode-normalizes, so a
    percent-encoded or Unicode-confusable ``..`` never became a real ``..``
    — it stayed an inert, nonexistent literal filename. That was never an
    exploitable escape by itself, but ``validate_path``'s containment check
    still needs a canonical string to check: without normalizing first, a
    root that happens to contain the caller's cwd (any checkout-relative
    root, e.g. the filesystem MCP bridge's ``config.base_dir`` allowlist)
    lets that literal, nonexistent-but-in-bounds filename satisfy
    containment.

    An earlier version of this fix denylisted the raw/partially-decoded
    string outright, which also rejected legitimate in-bounds ``..``
    navigation and filenames literally containing ``..`` — a false-positive
    regression across 20+ callers (git_mcp.py, npu_code_search_agent.py, the
    codebase_analytics endpoints, long_running_operations.py) that
    legitimately walk arbitrary repository trees. The fix instead
    canonicalizes *before* the one containment check and lets that check be
    the sole authority in both directions, exactly like it already was for
    a literal, undisguised ``..``.
    """

    @pytest.mark.parametrize(
        "attack_path",
        [
            "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "..%2f..%2f..%2fetc%2fpasswd",
            "%2e%2e/%2e%2e/%2e%2e/etc/passwd",
            "%252e%252e%252f%252e%252e%252fetc%252fpasswd",
            "../../etc/passwd",
            "﹒﹒/﹒﹒/etc/passwd",
            "‥/‥/etc/passwd",
        ],
    )
    def test_disguised_traversal_rejected_even_inside_cwd(self, tmp_path, attack_path, monkeypatch) -> None:
        """The allowed root deliberately includes cwd — the case that let a
        disguised traversal satisfy containment before canonicalization,
        because the raw/decoded string never resolved to a real out-of-
        bounds path in the first place."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="outside allowed directories"):
            validate_path(attack_path, allowed_roots=[str(tmp_path)])

    def test_legitimate_path_with_single_dot_segment_still_resolves(self, tmp_path) -> None:
        """'.' is not '..' — an ordinary relative reference to cwd itself is
        untouched by canonicalization."""
        target = tmp_path / "file.txt"
        target.write_text("data", encoding="utf-8")

        result = validate_path(f"{tmp_path}/./file.txt", allowed_roots=[str(tmp_path)])

        assert result == target.resolve()

    def test_in_bounds_dotdot_navigation_accepted(self, tmp_path) -> None:
        """The false-positive this pins: 'a/../b/file.txt' resolves to a real
        in-bounds file and must be ACCEPTED, not denylisted on sight."""
        (tmp_path / "a").mkdir()
        b_dir = tmp_path / "b"
        b_dir.mkdir()
        target = b_dir / "file.txt"
        target.write_text("data", encoding="utf-8")

        result = validate_path(f"{tmp_path}/a/../b/file.txt", allowed_roots=[str(tmp_path)])

        assert result == target.resolve()

    def test_literal_dotdot_in_filename_accepted(self, tmp_path) -> None:
        """A real filename containing '..' (not a path segment) must be
        ACCEPTED — the denylist this replaced rejected it outright."""
        target = tmp_path / "notes..final.txt"
        target.write_text("data", encoding="utf-8")

        result = validate_path(str(target), allowed_roots=[str(tmp_path)])

        assert result == target.resolve()

    def test_symlink_escape_still_rejected(self, tmp_path) -> None:
        """A symlink pointing outside the root carries no '..' at all — the
        pre-existing realpath+containment check this canonicalization sits
        in front of already caught it, and still must."""
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        link = allowed / "escape"
        link.symlink_to("/etc")

        with pytest.raises(ValueError, match="outside allowed directories"):
            validate_path(str(link / "passwd"), allowed_roots=[str(allowed)])

    def test_percent_encoded_null_byte_rejected(self, tmp_path) -> None:
        """A null byte smuggled in via '%00' only exists after decoding —
        checked again post-canonicalization so it can't bypass the
        pre-decode check the same way an encoded '..' used to."""
        with pytest.raises(ValueError, match="empty or contains null bytes"):
            validate_path(f"{tmp_path}/file.txt%00.png", allowed_roots=[str(tmp_path)])


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
            validate_relative_path("", "/tmp/base")  # nosec B108  # test/controlled code uses tmpdir intentionally

    def test_null_byte_in_segment_raises(self) -> None:
        """Null byte in segment raises ValueError."""
        with pytest.raises(ValueError, match="empty or contains null bytes"):
            validate_relative_path(
                "file\x00.txt",
                # Test/controlled code uses tmpdir intentionally.
                "/tmp/base",  # nosec B108
            )

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


# =============================================================================
# resolve_within_sandbox (shared sandbox resolver, #11844 / #11823)
# =============================================================================


class TestResolveWithinSandbox:
    """Tests for the shared sandbox resolver behind files.py + sandbox_files.py."""

    @pytest.mark.parametrize("root_path", ["", "/", "//"])
    def test_root_addressing_returns_root(self, tmp_path, root_path) -> None:
        """'' and '/' (and '//') address the sandbox root itself (#11823)."""
        assert resolve_within_sandbox(root_path, tmp_path) == tmp_path

    def test_normal_relative_path_resolves_under_root(self, tmp_path) -> None:
        """A simple relative sub-path resolves within the root."""
        result = resolve_within_sandbox("subdir/file.txt", tmp_path)
        assert result == (tmp_path / "subdir" / "file.txt").resolve()

    def test_leading_slash_stripped_then_resolved(self, tmp_path) -> None:
        """Leading/trailing slashes are stripped, not treated as escape."""
        result = resolve_within_sandbox("/subdir/file.txt/", tmp_path)
        assert result == (tmp_path / "subdir" / "file.txt").resolve()

    @pytest.mark.parametrize(
        "evil",
        ["../etc/passwd", "foo/../../etc", "~/secrets", "a<b", 'a"b', "a|b", "a?b", "a*b"],
    )
    def test_traversal_rejected(self, tmp_path, evil) -> None:
        """Traversal / invalid-character inputs raise SandboxPathError."""
        with pytest.raises(SandboxPathError, match="path traversal not allowed"):
            resolve_within_sandbox(evil, tmp_path)

    def test_encoded_traversal_rejected(self, tmp_path) -> None:
        """URL-encoded traversal is caught after decoding."""
        with pytest.raises(SandboxPathError, match="encoded traversal not allowed"):
            resolve_within_sandbox("%2e%2e/etc", tmp_path)

    def test_double_encoded_traversal_rejected(self, tmp_path) -> None:
        """#14050: a single unquote() pass left %252e%252e undecoded; the
        shared _canonicalize helper now decodes to a fixed point instead."""
        with pytest.raises(SandboxPathError, match="encoded traversal not allowed"):
            resolve_within_sandbox("%252e%252e%252fetc", tmp_path)

    def test_unicode_confusable_traversal_rejected(self, tmp_path) -> None:
        """#14050: Unicode dot look-alikes (e.g. SMALL FULL STOP) NFKC-normalize
        to ASCII '..'. The raw string carries no literal '..', so this only
        the second (decode/normalize) check catches it."""
        with pytest.raises(SandboxPathError, match="encoded traversal not allowed"):
            resolve_within_sandbox("﹒﹒/etc", tmp_path)

    def test_null_byte_rejected_as_outside_sandbox(self, tmp_path) -> None:
        """A null byte reaches validate_relative_path and surfaces as outside-sandbox."""
        with pytest.raises(SandboxPathError, match="outside sandbox not allowed"):
            resolve_within_sandbox("file\x00.txt", tmp_path)

    def test_error_is_valueerror_subclass(self) -> None:
        """SandboxPathError remains a ValueError for compatibility."""
        assert issubclass(SandboxPathError, ValueError)


# =============================================================================
# require_path_string — boundary check against non-path values (#14217)
# =============================================================================


class TestRequirePathString:
    """A sanitizer that stringifies whatever it is given turns junk into a
    real, creatable directory tree (an object repr, or a MagicMock whose
    default __fspath__ embeds "/" separators). This is the boundary check
    that rejects it before it ever reaches Path()/os.makedirs.
    """

    def test_str_value_accepted_unchanged(self) -> None:
        assert require_path_string("data/chats", context="test") == "data/chats"

    def test_path_value_accepted_and_stringified(self, tmp_path) -> None:
        result = require_path_string(tmp_path, context="test")
        assert result == str(tmp_path)
        assert isinstance(result, str)

    def test_magicmock_rejected_with_typeerror(self) -> None:
        """The real reproduction: an object, not a crafted string.

        Path(MagicMock()) never raises — its default __fspath__ embeds "/"
        separators and silently becomes a multi-component path. This must
        raise instead.
        """
        mock = MagicMock(name="mock.unified_config_manager.get().get().get()")

        with pytest.raises(TypeError, match="expected a str or Path"):
            require_path_string(mock, context="paths.data.file_manager_root")

    def test_arbitrary_object_rejected_with_typeerror(self) -> None:
        with pytest.raises(TypeError, match="expected a str or Path"):
            require_path_string(object(), context="test")

    def test_int_rejected_with_typeerror(self) -> None:
        with pytest.raises(TypeError, match="expected a str or Path"):
            require_path_string(123, context="test")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty or contains a null byte"):
            require_path_string("", context="test")

    def test_null_byte_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty or contains a null byte"):
            require_path_string("data/file\x00.txt", context="test")

    def test_error_message_includes_context(self) -> None:
        """The context string points at the misconfigured setting."""
        with pytest.raises(TypeError, match="settings.backup_dir"):
            require_path_string(MagicMock(), context="settings.backup_dir")


class TestRejectionBeforeThePathExpression:
    """The escaping shapes are refused before the path is built (#15786).

    The containment check was already sound — `realpath` both sides, then
    `relative_to` raises on escape. What it was not was *legible*: the
    sanitisation is a post-condition on the sink rather than a pre-condition on
    the input, which is what `py/path-injection` objects to and what makes a
    reader check the order twice. These are defence in depth; the barrier below
    them is unchanged and still tested.
    """

    def test_a_parent_reference_is_refused_up_front(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="parent reference"):
            validate_relative_path("../escape.txt", tmp_path)

    def test_a_parent_reference_mid_path_is_refused(self, tmp_path) -> None:
        """`a/../../b` normalises out of the base only after resolution."""
        with pytest.raises(ValueError, match="parent reference"):
            validate_relative_path("a/../../b.txt", tmp_path)

    def test_an_absolute_segment_says_what_actually_happened(self, tmp_path) -> None:
        """pathlib discards the base for an absolute right-hand side, so nothing
        traversed out — the base was never involved."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_relative_path("/etc/passwd", tmp_path)

    def test_a_legitimate_nested_segment_still_resolves(self, tmp_path) -> None:
        """The contrast: refusing everything would satisfy every test above."""
        resolved = validate_relative_path("sub/dir/file.txt", tmp_path)

        assert str(resolved).startswith(str(tmp_path.resolve()))
        assert resolved.name == "file.txt"

    def test_a_filename_containing_dots_is_not_a_parent_reference(self, tmp_path) -> None:
        """`..weird.txt` is a filename, not a traversal."""
        resolved = validate_relative_path("..weird.txt", tmp_path)

        assert resolved.name == "..weird.txt"

    def test_the_containment_check_still_catches_a_symlink_escape(self, tmp_path) -> None:
        """The barrier the pre-checks cannot replace.

        A symlink *inside* the base pointing out of it passes every syntactic
        check — it has no `..`, it is not absolute — and only `realpath` reveals
        where it leads. This is why the containment check is retained rather
        than replaced.
        """
        outside = tmp_path.parent / "outside_target"
        outside.mkdir(exist_ok=True)
        base = tmp_path / "base"
        base.mkdir()
        (base / "link").symlink_to(outside, target_is_directory=True)

        with pytest.raises(ValueError, match="escapes base directory"):
            validate_relative_path("link/secret.txt", base)
