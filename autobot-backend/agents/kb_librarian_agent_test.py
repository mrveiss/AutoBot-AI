# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for KBLibrarianAgent.search_knowledge (#13025).

``self.knowledge_base.search(query, limit=limit)`` passes a non-None
``limit``, which routes the canonical ``KnowledgeBase.search()`` (#10666
consolidation, ``knowledge/search.py``) to the "Enhanced" path returning a
``Dict[str, Any]``, not the ``List[Dict]`` this method iterates
(``for result in results: result.get(...)``). Iterating a dict yields its
keys (strings), so ``result.get(...)`` raised ``AttributeError`` on every
non-empty search, silently caught and turned into ``[]``.

Reachability: ``KBLibrarianAgent`` is live via ``api/kb_librarian.py``,
``api/workflow.py``, and the ``KNOWLEDGE_RETRIEVAL``/``RAG`` handlers in
``agents/agent_orchestration/agent_execution.py`` -- all through
``process_query()`` -> ``search_knowledge()``.

Uses ``create_autospec(KnowledgeBase, instance=True)`` (not a bare mock) so
this test would have caught the real defect: an autospec of the Enhanced
path's dict return combined with list iteration reproduces the exact
production ``AttributeError``, and top_k= keeps it on the List-returning
Basic path.
"""

from __future__ import annotations

from unittest.mock import create_autospec

import pytest

from agents.kb_librarian_agent import KBLibrarianAgent
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge_base import KnowledgeBase


def _agent_with_mock_kb(results):
    agent = object.__new__(KBLibrarianAgent)
    agent.knowledge_base = create_autospec(KnowledgeBase, instance=True)
    agent.knowledge_base.search.return_value = results
    return agent


@pytest.mark.asyncio
async def test_search_knowledge_returns_real_content_not_empty_list():
    agent = _agent_with_mock_kb(
        [{"content": "AutoBot uses Redis for caching", "metadata": {"source": "docs"}, "score": 0.87}]
    )

    results = await agent.search_knowledge("how does autobot cache", limit=5)

    assert results != []
    assert results[0]["content"] == "AutoBot uses Redis for caching"
    assert results[0]["source"] == "docs"
    agent.knowledge_base.search.assert_called_once_with(
        "how does autobot cache", top_k=5, filters=RESEARCH_QUARANTINE_FILTER
    )


@pytest.mark.asyncio
async def test_search_knowledge_empty_kb_returns_empty_list():
    agent = _agent_with_mock_kb([])

    results = await agent.search_knowledge("nothing relevant", limit=5)

    assert results == []
