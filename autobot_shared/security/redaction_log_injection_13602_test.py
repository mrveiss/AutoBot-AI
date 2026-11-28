# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The path-traversal log line may not carry raw attacker input (#13602).

Two halves, because either alone passes while the defect is live:

* the **behaviour** of :func:`sanitize_log_value` — a CRLF, an ANSI escape or a
  megabyte of padding stops being able to author log records;
* the **call site** in the codebase-analytics env endpoint, read as an AST. The
  triage this came from claimed the log fires "unconditionally"; it does not,
  it sits in ``except ValueError``. The defect is the raw ``path`` argument, so
  the guard must assert what is *passed*, not that the file mentions a helper.

The guard is AST-only on purpose. ``grep sanitize_log_value`` over this very
file would pass today and would keep passing after someone reverted the fix and
left the comment behind -- so a contrast fixture, where the name appears only
in a docstring and a comment, is asserted *not* to satisfy it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from autobot_shared.security.redaction import LOG_VALUE_MAX_CHARS, sanitize_log_value

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENDPOINT = _REPO_ROOT / "autobot-backend" / "api" / "codebase_analytics" / "endpoints" / "environment.py"
_GUARDED_FUNCTION = "_validate_env_path_security"


class TestSanitizeLogValue:
    def test_a_crlf_can_no_longer_start_a_record(self):
        out = sanitize_log_value("ok\r\n2026-01-01 12:00:00 ERROR forged")
        assert "\r" not in out and "\n" not in out
        assert "\\x0d\\x0a" in out

    def test_an_ansi_escape_is_neutralised(self):
        assert "\x1b" not in sanitize_log_value("\x1b[2J\x1b[31mwiped")

    def test_unicode_line_and_bidi_separators_are_neutralised(self):
        out = sanitize_log_value("a\u2028b\u202ec")
        assert "\u2028" not in out and "\u202e" not in out

    def test_an_oversized_value_cannot_pad_the_line(self):
        out = sanitize_log_value("A" * (LOG_VALUE_MAX_CHARS + 500))
        assert len(out) < LOG_VALUE_MAX_CHARS + 60
        assert "truncated" in out

    def test_an_ordinary_path_is_returned_unchanged(self):
        """Over-masking would destroy the diagnostic the log line exists for."""
        assert sanitize_log_value("../../etc/passwd") == "../../etc/passwd"

    def test_a_non_string_does_not_raise(self):
        assert sanitize_log_value(None) == "None"


def _warning_calls_in(tree: ast.AST, function_name: str) -> list[ast.Call]:
    """Every ``logger.warning``/``error``/``info`` call inside *function_name*."""
    target = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
        ),
        None,
    )
    assert target is not None, f"{function_name} is gone — re-point this guard, do not delete it"
    return [
        node
        for node in ast.walk(target)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"warning", "error", "info", "debug"}
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
    ]


_SANITISER = "sanitize_log_value"


def _is_sanitiser_call(node: ast.AST) -> bool:
    """True only for ``sanitize_log_value(...)``, plain or attribute-qualified."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id == _SANITISER
    return isinstance(node.func, ast.Attribute) and node.func.attr == _SANITISER


def _every_logged_argument_is_sanitised(source: str, function_name: str) -> bool:
    """True when every interpolated value goes through ``sanitize_log_value``.

    #13602 review: this accepted *any* ``ast.Call`` as evidence of sanitising, so
    ``logger.warning("...%s", str(path))`` satisfied it while the raw path still reached the
    log store. It also never looked at the format string, so ``logger.warning(f"...{path}")``
    passed by leaving no positional arguments to check — the guard was green on both of the
    two shapes this defect actually takes.
    """
    calls = _warning_calls_in(ast.parse(source), function_name)
    if not calls:
        return False
    for call in calls:
        if not call.args:
            return False
        fmt = call.args[0]
        if isinstance(fmt, ast.JoinedStr):
            # An f-string interpolates before the logger is called, so an unsanitised piece
            # is already in the message regardless of the remaining arguments.
            if any(
                isinstance(piece, ast.FormattedValue) and not _is_sanitiser_call(piece.value) for piece in fmt.values
            ):
                return False
        elif not isinstance(fmt, ast.Constant):
            return False
        for argument in call.args[1:]:
            if _is_sanitiser_call(argument) or isinstance(argument, ast.Constant):
                continue
            return False
    return True


_CONTRAST_FIXTURE = '''
def _validate_env_path_security(path, project_root):
    """Validate the path.

    Untrusted input is passed through sanitize_log_value before logging.
    """
    try:
        validate_path(path)
    except ValueError:
        # sanitize_log_value(path) keeps CRLF out of the log store
        logger.warning("Path traversal attempt blocked: %s", path)
'''


#: The raw value wrapped in some *other* call. `str(path)` is an `ast.Call`, which the
#: pre-review guard accepted as proof of sanitising.
_STR_WRAPPED_FIXTURE = """
def _validate_env_path_security(path, project_root):
    try:
        validate_path(path)
    except ValueError:
        logger.warning("Path traversal attempt blocked: %s", str(path))
"""

#: The raw value interpolated by an f-string, leaving no positional argument to inspect.
_FSTRING_FIXTURE = """
def _validate_env_path_security(path, project_root):
    try:
        validate_path(path)
    except ValueError:
        logger.warning(f"Path traversal attempt blocked: {path}")
"""


class TestTheCallSiteIsGuarded:
    def test_the_log_line_sits_inside_the_except_not_at_the_top(self):
        """The triage said "unconditional". It is not — assert the real shape.

        Repeating a wrong claim in a guard is how a wrong claim becomes
        permanent, so the structural fact is pinned rather than restated.
        """
        source = _ENDPOINT.read_text(encoding="utf-8")
        function = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == _GUARDED_FUNCTION
        )
        handlers = [node for node in ast.walk(function) if isinstance(node, ast.ExceptHandler)]
        assert handlers, "the validation failure path is gone"
        logged_in_handler = [
            node
            for handler in handlers
            for node in ast.walk(handler)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "warning"
        ]
        assert len(logged_in_handler) == len(_warning_calls_in(ast.parse(source), _GUARDED_FUNCTION))

    def test_no_raw_value_reaches_the_log_call(self):
        assert _every_logged_argument_is_sanitised(_ENDPOINT.read_text(encoding="utf-8"), _GUARDED_FUNCTION)

    def test_prose_naming_the_helper_does_not_satisfy_the_guard(self):
        """The contrast fixture: the string is present, the call is not.

        Eleven guards here have been satisfied by a comment carrying the name
        they looked for. This asserts the detector is not one of them.
        """
        assert "sanitize_log_value" in _CONTRAST_FIXTURE
        assert not _every_logged_argument_is_sanitised(_CONTRAST_FIXTURE, _GUARDED_FUNCTION)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
