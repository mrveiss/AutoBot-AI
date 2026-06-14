#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for tools/lint/check_no_src_mock_path.py (#7165 / #6987 AC3)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent / "check_no_src_mock_path.py"
_SPEC = importlib.util.spec_from_file_location("check_src_mock_path", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
hook = importlib.util.module_from_spec(_SPEC)
sys.modules["check_src_mock_path"] = hook
_SPEC.loader.exec_module(hook)


def _scan(source: str, name: str = "fake_test.py") -> list[tuple[int, str]]:
    return hook._scan_file(Path(name), source)


# ---------------------------------------------------------------------------
# Banned patterns: patch("src.*") in all forms
# ---------------------------------------------------------------------------


def test_flags_patch_with_src_prefix() -> None:
    """The canonical bug: ``patch("src.foo.bar")`` from #6987."""
    src = """
from unittest.mock import patch

def test_foo():
    with patch("src.module.func", return_value=1):
        pass
"""
    findings = _scan(src)
    assert len(findings) == 1
    assert "src.module.func" in findings[0][1]
    assert "#6987" in findings[0][1]


def test_flags_qualified_mock_patch() -> None:
    """``mock.patch("src.…")`` — qualified import form."""
    src = """
from unittest import mock

def test_foo():
    with mock.patch("src.foo.bar"):
        pass
"""
    findings = _scan(src)
    assert len(findings) == 1
    assert "src.foo.bar" in findings[0][1]


def test_flags_fully_qualified_unittest_mock_patch() -> None:
    """``unittest.mock.patch("src.…")`` — fully qualified."""
    src = """
import unittest.mock

def test_foo():
    with unittest.mock.patch("src.foo.bar"):
        pass
"""
    findings = _scan(src)
    assert len(findings) == 1


def test_flags_patch_object_with_src_target() -> None:
    """``patch.object("src.…")`` — object form. Less common but valid syntax."""
    src = """
from unittest.mock import patch

def test_foo():
    with patch.object("src.module", "attr"):
        pass
"""
    findings = _scan(src)
    assert len(findings) == 1


def test_flags_kwarg_target() -> None:
    """``patch(target="src.…")`` — keyword form."""
    src = """
from unittest.mock import patch

def test_foo():
    with patch(target="src.module.func"):
        pass
"""
    findings = _scan(src)
    assert len(findings) == 1
    assert "src.module.func" in findings[0][1]


def test_flags_multiple_violations_in_one_file() -> None:
    """Hook reports each violation separately."""
    src = """
from unittest.mock import patch

def test_a():
    with patch("src.alpha"):
        pass

def test_b():
    with patch("src.beta"):
        pass
"""
    findings = _scan(src)
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# Negative cases — should NOT flag
# ---------------------------------------------------------------------------


def test_does_not_flag_legitimate_patch_paths() -> None:
    """``patch("autobot_backend.foo")`` is the correct form — must not flag."""
    src = """
from unittest.mock import patch

def test_foo():
    with patch("autobot_backend.module.func"):
        pass
"""
    assert _scan(src) == []


def test_does_not_flag_paths_containing_src_substring_elsewhere() -> None:
    """Paths like ``foo.src_helper`` shouldn't trip — only the ``src.`` prefix."""
    src = """
from unittest.mock import patch

def test_foo():
    with patch("foo.src_helper"):
        pass

def test_bar():
    with patch("module.with.src.in.middle"):
        pass
"""
    assert _scan(src) == []


def test_does_not_flag_dynamic_target() -> None:
    """``patch(SOME_CONST)`` — non-literal, can't statically resolve."""
    src = """
from unittest.mock import patch

TARGET = "src.module.foo"

def test_foo():
    with patch(TARGET):
        pass
"""
    # Hook only flags string-literal targets — dynamic refs out of scope.
    assert _scan(src) == []


def test_does_not_flag_patch_dict() -> None:
    """``patch.dict(...)`` patches mappings, not import targets — different semantic."""
    src = """
from unittest.mock import patch

def test_foo():
    with patch.dict("src.module.CONFIG", {"key": "val"}):
        pass
"""
    # patch.dict mutates a mapping; "src." here would be a dict-import attribute,
    # not a module-resolution target. Out of scope for this hook.
    assert _scan(src) == []


def test_does_not_flag_syntax_error_files() -> None:
    """Files with syntax errors are skipped silently — other linters handle them."""
    src = """
from unittest.mock import patch

def test_foo(:  # syntax error
    with patch("src.foo"):
        pass
"""
    assert _scan(src) == []


# ---------------------------------------------------------------------------
# File-name scoping
# ---------------------------------------------------------------------------


def test_test_file_predicate_for_underscore_test_suffix() -> None:
    assert hook._is_test_file("autobot-backend/foo_test.py") is True


def test_test_file_predicate_for_test_underscore_prefix() -> None:
    assert hook._is_test_file("autobot-backend/tests/test_foo.py") is True


def test_test_file_predicate_rejects_non_test_files() -> None:
    assert hook._is_test_file("autobot-backend/api/marketplace.py") is False
    assert hook._is_test_file("autobot-backend/utils/testing_helpers.py") is False


# ---------------------------------------------------------------------------
# Runtime resolution checks
# ---------------------------------------------------------------------------


def test_resolve_module_with_builtin() -> None:
    """Builtin modules like ``sys`` should resolve."""
    resolves, error = hook._resolve_module("sys")
    assert resolves is True
    assert error is None


def test_resolve_module_with_nonexistent() -> None:
    """Non-existent modules should fail resolution."""
    resolves, error = hook._resolve_module("this_module_definitely_does_not_exist_xyz123")
    assert resolves is False
    assert error is not None
    assert "not found" in error.lower() or "resolution error" in error.lower()


def test_resolve_module_caches_results() -> None:
    """Module resolution results should be cached."""
    # Clear cache first
    hook._RESOLUTION_CACHE.clear()

    target = "sys.nonexistent"
    # First call populates cache
    resolves1, error1 = hook._resolve_module(target)
    # Second call hits cache
    resolves2, error2 = hook._resolve_module(target)

    assert resolves1 == resolves2
    assert error1 == error2
    # Verify it was cached
    assert target in hook._RESOLUTION_CACHE


def test_resolve_module_handles_empty_string() -> None:
    """Empty module strings should return unresolvable."""
    resolves, error = hook._resolve_module("")
    assert resolves is False
    assert error is not None


def test_resolution_works_with_builtins() -> None:
    """Verify resolution check can detect builtin modules."""
    resolves, error = hook._resolve_module("sys")
    assert resolves is True
    assert error is None


def test_src_prefix_takes_precedence_over_resolution() -> None:
    """Even if src.* target resolved, it should be flagged for #6987."""
    src = """
from unittest.mock import patch

def test_foo():
    # If 'src' were a valid package, this would resolve, but we still flag it.
    with patch("src.something"):
        pass
"""
    findings = _scan(src)
    assert len(findings) == 1
    assert "src.something" in findings[0][1]
    assert "#6987" in findings[0][1]  # Should reference the original issue
