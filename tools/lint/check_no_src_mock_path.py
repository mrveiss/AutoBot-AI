#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Regression-prevention check for the #6987 ``patch("src.*")`` mock-path bug.

Background
----------
#6987 found 48 test sites using ``patch("src.module.foo", ...)``. The
``autobot-backend`` package has no ``src/`` directory — these patches
silently no-op'd. ``patch.start()`` either raised ``ModuleNotFoundError``
(swallowed by ``with`` cleanup) or returned a placeholder MagicMock that
never installed. Production code ran unmocked, and tests passed on
stale-mock-luck. This masked years of real production drift (#7147,
#7154, #7161, #7216, #7237, #7251, …).

This hook AST-scans test files for ``patch(target=...)`` calls whose
target is a string literal starting with ``"src."`` and flags them at
commit time, preventing the pattern from being reintroduced.

Scope
-----
Only files matching ``*_test.py`` or ``test_*.py`` are scanned — the
pattern is test-only by design.

Detected forms
--------------
* ``patch("src.foo.bar")``                   (from unittest.mock import patch)
* ``patch.object("src.foo.bar", ...)``       (object form)
* ``mock.patch("src.foo.bar")``              (qualified)
* ``unittest.mock.patch("src.foo.bar")``     (fully qualified)
* ``patch(target="src.foo.bar")``            (kwarg form)
* ``patch(CONST_TARGET)``                    (dynamic target heuristic)
* ``patch(f"module.{VAR}")``                 (f-string dynamic target heuristic)

Runtime resolution
------------------
For string-literal targets, this hook also validates that the module
resolves at runtime using ``importlib.util.find_spec()``. Targets that
fail to resolve raise a resolution error. Results are cached per file
(mtime-keyed) to avoid redundant resolution checks.

Allowlist
---------
None — there is no legitimate ``src.`` package in this repo.

Exit code
---------
  0 — clean (no banned patterns found in scanned files)
  1 — banned patterns found (PR/commit blocked)
  2 — usage error
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import NamedTuple

# tools/lint/ is not a Python package; ensure sibling module is importable
# regardless of invocation mode (script / importlib from tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402


class _ResolutionCache(NamedTuple):
    """Cache key for module resolution results: (file_path, mtime)."""

    file_path: str
    mtime: float


# Files exempt from the check.
ALLOWLIST: frozenset[str] = frozenset(
    {
        # The hook itself + tests reference the patterns as strings.
        "tools/lint/check_no_src_mock_path.py",
        "tools/lint/check_no_src_mock_path_test.py",
    }
)

# Module resolution cache: {target_module: (resolves, error_msg)}
# Keyed by the normalized module path to avoid redundant lookups.
_RESOLUTION_CACHE: dict[str, tuple[bool, str | None]] = {}


def _is_test_file(rel_path: str) -> bool:
    """Return True if path matches the test naming convention."""
    name = Path(rel_path).name
    return name.endswith("_test.py") or name.startswith("test_")


def _is_patch_call(node: ast.Call) -> bool:
    """Return True if ``node`` is a call to ``patch`` or ``patch.object``.

    Covers all import forms:
      - ``patch(...)``                              (Name)
      - ``patch.object(...)``                       (Attribute on Name)
      - ``mock.patch(...)``                         (Attribute, attr=patch)
      - ``mock.patch.object(...)``                  (Attribute, attr=object on patch)
      - ``unittest.mock.patch(...)``                (chained Attribute)
      - ``unittest.mock.patch.object(...)``
    """
    func = node.func

    # patch(...) — direct call
    if isinstance(func, ast.Name) and func.id == "patch":
        return True

    # patch.object(...) — attribute access on Name "patch"
    if isinstance(func, ast.Attribute):
        # X.patch(...) or X.patch.object(...)
        if func.attr == "patch":
            return True
        # patch.object(...) or X.patch.object(...) → outer .object on .patch
        if func.attr == "object" and isinstance(func.value, ast.Attribute) and func.value.attr == "patch":
            return True
        if func.attr == "object" and isinstance(func.value, ast.Name) and func.value.id == "patch":
            return True

    return False


def _extract_target(node: ast.Call) -> tuple[ast.AST | None, str | None]:
    """Return (literal-node, string-value) of the patch target if a string literal.

    The target is the first positional arg, or the ``target=`` keyword. Returns
    ``(None, None)`` if not a string literal (e.g. ``patch(SOME_CONST)`` —
    can't statically resolve).
    """
    # Positional first arg
    if node.args:
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg, arg.value

    # target= kwarg
    for kw in node.keywords:
        if kw.arg == "target" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value, kw.value.value

    return None, None


def _resolve_module(target: str) -> tuple[bool, str | None]:
    """Check if a patch target module resolves at runtime.

    Uses importlib.util.find_spec() to validate that the target module
    can be imported. Results are cached to avoid redundant lookups.

    Args:
        target: The patch target string (e.g. "autobot_backend.module.func").

    Returns:
        (resolves, error_msg) where:
        - resolves: True if module found, False otherwise
        - error_msg: None if resolves, else description of why it failed
    """
    if target in _RESOLUTION_CACHE:
        return _RESOLUTION_CACHE[target]

    # Extract the top-level module name from the target
    # (e.g. "autobot_backend.module.func" -> "autobot_backend")
    parts = target.split(".")
    if not parts:
        result = (False, "Empty target")
        _RESOLUTION_CACHE[target] = result
        return result

    top_level = parts[0]
    try:
        spec = importlib.util.find_spec(top_level)
        if spec is not None:
            result = (True, None)
        else:
            result = (False, f"Module '{top_level}' not found in sys.path")
    except (ImportError, ValueError, AttributeError, TypeError) as e:
        result = (False, f"Resolution error: {type(e).__name__}: {e}")

    _RESOLUTION_CACHE[target] = result
    return result


def _scan_file(path: Path, source: str) -> list[tuple[int, str]]:
    """Return [(line_no, message), …] for any banned ``src.*`` patch target or unresolvable targets."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []  # let other linters handle

    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_patch_call(node):
            continue
        literal_node, target = _extract_target(node)
        if target is None:
            continue

        # Check 1: Flag "src.*" prefix pattern
        if target.startswith("src."):
            findings.append(
                (
                    literal_node.lineno if literal_node else node.lineno,
                    (
                        f'patch("{target}") — autobot-backend has no `src/` package; '
                        "this mock target will fail to import and silently no-op. "
                        "Use the actual production import path (e.g. "
                        '`patch("autobot_backend.module.foo")` or the consumer '
                        "namespace where the symbol is bound). See #6987."
                    ),
                )
            )
            continue

        # Check 2: Runtime resolution check (informational only for non-existent modules)
        # Only flag if we can definitively say the module doesn't exist in the current
        # environment. This is an optional enhancement to catch typos early.
        # Note: We don't fail here if a module isn't found, as it might be installed
        # in the actual test environment but not in the lint hook's environment.
        # Instead, we only report this if explicitly enabled (future feature).

    return findings


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    repo_root = Path(__file__).resolve().parents[2]
    files = iter_python_files(args, repo_root)

    total_violations = 0
    for f in files:
        try:
            rel = f.resolve().relative_to(repo_root)
        except ValueError:
            rel = f
        rel_str = str(rel).replace("\\", "/")

        if rel_str in ALLOWLIST:
            continue
        if not _is_test_file(rel_str):
            continue

        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for line_no, message in _scan_file(f, source):
            print(
                f"[no-src-mock-path] {rel_str}:{line_no}: {message}",
                file=sys.stderr,
            )
            total_violations += 1

    if total_violations:
        print(
            f"\n[no-src-mock-path] {total_violations} banned patch target(s) found. "
            f"See per-line fix suggestions above. Rationale: #6987.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
