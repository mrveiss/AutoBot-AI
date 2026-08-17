# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Exactly one ``with_error_handling`` may exist in the tracked tree (#14191).

Before this fix, ``autobot-backend/error_handler.py`` and
``autobot-backend/utils/error_boundaries/decorators.py`` each defined a
top-level function named ``with_error_handling`` with disjoint parameter sets
and opposite behaviour on ``HTTPException``. Nothing distinguished them at an
import site — ``grep -rn "def with_error_handling"`` returned two hits with no
indication which one any given ``from ... import with_error_handling`` call
resolved to, and getting it wrong produced a materially wrong analysis in PR
#14186.

The guard walks the AST (never a source-text grep for the string
``with_error_handling``, which would also match comments, docstrings, and the
now-renamed ``with_default_on_error``) looking for ``FunctionDef``/
``AsyncFunctionDef`` nodes whose name is exactly ``with_error_handling``. Only
the canonical decorator in ``decorators.py`` may define it; a second
definition anywhere else — under any name that happens to collide — fails
this test with the offending file:line, whether or not it is ever imported.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"

_TARGET_NAME = "with_error_handling"

# The one file allowed to define it. Anything else defining a function or
# async function with this exact name is the fork this test exists to catch.
_CANONICAL_DEFINER = (_BACKEND / "utils" / "error_boundaries" / "decorators.py").resolve()


def _production_sources() -> List[Path]:
    """Backend .py files, excluding tests, node_modules and worktree copies."""
    out: List[Path] = []
    for path in _BACKEND.rglob("*.py"):
        posix = path.as_posix()
        if path.name.endswith("_test.py") or path.name.startswith("test_"):
            continue
        if "/node_modules/" in posix or "/.worktrees/" in posix or "/tests/" in posix:
            continue
        out.append(path)
    return out


def _defines_target(path: Path) -> List[int]:
    """Return line numbers where `path` defines a (async) function named _TARGET_NAME."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    lines = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == _TARGET_NAME:
            lines.append(node.lineno)
    return lines


def test_exactly_one_definition_exists_in_the_tracked_tree():
    definers = {}
    for path in _production_sources():
        hits = _defines_target(path)
        if hits:
            definers[path.resolve()] = hits

    assert definers, f"{_TARGET_NAME} vanished from its canonical module — this guard expects it to exist"

    offenders = {path: lines for path, lines in definers.items() if path != _CANONICAL_DEFINER}
    assert not offenders, (
        f"A second `{_TARGET_NAME}` definition reappeared outside "
        f"{_CANONICAL_DEFINER.relative_to(_REPO)}: {offenders}. "
        "Give it a distinct, descriptive name instead (see error_handler.py's "
        "with_default_on_error for the pattern) — #14191 exists because a "
        "shared name with different behaviour produced a wrong analysis in PR "
        "#14186."
    )


def test_the_canonical_definer_defines_it_exactly_once():
    """A guard this narrow is only as good as its own precision: catch the
    canonical file itself acquiring a second, shadowing definition."""
    hits = _defines_target(_CANONICAL_DEFINER)
    assert len(hits) == 1, f"expected exactly one {_TARGET_NAME} in {_CANONICAL_DEFINER}, found at lines {hits}"


def test_the_renamed_sibling_no_longer_shares_the_name():
    """error_handler.py's decorator must not silently regain the collision."""
    renamed_module = _BACKEND / "error_handler.py"
    assert _defines_target(renamed_module) == [], (
        f"{renamed_module.relative_to(_REPO)} defines {_TARGET_NAME} again — "
        "it was renamed to with_default_on_error in #14191 specifically to "
        "end the name collision; keep it renamed."
    )

    tree = ast.parse(renamed_module.read_text(encoding="utf-8"))
    defined = {
        node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "with_default_on_error" in defined, (
        f"{renamed_module.relative_to(_REPO)} lost with_default_on_error — "
        "never-delete: it must be renamed, not removed."
    )
