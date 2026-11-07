# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the research-quarantine filter fix at api/knowledge_search_aggregator.py (#13009).

This module is documented as "the single entry point for all knowledge
retrieval" (facts + graph + LLM context) -- all three unfiltered
``kb.search()`` call sites found here must exclude quarantined research
facts (#12622) the same way ``async_chat_workflow.py::_execute_kb_search``
already does.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.knowledge_graph_facts import visible_facts_page
from api.knowledge_search_aggregator import _search_facts, get_llm_context
from api.schemas_knowledge import ContextRequest
from knowledge.graph_limits import SCAN_BATCH
from knowledge.ownership import KnowledgeOwnership
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER

# #16665 added user_id/user_org_id/user_group_ids/is_admin params for
# fact-visibility filtering; these tests pass placeholder values since an
# empty kb.search() result has nothing for the filter to act on.
_USER_ID = "u1"
_CURRENT_USER = {"user_id": _USER_ID, "role": "user"}


@pytest.mark.asyncio
async def test_search_facts_applies_quarantine_filter():
    mock_kb = AsyncMock()
    mock_kb.search.return_value = {"results": []}
    result: dict = {"sources_searched": []}

    await _search_facts(mock_kb, "what is autobot", 5, result, _USER_ID, None, [], False)

    mock_kb.search.assert_called_once_with("what is autobot", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_get_facts_for_graph_lists_facts_with_quarantined_ones_left_out():
    """#19727: listed, not searched for "*"; get_all_facts excludes research quarantine by default (#13009)."""
    mock_kb = AsyncMock()
    mock_kb.get_all_facts.return_value = []

    await visible_facts_page(mock_kb, None, 25, 0, _USER_ID, None, [], False)

    mock_kb.get_all_facts.assert_awaited_once_with(limit=SCAN_BATCH, offset=0)
    mock_kb.search.assert_not_called()


@pytest.mark.asyncio
async def test_the_graph_has_facts_when_search_falls_back_and_star_matches_nothing():
    """#19727: with no embedding, search falls back to keywords, where "*" matches no fact."""
    facts = [
        {"fact_id": "f1", "content": "one", "metadata": {"category": "docs", "source": "a"}, "timestamp": ""},
        {"fact_id": "f2", "content": "two", "metadata": {"source": "b"}, "timestamp": ""},
    ]
    mock_kb = AsyncMock()
    mock_kb.search.return_value = {"results": []}  # what the keyword fallback answers for "*"
    mock_kb.get_all_facts.return_value = facts
    mock_kb.ownership_manager = KnowledgeOwnership(None)  # the real access check, as the read-path fakes use

    got = (await visible_facts_page(mock_kb, None, 25, 0, _USER_ID, None, [], True)).facts

    assert [fact["id"] for fact in got] == ["f1", "f2"], "the permission check needs the id search would give"
    assert [fact["category"] for fact in got] == ["docs", "general"]


@pytest.mark.asyncio
async def test_get_llm_context_applies_quarantine_filter():
    mock_kb = AsyncMock()
    mock_kb.search.return_value = {"results": []}

    req = SimpleNamespace(app=None)
    body = ContextRequest(query="what is autobot", include_documentation=False, include_relations=False)

    with patch(
        "api.knowledge_search_aggregator.get_or_create_knowledge_base",
        AsyncMock(return_value=mock_kb),
    ):
        await get_llm_context(req, body, current_user=_CURRENT_USER)

    mock_kb.search.assert_called_once_with("what is autobot", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)
