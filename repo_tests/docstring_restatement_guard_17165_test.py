# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A docstring must add something beyond its own symbol's name (#17165).

Step 1 of #17165: this guard has to land BEFORE the bulk-LLM drafting batches that
fill the 2,275-symbol coverage gap, because it defines the standard those drafts
are written against -- and it applies equally to a hand-written docstring, since
the standard is about the codebase, not about who typed it.

``docstring_restatement_baseline_17165.py`` grandfathers the 280 restatements
already in the tree the day this guard landed (measured by this file's own
sweep, so the two numbers cannot drift apart silently). This guard's job is not
retroactive cleanup -- #17165's drafting batches do that, tracked per its own
AC2 -- it is to block the NEXT one from landing, starting now.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._docstring_restatement import is_restatement
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.docstring_restatement_baseline_17165 import KNOWN_RESTATEMENTS

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.endswith("_test.py") or name.startswith("test_") or "/tests/" in path


def _public_symbols(root: Path) -> list[tuple[str, str, str | None]]:
    """``(file, name, docstring)`` for every named public non-test symbol.

    "Named public non-test" matches #17165's own scope: a `FunctionDef` /
    `AsyncFunctionDef` / `ClassDef` whose name does not start with `_` (so
    neither a private helper nor a dunder -- `__init__` etc. are covered by
    their class's own docstring, per the issue's scope decision), outside any
    test file. Nested functions/methods are included: a restating docstring on
    a public method is exactly as much noise in the embedding index as one on
    a module-level function.
    """
    try:
        paths = tracked_paths(root, "*.py")
    except EmptyEnumeration:
        return []

    found: list[tuple[str, str, str | None]] = []
    for rel in paths:
        if _is_test_path(rel):
            continue
        path = root / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            found.append((rel, node.name, ast.get_docstring(node)))
    return found


#: Live population 2026-09-20: 23,819 named public non-test symbols. Growth
#: reflects that ordinary feature work adds public functions/classes
#: continuously -- not a fixed vocabulary like a workflow list. 1,000 headroom
#: is roughly the size of a single large feature PR's worth of new public
#: surface; re-measure and ratchet down per RATCHET_BASELINES.md if it is ever
#: found loose.
REACH = declare(
    "docstring-restatement-scan",
    discover=_public_symbols,
    #: Re-measured on 9ea37f7cb3 (#17517): the live population had reached
    #: 24,000 -- exactly the old cap of floor+growth -- so main passed with zero
    #: margin and every PR adding one public symbol went red on an unrelated
    #: branch. Raising a *floor* tightens the guard; the 1,000 stays as the
    #: working headroom the note above describes.
    floor=24_000,
    growth=1_000,
    what="named public non-test symbols (functions, methods, classes)",
)


def _current_restatements(root: Path) -> dict[str, frozenset[str]]:
    by_file: dict[str, set[str]] = {}
    for rel, name, doc in REACH.examined(root):
        if doc and is_restatement(name, doc):
            by_file.setdefault(rel, set()).add(name)
    return {rel: frozenset(names) for rel, names in by_file.items()}


def test_the_sweep_reaches_the_codebase() -> None:
    """Positive assertion first -- an empty sweep would pass every check below
    having examined nothing, which is the silence this guard exists to avoid."""
    REACH.verify_floor(REPO_ROOT)


def test_is_restatement_rejects_a_literal_restatement() -> None:
    """The failure case #17165 names verbatim: the docstring is the name, reworded."""
    assert is_restatement("get_user_by_id", "Get user by id.") is True
    assert is_restatement("register_local_agent", "Register a local agent") is True


def test_is_restatement_accepts_a_docstring_carrying_real_information() -> None:
    """Negative control (#17165 review): same function name, a docstring that
    actually says something -- proves the check can pass, not just fail."""
    assert (
        is_restatement(
            "get_user_by_id",
            "Look up the user in the primary cache, falling back to a database read "
            "and raising KeyError if the id is unknown.",
        )
        is False
    )


def test_is_restatement_ignores_a_missing_docstring() -> None:
    """Coverage (does a docstring exist) is a separate, tracked-elsewhere concern
    (#17165 AC2) -- this guard must not conflate 'missing' with 'restates'."""
    assert is_restatement("get_user_by_id", None) is False
    assert is_restatement("get_user_by_id", "   ") is False


def test_no_new_restatement_beyond_the_grandfathered_baseline() -> None:
    """The guard itself: every CURRENT restatement must already be known."""
    current = _current_restatements(REPO_ROOT)
    new: dict[str, frozenset[str]] = {}
    for rel, names in current.items():
        unbaselined = names - KNOWN_RESTATEMENTS.get(rel, frozenset())
        if unbaselined:
            new[rel] = frozenset(unbaselined)
    assert not new, (
        f"new restating docstring(s), not in docstring_restatement_baseline_17165.py: {dict(sorted(new.items()))}\n"
        "A docstring that only rewords its symbol's name is worse than none for the "
        "vector index #17165 exists to build -- write one that says what the symbol "
        "actually does, or add it to the baseline only if fixing it now is out of scope."
    )


def test_the_baseline_has_no_stale_entries() -> None:
    """The other half of a ratchet: an entry that no longer restates (fixed, but
    the baseline was not updated in the same commit) must be removed, not left
    as unused headroom -- the same discipline RATCHET_BASELINE is held to."""
    current = _current_restatements(REPO_ROOT)
    stale: dict[str, frozenset[str]] = {}
    for rel, names in KNOWN_RESTATEMENTS.items():
        no_longer = names - current.get(rel, frozenset())
        if no_longer:
            stale[rel] = frozenset(no_longer)
    assert not stale, (
        f"docstring_restatement_baseline_17165.py entries no longer restating anything "
        f"(delete them, in the commit that fixed them): {dict(sorted(stale.items()))}"
    )
