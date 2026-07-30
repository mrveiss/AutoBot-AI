# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for ChatKnowledgeManager.search_chat_knowledge (#13024).

``self.knowledge_base.search(query, n_results=10)`` raised ``TypeError``
against the canonical ``KnowledgeBase.search()`` signature on every call --
this is a live path (wired to ``POST /search`` in this same file). Uses
``create_autospec(KnowledgeBase, instance=True)`` so an invalid kwarg would
reproduce the real production ``TypeError`` rather than being silently
accepted by a bare mock.
"""

from __future__ import annotations

from unittest.mock import create_autospec

import pytest

from api.chat_knowledge import ChatKnowledgeManager
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge_base import KnowledgeBase


def _manager_with_mock_kb(results):
    """Bare ChatKnowledgeManager instance without running the heavy __init__."""
    manager = object.__new__(ChatKnowledgeManager)
    manager.knowledge_base = create_autospec(KnowledgeBase, instance=True)
    manager.knowledge_base.search.return_value = results
    manager.chat_contexts = {}
    return manager


@pytest.mark.asyncio
async def test_search_chat_knowledge_returns_real_content():
    manager = _manager_with_mock_kb([{"content": "AutoBot uses Redis for caching", "metadata": {}, "score": 0.9}])

    results = await manager.search_chat_knowledge("redis", include_temporary=False)

    assert len(results) == 1
    assert results[0]["content"] == "AutoBot uses Redis for caching"
    manager.knowledge_base.search.assert_called_once_with("redis", top_k=10, filters=RESEARCH_QUARANTINE_FILTER)
