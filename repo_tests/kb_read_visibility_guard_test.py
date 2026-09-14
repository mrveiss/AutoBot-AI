# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every production read of knowledge-base facts applies the ownership filter, or is a
known, tracked exception (#16667; umbrella #16654).

**What counts as a read.** A call ``<receiver>.<method>(...)`` where ``method`` is one of
:data:`READ_METHODS` -- the KB primitives that return fact content (``search``,
``get_fact``, ``get_all_facts`` and the tag, category, collection, metadata and relation
readers) -- on a receiver the codebase uses for the knowledge base (:data:`KB_RECEIVERS`),
or ``advanced_search`` on a RAG receiver (:data:`RAG_RECEIVERS`). It is checked at the call
site, in the innermost enclosing function, not at the route: a route usually reaches the
knowledge base several service layers down, and a per-route rule would miss every one.

**What counts as filtering.** The enclosing function (anywhere in its body) calls one of
:data:`FILTER_HELPERS`.

**Scope.** Git-tracked production Python under :data:`SCAN_ROOTS`; tests and scripts are
excluded.

**Blind spots -- declared, not silent.** This detector cannot see: a KB method stored as a
bound method and called later (``HybridSearcher`` keeps ``self.search``); polymorphic
backend dispatch (``VectorSearchEngine`` backends); filters hidden in ``**kwargs``; the
infra MCP server's HTTP hop; reads that bypass the primitives (direct ``fact:*`` Redis
reads, raw ChromaDB collection reads such as ``api/knowledge_chroma.py``); receivers named
outside :data:`KB_RECEIVERS` -- including a bare ``self`` (the KB's own mixins calling a
sibling reader, e.g. ``FactsMixin.get_shared_facts``; ``self.advanced_search`` in the RAG
optimizer) and a call-result receiver (``self._get_hybrid_searcher().search(...)``); and
reads outside any function. Those are tracked on the #16654 sub-issues instead of detected
here.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.kb_read_visibility_allowlist import ALLOWLIST, MAX_ALLOWLISTED

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()
SCAN_ROOTS = ("autobot-backend/", "autobot_shared/", "autobot-infrastructure/shared/mcp/")
_SKIP_SUBSTRINGS = ("/tests/", "/scripts/")

READ_METHODS = frozenset(
    {
        "search",
        "get_fact",
        "get_all_facts",
        "list_facts_with_usage",
        "get_facts_by_tag",
        "search_facts_by_tags",
        "get_facts_in_category",
        "get_facts_in_collection",
        "export_collection",
        "search_by_metadata",
        "get_fact_relations",
        "traverse_relations",
        "hybrid_search",
        "basic_vector_search",
        "search_ctx",
    }
)
KB_RECEIVERS = frozenset(
    {
        "kb",
        "self.kb",
        "knowledge_base",
        "self.knowledge_base",
        "kb_to_use",
        "self._kb",
        "ctx.worker.knowledge_base",
        "kb_manager",
        "kb_service",
        "self.kb_adapter",
        "self.knowledge_base_adapter",
    }
)
RAG_METHODS = frozenset({"advanced_search"})
RAG_RECEIVERS = frozenset(
    {"rag_service", "self.rag_service", "self.rag", "self._rag", "self.optimizer", "optimizer", "self._rag_service"}
)
FILTER_HELPERS = frozenset(
    {
        "filter_search_results_by_permission",
        "augment_search_request_with_permissions",
        "build_chromadb_permission_filter",
        "check_access",
        "filter_accessible_facts",
        "get_all_accessible_facts",
    }
)

#: A floor on what the scan FOUND, not a census: fewer reads than this means a receiver or
#: method was renamed, and the guard would otherwise pass vacuously. The floor on what it
#: examined is :data:`REACH`.
MIN_READS_FOUND = 40

_REASON_PREFIXES = ("TRACKED_GAP #", "SCOPED: ", "NOT_USER_FACING: ", "IMPL: ")
_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _is_production(rel: str) -> bool:
    name = Path(rel).name
    return (
        rel.startswith(SCAN_ROOTS)
        and rel.endswith(".py")
        and not name.startswith("test_")
        and not name.endswith("_test.py")
        and name != "conftest.py"
        and not any(skip in rel for skip in _SKIP_SUBSTRINGS)
    )


def _production_files(root: Path) -> list[str]:
    """Tracked production Python under :data:`SCAN_ROOTS` -- this guard's population."""
    try:
        tracked = tracked_paths(root, "*.py")
    except EmptyEnumeration:
        return []  # an empty tree: REACH's floor raises the typed refusal instead (_reach.declare)
    return [rel for rel in tracked if _is_production(rel)]


#: MEASURED 2026-09-14 against this tree: 2558 production files by this guard's own filter
#: (2359 autobot-backend, 195 autobot_shared, 4 infra MCP); the hand-rolled 2000 it replaces
#: sat 22% below. `growth=250` (~10%) absorbs ordinary additions, since most feature work
#: adds production modules. That band cannot see a small root vanish, so
#: `test_every_scan_root_is_reached` checks each root separately. `skips=0`: every
#: discovered file is parsed, and an unparseable one fails the scan loudly.
REACH = declare(
    "kb-read-visibility-production-sweep",
    discover=_production_files,
    floor=2558,
    growth=250,
    skips=0,
    what="production python files",
)


def _dotted(node: ast.AST) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _own_calls(func: ast.AST) -> list[ast.Call]:
    """Calls in *func*'s own body -- nested functions and classes are attributed to themselves."""
    calls, stack = [], list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        if isinstance(node, _NESTED):
            continue
        if isinstance(node, ast.Call):
            calls.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return calls


def _called_name(call: ast.Call) -> str | None:
    return call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", None)


