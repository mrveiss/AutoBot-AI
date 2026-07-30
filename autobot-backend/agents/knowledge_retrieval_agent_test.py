# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for KnowledgeRetrievalAgent.find_similar_documents (#13024).

``self.knowledge_base.search(query, n_results=top_k)`` raised ``TypeError``
against the canonical ``KnowledgeBase.search()`` signature. Uses
``create_autospec(KnowledgeBase, instance=True)`` so an invalid kwarg would
reproduce the real production ``TypeError``.

Reachability: ``KnowledgeRetrievalAgent`` has zero production instantiation
callers (confirmed by #13009's audit -- filed separately as #13028, a dead
code decision explicitly out of scope here). This fix and test are purely
mechanical correctness for #13024's affected-call-site list; the path
remains unreachable in production regardless.
"""

from __future__ import annotations

from unittest.mock import create_autospec

import pytest

from agents.knowledge_retrieval_agent import KnowledgeRetrievalAgent
from knowledge_base import KnowledgeBase


@pytest.mark.asyncio
async def test_find_similar_documents_returns_real_content():
    agent = object.__new__(KnowledgeRetrievalAgent)
    agent._kb_initialized = True
    agent.knowledge_base = create_autospec(KnowledgeBase, instance=True)
    agent.knowledge_base.search.return_value = [{"content": "fact", "score": 0.9}]

    result = await agent.find_similar_documents("query", top_k=5)

    assert result["status"] == "success"
    assert result["count"] == 1
    assert result["documents"][0]["content"] == "fact"
    agent.knowledge_base.search.assert_called_once_with("query", top_k=5)
