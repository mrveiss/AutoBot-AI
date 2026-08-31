# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A first-party import must name a module that exists (#14839).

`llc/kb/capability_indexer.py` did `from llc.db import get_async_session_factory`.
There is no `llc.db`. Because the import sat **inside a function**, nothing
failed at import time, no linter that only resolves top-level imports saw it,
and `from llc.kb import AgentCapabilityIndexer` kept working. It raised
`ModuleNotFoundError` on every *call* — and all four call sites caught it and
logged it as non-fatal, so agent capability indexing was 100% dead for as long
as the typo existed, with no signal anywhere but a log line.

That combination — a deferred import, a broad `except`, and a feature nobody
watches — is why this needs a check rather than a code review habit.

Scope note: this deliberately checks only that the **module** resolves, not that
the imported *name* exists inside it. Resolving names would mean importing the
module, which pulls the whole dependency graph and turns a cheap structural
check into a fragile one. Module-not-found is the failure this class produces.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _REPO_ROOT / "autobot-backend"
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".worktrees", ".claude", "venv", ".venv"}

# Imports whose module genuinely does not exist, each with the issue tracking it.
# Kept tiny on purpose: an entry here is a live bug, not an accepted exception.
# The test below asserts every entry is still broken, so a fixed import forces
# its exemption to be removed rather than sitting here exempting nothing.
_KNOWN_BROKEN = {
    ("chat_history/context_overflow.py", "llm_shared.gateway"): "#14840",
}


def _first_party_roots() -> set[str]:
    """Top-level packages under autobot-backend, derived from the filesystem."""
    return {p.name for p in _BACKEND.iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def _resolves(module: str) -> bool:
    base = _BACKEND / Path(*module.split("."))
    return base.with_suffix(".py").exists() or (base / "__init__.py").exists()


def _optional_import_nodes(tree: ast.AST) -> set[int]:
    """Nodes inside a try/except that catches an import error.

    An optional dependency guarded that way is allowed to be absent — that is
    the point of the guard, and flagging it would train people to ignore this.
    """
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        caught: set[str] = set()
        for handler in node.handlers:
            for sub in ast.walk(handler.type) if handler.type else []:
                if isinstance(sub, ast.Name):
                    caught.add(sub.id)
        # Deliberately NOT including bare `Exception`. A broad handler is not a
        # declaration that the import is optional — and in this repo it is the
        # single most common wrapper around a first-party import, including all
        # three call sites of the very function #14839 fixed
        # (`agent_org_service.py:263`, `:331`, `portability.py:716`). Treating it
        # as an exemption would have made this guard blind at exactly the places
        # its own docstring names. It caught the original bug only because that
        # import happened to sit in a function with no surrounding try.
        if {"ImportError", "ModuleNotFoundError"} & caught:
            guarded.update(id(child) for child in ast.walk(node))
    return guarded


def _unresolvable_imports() -> tuple[list[tuple[str, str, int]], int]:
    """((relative path, module, lineno) list, files scanned) — the count is the floor."""
    roots = _first_party_roots()
    found: list[tuple[str, str, int]] = []
    scanned = 0
    for path in _BACKEND.rglob("*.py"):
        # Relative to the backend, never the absolute path: a checkout living
        # under a directory that happens to be named `.claude` or `venv` would
        # otherwise match every file, skip the whole tree, and report clean.
        # That is the failure this guard exists to catch, so it must not be the
        # guard's own failure mode — it was, in the first draft of this file.
        if any(part in _SKIP_PARTS for part in path.relative_to(_BACKEND).parts):
            continue
        scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        guarded = _optional_import_nodes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            if node.module.split(".")[0] not in roots or id(node) in guarded:
                continue
            if not _resolves(node.module):
                found.append((str(path.relative_to(_BACKEND)), node.module, node.lineno))
    return found, scanned


def test_the_sweep_actually_reached_the_tree() -> None:
    """A discovery floor. An empty walk reports clean having asserted nothing.

    Both halves are needed. The package floor alone passed while the file walk
    was skipping every file in the tree — the packages were discovered by a
    different code path than the files.
    """
    roots = _first_party_roots()
    _, scanned = _unresolvable_imports()

    assert len(roots) > 20, f"only found {len(roots)} first-party packages — the walk is wrong"
    assert "llc" in roots and "chat_history" in roots
    assert scanned > 1000, f"only walked {scanned} python files — the skip list is eating the tree"


def test_every_first_party_import_names_a_real_module() -> None:
    found, scanned = _unresolvable_imports()
    assert scanned > 1000, f"only walked {scanned} python files — this would pass vacuously"
    offenders = [
        f"{rel}:{line}  from {module} import ..." for rel, module, line in found if (rel, module) not in _KNOWN_BROKEN
    ]

    assert not offenders, (
        "these imports name modules that do not exist. If the import sits inside a "
        "function, it raises ModuleNotFoundError at call time rather than at import "
        "time, and a caller with a broad `except` will swallow it — the feature is "
        "then dead with no signal (#14839):\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("entry,issue", sorted(_KNOWN_BROKEN.items()))
def test_each_exemption_is_still_broken(entry: tuple[str, str], issue: str) -> None:
    """An exemption that no longer applies exempts nothing, silently.

    If someone fixes the import but leaves the entry, this file quietly stops
    guarding that path. Failing here forces the entry out along with the fix.
    """
    rel, module = entry
    path = _BACKEND / rel
    assert path.is_file(), f"{rel} moved or was deleted — update or drop this exemption ({issue})"
    assert not _resolves(module), (
        f"{module} now resolves, so the exemption for {rel} ({issue}) is obsolete — "
        "remove it from _KNOWN_BROKEN so the import is guarded again"
    )
    # #14851 fixed its import by REMOVING it: the module still does not resolve,
    # so the assertion above stayed green while the entry exempted a file that
    # no longer contains the import. An exemption stranded that way is invisible
    # — it guards nothing and nothing says so.
    imported = {
        node.module
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert module in imported, (
        f"{rel} no longer imports {module}, so the exemption ({issue}) is obsolete — " "remove it from _KNOWN_BROKEN"
    )
