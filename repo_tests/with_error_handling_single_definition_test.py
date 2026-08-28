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
from typing import List, Set

import pytest

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"

_TARGET_NAME = "with_error_handling"

# Directory names skipped, matched against parts of the path RELATIVE to the
# scan root -- never a substring of the absolute path (#15121). This repo's
# whole workflow runs from `<main-tree>/.worktrees/<branch>/` checkouts, so
# `"/.worktrees/" in path.as_posix()` is true of the repo root itself and skips
# every file in the tree; the guard then inspects nothing and fails its own
# non-vacuity assertion. `tests` has the identical failure mode for a checkout
# under any directory of that name. Same form as
# `first_party_imports_resolve_test.py:33` and
# `shell_lib_sources_resolve_test.py:58`.
_SKIP_PARTS = {"node_modules", ".worktrees", "tests", "__pycache__", "venv", ".venv"}

# The one file allowed to define it. Anything else defining a function or
# async function with this exact name is the fork this test exists to catch.
_CANONICAL_DEFINER = (_BACKEND / "utils" / "error_boundaries" / "decorators.py").resolve()


def _production_sources(root: Path = _BACKEND) -> List[Path]:
    """Backend .py files, excluding tests, node_modules and worktree copies.

    `root` is a parameter so the exclusion logic can be exercised against a
    fixture tree that itself lives under `.worktrees/` -- the arrangement this
    scan silently erased before #15121.
    """
    out: List[Path] = []
    for path in root.rglob("*.py"):
        if path.name.endswith("_test.py") or path.name.startswith("test_"):
            continue
        if any(part in _SKIP_PARTS for part in path.relative_to(root).parts):
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


def test_the_scan_sees_the_tree_it_is_pointed_at():
    """A guard that skipped every file would report clean, not report a skip.

    Split out from the assertion below so the two failures read differently:
    "the scan found nothing to inspect" is a defect in this file, while
    "with_error_handling vanished" is a defect in the code under guard. Before
    #15121 the first masqueraded as the second in every worktree checkout.
    """
    sources = _production_sources()

    assert len(sources) > 100, (
        f"only {len(sources)} backend sources survived the exclusion filter — "
        "the filter is eating the tree, so every assertion below is vacuous"
    )
    assert _CANONICAL_DEFINER in {path.resolve() for path in sources}


def _write_fixture_tree(root: Path) -> Path:
    """One canonical definer plus genuinely excluded files; returns the definer.

    Same fixture shape as `scripts/check_ansible_file_references_test.py:40-45`
    and `repo_tests/lint/canonical/test_context.py:76-78`.
    """
    (root / "utils" / "error_boundaries").mkdir(parents=True)
    definer = root / "utils" / "error_boundaries" / "decorators.py"
    definer.write_text(f"def {_TARGET_NAME}():\n    pass\n", encoding="utf-8")
    for excluded in ("node_modules", "tests"):
        (root / excluded).mkdir()
        (root / excluded / "vendored.py").write_text("x = 1\n", encoding="utf-8")
    return definer


def _relative_scan(root: Path) -> Set[str]:
    """`_production_sources` as repo-relative posix strings, so two trees compare."""
    return {path.relative_to(root).as_posix() for path in _production_sources(root)}


def test_a_checkout_under_worktrees_is_still_scanned(tmp_path):
    """#15121: the filter must key on parts relative to the scan root.

    The fixture reproduces the mandated layout exactly — the scan root itself
    sits under `.worktrees/<branch>/`. Matching a substring of the absolute path
    skips every file here; matching relative parts finds the definer.
    """
    root = tmp_path / ".worktrees" / "issue-9999" / "autobot-backend"
    definer = _write_fixture_tree(root)

    scanned = _production_sources(root)

    assert definer in scanned, (
        "a scan rooted under .worktrees/ skipped its own tree — the exclusion "
        "is matching the absolute path instead of parts relative to the root"
    )
    assert {path.name for path in scanned} == {"decorators.py"}
    assert _defines_target(definer) == [1]


@pytest.mark.parametrize("ancestor", sorted(_SKIP_PARTS))
def test_an_excluded_name_above_the_scan_root_changes_nothing(tmp_path, ancestor):
    """#15140: the filter must be prefix-invariant for *every* skipped name.

    The test above pins `.worktrees` alone, so reintroducing the absolute form
    for just one of the other names — `if "/tests/" in path.as_posix()` — keeps
    this file green while emptying the tree for any checkout under a directory
    of that name. Measured: that partial regression left the suite 5-green.
    Comparing the same tree at two prefixes pins the invariant instead of one
    case of it.
    """
    under = tmp_path / "under" / ancestor / "issue-9999" / "autobot-backend"
    plain = tmp_path / "plain" / "checkout" / "autobot-backend"
    _write_fixture_tree(under)
    _write_fixture_tree(plain)

    # Non-vacuity first: if the neutral tree scanned empty the comparison below
    # would pass by finding nothing at either prefix.
    assert _relative_scan(plain) == {"utils/error_boundaries/decorators.py"}
    assert _relative_scan(under) == _relative_scan(plain), (
        f"a scan root nested under a directory named {ancestor!r} enumerated a "
        "different set than the same tree elsewhere — the exclusion is matching "
        "the absolute path instead of parts relative to the root"
    )


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
