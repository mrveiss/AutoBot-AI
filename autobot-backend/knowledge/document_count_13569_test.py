# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``KnowledgeBase.get_document_count`` exists and means one specific number (#13569).

`api/knowledge_mcp.py` awaited `kb.get_document_count()` at three sites and nothing
in the tree defined it, so every MCP knowledge-stats and resource call raised
``AttributeError: 'KnowledgeBase' object has no attribute 'get_document_count'``.

## Why the count delegates rather than counts

"How many documents" has three candidate answers -- source documents, embedding
chunks, raw collection entries -- and picking one by taste would have created a
second definition free to drift from the one already shipping. It does not need
picking, because the codebase already decided: ``StatsMixin._populate_redis_stats``
assigns ``total_documents``, ``total_vectors`` and ``total_chunks`` from a single
vector-store count, and every non-crashing producer of ``total_documents`` in the
tree reads it back out of ``get_stats()``. ``add_document`` routes through
``store_fact``, which writes exactly one embedding per document, so on this class
the three numbers are one number.

The near-miss worth naming is ``_count_facts`` (``knowledge/base.py``), which the
issue itself floated. It scans Redis ``fact:*`` keys -- a real count, of facts,
which ``get_stats`` already publishes as ``total_facts``. Returning it from a
method named for documents would be correct about facts and wrong about the
question asked, so `test_document_count_is_not_the_fact_count` pins the two apart
with deliberately different values. Equal fixtures would pass either way.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from knowledge.documents import DocumentsMixin

_MCP = Path(__file__).resolve().parents[1] / "api" / "knowledge_mcp.py"
_COMPOSED = Path(__file__).with_name("_composed.py")


class _Stub(DocumentsMixin):
    """Minimal host for the mixin: only ``get_stats`` is needed to answer."""

    def __init__(self, stats: dict) -> None:
        self._stats = stats

    async def get_stats(self) -> dict:  # overrides the mixin's NotImplementedError stub
        return self._stats


def _awaited_kb_methods(source: str) -> set[str]:
    """Names in ``await kb.<name>(...)``, taken from the AST.

    Parsed rather than grepped so a method named only in a docstring or comment
    cannot register as a call -- `test_prose_mentions_are_not_call_sites` holds
    that property against a fixture where the name appears in nothing else.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "kb":
            found.add(func.attr)
    return found


def test_the_mixin_defines_get_document_count() -> None:
    """The method the three MCP call sites await is actually defined."""
    assert hasattr(
        DocumentsMixin, "get_document_count"
    ), "get_document_count is undefined -- every awaiting call site raises AttributeError"


def test_documents_mixin_is_composed_into_the_knowledge_base() -> None:
    """Defining it on a mixin only helps if that mixin is one of the bases."""
    tree = ast.parse(_COMPOSED.read_text(encoding="utf-8"))
    bases: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "KnowledgeBase":
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
    assert bases, "no class KnowledgeBase found in _composed.py"
    assert "DocumentsMixin" in bases, f"DocumentsMixin is not a base of KnowledgeBase: {bases}"


@pytest.mark.asyncio
async def test_get_document_count_returns_the_canonical_total_documents() -> None:
    kb = _Stub({"total_documents": 42, "total_facts": 7, "total_chunks": 42})
    assert await kb.get_document_count() == 42


@pytest.mark.asyncio
async def test_document_count_is_not_the_fact_count() -> None:
    """Pins the two counters apart.

    ``total_facts`` is deliberately a different value from ``total_documents``
    here: with equal fixtures a delegate to the wrong key would pass.
    """
    kb = _Stub({"total_documents": 500, "total_facts": 3})
    assert await kb.get_document_count() == 500, "returned the fact count, not the document count"


@pytest.mark.asyncio
async def test_missing_key_degrades_to_zero_rather_than_raising() -> None:
    """``get_stats`` already returns a zeroed payload on error; don't re-raise over it."""
    assert await _Stub({}).get_document_count() == 0


def test_the_mcp_call_sites_await_a_method_that_now_exists() -> None:
    """The real call sites in knowledge_mcp.py resolve against the mixin.

    Positive control first: the detector must find a method it is known to find,
    or the assertion below is a claim about a broken parser rather than about the
    file. ``get_document_count`` is awaited on ``kb`` at three sites. The other members those
    sites read are tracked separately on #17966.
    """
    awaited = _awaited_kb_methods(_MCP.read_text(encoding="utf-8"))
    assert awaited, "parsed no `await kb.<method>()` calls at all -- detector is broken"
    assert (
        "get_document_count" in awaited
    ), f"knowledge_mcp.py no longer awaits get_document_count; found {sorted(awaited)}"
    assert hasattr(DocumentsMixin, "get_document_count")


def test_prose_mentions_are_not_call_sites() -> None:
    """Contrast fixture: the name in a comment and a docstring, and nowhere else.

    A `grep get_document_count` over this source returns hits, so a text-matching
    version of the check above would call it a call site. The AST has no ``Await``
    node here at all, so the parser reports it empty -- which is the difference
    being asserted.
    """
    prose_only = '''
"""A docstring mentioning get_document_count and await kb.get_document_count()."""
# await kb.get_document_count()  -- a commented-out call site
MESSAGE = "await kb.get_document_count() appears here only as text"
'''
    assert "get_document_count" in prose_only, "fixture lost the string it exists to carry"
    assert _awaited_kb_methods(prose_only) == set(), "a comment, docstring or string literal registered as a call site"