#: Calls that run their first argument on a worker thread: ``asyncio.to_thread(kb.get_fact, fid)``
#: is a ``kb.get_fact`` read (#16670 moved the synchronous ``get_fact`` behind it).
THREAD_OFFLOADS = frozenset({"asyncio.to_thread", "to_thread"})


def _is_kb_read(call: ast.Call) -> bool:
    func = call.func
    if _dotted(func) in THREAD_OFFLOADS and call.args:
        func = call.args[0]
    if not isinstance(func, ast.Attribute):
        return False
    receiver, method = _dotted(func.value), func.attr
    return (method in READ_METHODS and receiver in KB_RECEIVERS) or (
        method in RAG_METHODS and receiver in RAG_RECEIVERS
    )


def kb_reads(source: str) -> list[tuple[str, int, bool]]:
    """``(enclosing qualname, line, filtered)`` for every KB read in *source*'s functions."""
    reads: list[tuple[str, int, bool]] = []

    def visit(node: ast.AST, qual: str) -> None:
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, _NESTED):
                continue
            name = f"{qual}.{child.name}" if qual else child.name
            if not isinstance(child, ast.ClassDef):
                filtered = any(_called_name(c) in FILTER_HELPERS for c in ast.walk(child) if isinstance(c, ast.Call))
                reads.extend((name, c.lineno, filtered) for c in _own_calls(child) if _is_kb_read(c))
            visit(child, name)

    visit(ast.parse(source), "")
    return reads


@lru_cache(maxsize=1)
def _scan() -> tuple[dict[tuple[str, str], list[int]], int]:
    """``({(file, qualname): [line, ...]} for unfiltered reads, reads found)``."""
    unfiltered: dict[tuple[str, str], list[int]] = {}
    found = 0
    for rel in REACH.examined(REPO_ROOT):
        reads = kb_reads((REPO_ROOT / rel).read_text(encoding="utf-8"))  # unparseable: fail loudly
        found += len(reads)
        for qual, line, filtered in reads:
            if not filtered:
                unfiltered.setdefault((rel, qual), []).append(line)
    return unfiltered, found


def test_the_scan_is_not_blind():
    _, found = _scan()
    assert found >= MIN_READS_FOUND, f"only {found} KB reads found -- did a receiver or method get renamed?"


def test_every_scan_root_is_reached():
    """REACH's band spans the whole population; a small root (4 infra MCP files) could vanish inside it."""
    examined = REACH.examined(REPO_ROOT)
    unreached = [root for root in SCAN_ROOTS if not any(rel.startswith(root) for rel in examined)]
    assert not unreached, f"no production file examined under {unreached} -- did a root move?"


def test_a_read_offloaded_to_a_thread_is_still_a_read():
    """Moving a sync read behind ``asyncio.to_thread`` must not hide it from the guard (#16670)."""
    src = "import asyncio\nasync def f(kb, fid):\n    return await asyncio.to_thread(kb.get_fact, fid)\n"
    assert kb_reads(src) == [("f", 3, False)]


def test_every_unfiltered_kb_read_is_allowlisted():
    """The regression guard: a new read that skips the ownership filter fails here."""
    unfiltered, _ = _scan()
    unlisted = {key: lines for key, lines in unfiltered.items() if key not in ALLOWLIST}
    assert not unlisted, (
        "KB reads without the ownership filter (#16654) -- filter them through "
        "knowledge.search_filters / check_access, or add a classified entry to "
        f"repo_tests/kb_read_visibility_allowlist.py: {sorted(unlisted.items())}"
    )


def test_every_allowlist_entry_is_still_an_unfiltered_read():
    """Shrink-only: a path that starts filtering (or goes away) must leave the allowlist."""
    unfiltered, _ = _scan()
    stale = sorted(key for key in ALLOWLIST if key not in unfiltered)
    assert not stale, f"allowlist entries with no unfiltered read left -- delete them: {stale}"


def test_the_allowlist_ceiling_matches_and_never_rises():
    assert len(ALLOWLIST) == MAX_ALLOWLISTED, (
        f"ALLOWLIST has {len(ALLOWLIST)} entries but MAX_ALLOWLISTED is {MAX_ALLOWLISTED}: "
        "lower the ceiling with every entry removed; never raise it"
    )


def test_every_allowlist_reason_is_classified():
    unclassified = sorted(key for key, reason in ALLOWLIST.items() if not reason.startswith(_REASON_PREFIXES))
    assert not unclassified, f"reasons must start with one of {_REASON_PREFIXES}: {unclassified}"


# --- the detector itself fires (synthetic mutations) --------------------------------


def test_an_unfiltered_kb_search_is_found():
    assert kb_reads("async def f(kb):\n    return await kb.search('q')\n") == [("f", 2, False)]


def test_a_function_that_filters_is_marked_filtered():
    source = (
        "async def f(kb, uid):\n"
        "    where = await augment_search_request_with_permissions('q', uid)\n"
        "    return await kb.search('q', filters=where)\n"
    )
    assert kb_reads(source) == [("f", 3, True)]


def test_a_method_read_is_keyed_by_class_and_method():
    source = "class A:\n    def g(self):\n        return self.knowledge_base.get_fact('x')\n"
    assert kb_reads(source) == [("A.g", 3, False)]


def test_a_nested_function_owns_its_read():
    source = "def outer(kb):\n    async def inner():\n        return await kb.get_all_facts()\n    return inner\n"
    assert kb_reads(source) == [("outer.inner", 3, False)]


def test_rag_reads_count_and_unrelated_search_calls_do_not():
    assert kb_reads("async def r(rag_service):\n    return await rag_service.advanced_search('q')\n") == [
        ("r", 2, False)
    ]
    assert kb_reads("def h(pattern):\n    return pattern.search('x')\n") == []
