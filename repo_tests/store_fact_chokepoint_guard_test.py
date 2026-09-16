# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fact content reaches the store through the sanitizing chokepoint, never around it (#16770).

``KnowledgeBase.store_fact`` and ``update_fact`` sanitize their content against indirect
prompt injection. That only holds while they are the sole way content becomes a stored
fact: a writer that calls the durable primitives itself -- ``fact_store.persist_fact`` or
``FactsMixin._store_and_vectorize_fact`` -- writes text nothing inspected, which is the
shape of the bug this guard exists for (#5064 guarded one route, six writers went around
it). This guard fails on a new such caller, and on the chokepoint losing its own call.

**Scope.** Git-tracked production Python under ``autobot-backend/`` and ``autobot_shared/``,
tests excluded. :data:`REACH` floors what the sweep read, so an empty enumeration fails
instead of passing. The scan is name-based: it sees ``persist_fact(...)`` and
``<x>.persist_fact(...)``, and cannot see a call made through an alias, ``getattr`` or a
dispatch table. Those are the declared blind spots; the known-positive test below shows the
form it does catch.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()
SCAN_ROOTS = ("autobot-backend/", "autobot_shared/")

#: The durable write primitives. Reaching either one directly skips the sanitizing that
#: ``store_fact``/``update_fact`` apply on the way in.
WRITE_PRIMITIVES = frozenset({"persist_fact", "_store_and_vectorize_fact"})

#: The chokepoint itself, and the projection path. ``fact_projection`` re-writes rows that
#: were already sanitized when first stored (#16693 adoption and the visibility backfill):
#: it moves an existing fact between stores rather than admitting new text.
CHOKEPOINT = "autobot-backend/knowledge/facts.py"
ALLOWED_DIRECT_WRITERS = frozenset({CHOKEPOINT, "autobot-backend/knowledge/fact_projection.py"})

#: The functions that must carry the sanitizing call, and the call they must carry.
SANITIZING_ENTRY_POINTS = ("store_fact", "update_fact")
SANITIZER = "sanitize_fact_content"


def _is_production(rel: str) -> bool:
    name = Path(rel).name
    return (
        rel.startswith(SCAN_ROOTS)
        and rel.endswith(".py")
        and not name.startswith("test_")
        and not name.endswith("_test.py")
        and name != "conftest.py"
        and "/tests/" not in rel
    )


def _production_files(root: Path) -> list[str]:
    """The production Python files under *root* this guard reads; ``[]`` for an empty tree."""
    try:
        tracked = tracked_paths(root, "*.py")
    except EmptyEnumeration:
        return []  # the floor then refuses the empty sweep with ReachFloorError, as it should
    return [rel for rel in tracked if _is_production(rel)]


#: Bound at the 2590 files measured when the floor was added.
REACH = declare(
    "store-fact-chokepoint",
    discover=_production_files,
    floor=2590,
    growth=200,
    skips=0,
    what="production python files under autobot-backend/ and autobot_shared/",
)


def _called_names(node: ast.AST) -> list[tuple[str, int]]:
    """Every call in *node*, as ``(callee name, line)``."""
    calls = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name:
            calls.append((name, child.lineno))
    return calls


def direct_write_calls(source: str) -> list[int]:
    """Line numbers of calls to a durable write primitive in *source*."""
    return [line for name, line in _called_names(ast.parse(source)) if name in WRITE_PRIMITIVES]


def sanitizing_entry_points(source: str) -> set[str]:
    """Names of the functions in *source* that call the sanitizer."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(name == SANITIZER for name, _ in _called_names(node)):
                found.add(node.name)
    return found


@lru_cache(maxsize=1)
def _scan() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    read = 0
    for rel in REACH.examined(REPO_ROOT):
        lines = direct_write_calls((REPO_ROOT / rel).read_text(encoding="utf-8"))
        read += 1
        if lines:
            found[rel] = lines
    REACH.completed(read)
    return found


def test_no_writer_reaches_the_store_around_the_chokepoint():
    offenders = {rel: lines for rel, lines in _scan().items() if rel not in ALLOWED_DIRECT_WRITERS}
    assert not offenders, (
        "fact content written without the #16770 sanitizing chokepoint — call "
        f"KnowledgeBase.store_fact/update_fact instead, or justify an entry in ALLOWED_DIRECT_WRITERS: {offenders}"
    )


def test_the_chokepoint_still_sanitizes_what_it_stores():
    """The allowlist above is only safe while these two actually sanitize."""
    source = (REPO_ROOT / CHOKEPOINT).read_text(encoding="utf-8")
    missing = sorted(set(SANITIZING_ENTRY_POINTS) - sanitizing_entry_points(source))
    assert not missing, f"{CHOKEPOINT}: {missing} no longer call {SANITIZER}() (#16770)"


def test_a_new_direct_writer_is_detected():
    """Known positive: the detector fires on the call form it claims to see."""
    src = "async def ingest(rows):\n    for row in rows:\n        await persist_fact(row.id, row.text, {})\n"
    assert direct_write_calls(src) == [3]
    assert direct_write_calls("async def ingest(kb, row):\n    await kb._store_and_vectorize_fact(1, 'x', {})\n") == [2]


def test_a_function_without_the_sanitizer_is_not_counted():
    """Known negative: the chokepoint check cannot be satisfied by an unrelated call."""
    src = "def store_fact(content, metadata):\n    return persist_fact(content, metadata)\n"
    assert sanitizing_entry_points(src) == set()
