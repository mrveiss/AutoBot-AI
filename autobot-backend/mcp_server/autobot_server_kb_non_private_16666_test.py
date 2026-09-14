# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""MCP knowledge tools read non-private facts only (#16666 AC2).

Owner decision on #16654: an MCP token caller reads SYSTEM or PUBLIC facts, or facts with a
``general`` or ``autobot`` access level, never private, shared, group or organisation facts,
and never quarantined research. A caller's filter can only narrow that set. Each search test
has the KB return a private fact as well, as if the ``where`` had been ignored, so the
post-filter is exercised and not just trusted.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ssot_config import config
from knowledge.search_filters import (
    filter_non_private_results,
    is_non_private,
    non_private_where,
)

_SYSTEM = {"id": "s", "content": "doc", "score": 0.9, "metadata": {"visibility": "system"}}
_PRIVATE = {"id": "p", "content": "mine", "score": 0.9, "metadata": {"visibility": "private", "owner_id": "u1"}}
_EMBEDDED = (
    Path(__file__).resolve().parents[2]
    / "autobot-infrastructure/shared/mcp/tools/knowledge-base-mcp/autobot_knowledge_mcp/embedded.py"
)


@pytest.mark.parametrize(
    ("metadata", "readable"),
    [
        ({"visibility": "system"}, True),
        ({"visibility": "public"}, True),
        ({"access_level": "general"}, True),
        ({"access_level": "autobot"}, True),
        ({"visibility": "private", "owner_id": "u1"}, False),
        ({"visibility": "shared", "shared_with": ["u2"]}, False),
        ({"visibility": "group", "group_ids": ["g1"]}, False),
        ({"visibility": "organization", "organization_id": "o1"}, False),
        ({}, False),
        (None, False),
        ({"visibility": "system", "collection": config.research_quarantine_collection}, False),
    ],
)
def test_only_non_private_unquarantined_facts_are_readable(metadata, readable):
    assert is_non_private(metadata) is readable


def test_a_caller_filter_narrows_the_where_and_never_replaces_it():
    where = non_private_where({"visibility": "private"})
    assert where["$and"][:2] == non_private_where()["$and"]  # the non-private and quarantine clauses stay
    assert where["$and"][2] == {"visibility": "private"}  # ANDed in: private AND non-private matches nothing


def test_the_post_filter_drops_what_the_where_should_have():
    assert filter_non_private_results([_SYSTEM, _PRIVATE]) == [_SYSTEM]
    assert filter_non_private_results(None) == []


def _kb(search_results=(), fact=None):
    kb = MagicMock()
    kb.search = AsyncMock(return_value=list(search_results))
    kb.get_fact = MagicMock(return_value=fact)
    return kb


@pytest.mark.asyncio
async def test_mcp_search_returns_only_non_private_facts():
    from mcp.autobot_server import AutoBotMCPServer

    kb = _kb([_SYSTEM, _PRIVATE])
    with patch("knowledge._composed.get_knowledge_base", AsyncMock(return_value=kb)):
        result = await AutoBotMCPServer()._kb_search("q", filters={"category": "docs"}, limit=5)

    assert result == {"results": [_SYSTEM], "count": 1}
    assert kb.search.await_args.kwargs["filters"] == non_private_where({"category": "docs"})


@pytest.mark.asyncio
@pytest.mark.parametrize(("fact", "found"), [(_SYSTEM, True), (_PRIVATE, False)])
async def test_mcp_get_document_does_not_disclose_a_private_fact(fact, found):
    from mcp.autobot_server import AutoBotMCPServer

    with patch("knowledge._composed.get_knowledge_base", AsyncMock(return_value=_kb(fact=fact))):
        doc = await AutoBotMCPServer()._kb_get_document(fact["id"])

    assert doc == (fact if found else {"error": "Document not found", "doc_id": fact["id"]})


def _embedded_client(kb):
    """The embedded MCP client, loaded by path (its package isn't on the backend's path)."""
    spec = importlib.util.spec_from_file_location("autobot_knowledge_mcp_embedded_16666", _EMBEDDED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = module.EmbeddedKnowledgeClient.__new__(module.EmbeddedKnowledgeClient)
    client._ensure_initialized = AsyncMock(return_value=kb)
    return client


@pytest.mark.asyncio
async def test_the_embedded_client_search_returns_only_non_private_facts():
    kb = _kb([_SYSTEM, _PRIVATE])
    results = await _embedded_client(kb).search("q", top_k=5, filters={"category": "docs"})

    assert [r.content for r in results] == ["doc"]
    assert kb.search.await_args.kwargs["filters"] == non_private_where({"category": "docs"})
