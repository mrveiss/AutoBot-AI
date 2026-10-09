#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18122 — how many modules hold a live KnowledgeBase, asserted and shrink-only.

There were three independent stores:

    knowledge/_composed.py      _knowledge_base_instance   module global + asyncio.Lock
    knowledge_factory.py        _knowledge_base_instance   module global, same NAME
    knowledge_base_factory.py   KnowledgeBaseInitializer._instance

Two module names differ by one word and two globals had the identical name in different
modules. #13026 was the direct consequence: a caller reached the wrong
`get_knowledge_base` and every request raised `TypeError` on a kwarg the other one does
not accept. `autobot_shared.store_authority` forbids the shape outright — one store is
the system of record, every other copy is a rebuildable projection.

`knowledge_base_factory` is now a facade and holds nothing. This test pins the remaining
population so a fourth cannot appear quietly, and so removing one is a deliberate edit
here rather than a silent drift. The set only shrinks.

Static on purpose: importing these modules pulls in FastAPI, ChromaDB and Redis, and the
property under test is structural — *where the instance is kept* — not runtime
behaviour.
"""

from __future__ import annotations

import ast
import functools
import subprocess  # nosec B404  # fixed argv, no shell, no caller input

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

#: Modules still allowed to cache a KnowledgeBase, with why. SHRINK-ONLY: removing a
#: store means deleting its line, never adding one.
#:
#: Both remaining stores are real and the consolidation is unfinished — this pins the
#: debt rather than claiming it is paid. `_composed` is reached by ~44 lazy import sites
#: across memory/, llc/ and mcp_server/; `knowledge_factory` owns `app.state` and is
#: reached by ~20 `api/knowledge*.py` routes plus lifespan. Collapsing them changes which
#: store those call sites read, which is the remaining half of #18122.
KNOWN_STORES = {
    "autobot-backend/knowledge/_composed.py": "the app-free singleton reached by lazy imports",
    "autobot-backend/knowledge_factory.py": "owns app.state.knowledge_base plus an app-free global",
}

#: Must hold nothing: it is a facade over `knowledge_factory` (#18122).
FACADE = "autobot-backend/knowledge_base_factory.py"

_SEARCH_ROOTS = ("autobot-backend/",)


@functools.lru_cache(maxsize=1)
def _tracked_python_files() -> tuple[str, ...]:
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(repo_root()),
        env=scrubbed_git_env(),
        check=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line)


def _is_knowledge_base_ref(node: ast.AST | None) -> bool:
    """True when `node` references the KnowledgeBase type itself.

    Inspects nodes rather than substring-matching `ast.unparse`. The first version of
    this matcher did the latter and reported six phantom stores, because
    `__all__ = [..., "KnowledgeBaseInitializer"]` and every re-export facade contain the
    substring. `KnowledgeBaseInitializer` is not `KnowledgeBase`, and a name in a string
    list is not a stored instance.
    """
    if node is None:
        return False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == "KnowledgeBase":
            return True
        # Forward reference: `_kb: "KnowledgeBase" | None = None`
        if isinstance(sub, ast.Constant) and sub.value == "KnowledgeBase":
            return True
    return False


def _caches_a_knowledge_base(tree: ast.Module) -> bool:
    """True when a module-level name or class attribute holds a KnowledgeBase.

    Two shapes, both of which the three stores used:

      * an annotated declaration -- `_knowledge_base_instance: "KnowledgeBase" | None = None`
      * a direct construction cached at module or class scope -- `_kb = KnowledgeBase()`

    A re-export (`from knowledge import KnowledgeBase`), a name inside `__all__`, and a
    function parameter annotation are all explicitly NOT stores.
    """
    scopes: list[ast.AST] = [tree]
    scopes += [n for n in tree.body if isinstance(n, ast.ClassDef)]
    for scope in scopes:
        for stmt in getattr(scope, "body", []):
            if isinstance(stmt, ast.AnnAssign) and _is_knowledge_base_ref(stmt.annotation):
                return True
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                if _is_knowledge_base_ref(stmt.value.func):
                    return True
    return False


@functools.lru_cache(maxsize=1)
def _modules_caching_a_knowledge_base() -> tuple[str, ...]:
    root = repo_root()
    found: list[str] = []
    for rel in _tracked_python_files():
        if not rel.startswith(_SEARCH_ROOTS):
            continue
        if rel.endswith("_test.py") or rel.startswith("test_") or "tests/" in rel:
            continue
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        if _caches_a_knowledge_base(tree):
            found.append(rel)
    return tuple(sorted(found))


def test_the_scan_is_not_vacuous() -> None:
    """An empty sweep satisfies every assertion below by looking at nothing."""
    assert len(_tracked_python_files()) > 3000, "git ls-files returned almost nothing"
    assert _modules_caching_a_knowledge_base(), "matched no store at all — the matcher is broken"


def test_the_matcher_sees_both_declaration_shapes() -> None:
    """Pinned against synthetic source, so it does not depend on the tree."""
    annotated = ast.parse('_kb: "KnowledgeBase" | None = None\n')
    assert _caches_a_knowledge_base(annotated)
    in_class = ast.parse('class I:\n    _instance: "KnowledgeBase" | None = None\n')
    assert _caches_a_knowledge_base(in_class)
    constructed = ast.parse("_kb = KnowledgeBase()\n")
    assert _caches_a_knowledge_base(constructed)
    unrelated = ast.parse("_x: int = 0\n\n\nclass C:\n    y = 1\n")
    assert not _caches_a_knowledge_base(unrelated)


@pytest.mark.parametrize(
    "label,source",
    [
        ("a name inside __all__", '__all__ = ["KnowledgeBase", "KnowledgeBaseInitializer"]\n'),
        ("a re-export", "from knowledge import KnowledgeBase\n"),
        ("a longer identifier", 'x: "KnowledgeBaseInitializer" | None = None\n'),
        ("a parameter annotation", 'def f(kb: "KnowledgeBase") -> None:\n    pass\n'),
        ("a call that returns one", "_kb = get_knowledge_base()\n"),
    ],
)
def test_the_matcher_rejects_what_merely_mentions_the_name(label: str, source: str) -> None:
    """The six phantom stores the first version of this matcher reported.

    It substring-matched `ast.unparse`, so `__all__` entries, re-export facades and
    `KnowledgeBaseInitializer` all counted. Each row here is one of those false
    positives, kept so the loose form cannot come back.
    """
    assert not _caches_a_knowledge_base(ast.parse(source)), label


def test_no_fourth_knowledge_base_store_has_appeared() -> None:
    found = set(_modules_caching_a_knowledge_base())
    unexpected = found - set(KNOWN_STORES)
    assert not unexpected, (
        f"#18122: a new module caches its own KnowledgeBase: {sorted(unexpected)}. "
        "One store is the system of record and every other copy is a rebuildable "
        "projection (autobot_shared.store_authority). Resolve the canonical instead — "
        "`knowledge_factory.get_knowledge_base_async()` app-free, or "
        "`get_or_create_knowledge_base(app)` with a request."
    )


@pytest.mark.parametrize("rel", sorted(KNOWN_STORES))
def test_every_known_store_still_exists(rel: str) -> None:
    """A baseline entry stranded by a rename exempts nothing, silently."""
    assert rel in _modules_caching_a_knowledge_base(), (
        f"#18122: {rel} no longer caches a KnowledgeBase. If its store was consolidated, "
        "delete its line from KNOWN_STORES — the set only shrinks."
    )


def test_the_facade_holds_no_store() -> None:
    """`knowledge_base_factory` was the third store; it must stay a facade."""
    assert FACADE not in _modules_caching_a_knowledge_base(), (
        f"#18122: {FACADE} caches a KnowledgeBase again. It is a facade over "
        "knowledge_factory; re-adding state there restores the third store."
    )
    source = (repo_root() / FACADE).read_text(encoding="utf-8")
    assert "from knowledge_factory import" in source, f"{FACADE} no longer delegates to the canonical"


def test_the_store_count_is_recorded() -> None:
    """States the number rather than implying it, so progress is legible.

    Two, down from three. Not one — the remaining consolidation changes which store ~64
    call sites read, and is tracked on #18122 rather than smuggled into a facade change.
    """
    assert len(_modules_caching_a_knowledge_base()) == 2
