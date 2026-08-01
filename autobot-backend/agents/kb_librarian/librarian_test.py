# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for KBLibrarian.search_tool_knowledge / get_tool_instructions (#13024).

Both methods called ``knowledge_base.search(query, n_results=...)`` -- a kwarg
the canonical ``KnowledgeBase.search()`` (``knowledge/search.py``) does not
accept, so every call raised ``TypeError``, was swallowed by the method's own
broad ``except Exception``, and silently returned an empty result. These
tests use ``create_autospec(KnowledgeBase, instance=True)`` (not a bare
``AsyncMock``) so an invalid kwarg reproduces the exact production
``TypeError`` instead of being silently accepted by the mock.

Reachability: ``KBLibrarian`` itself is live (``agents/system_knowledge_manager.py``),
but these two specific methods have zero production callers today -- they are
reachable only via direct invocation (as these tests do). Fixed for
correctness per #13024's affected-call-site list; still dead code until
something calls them.
"""

from __future__ import annotations

from unittest.mock import create_autospec

import pytest

from agents.kb_librarian.librarian import KBLibrarian
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge_base import KnowledgeBase


def _autospec_kb(results):
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = results
    return mock_kb


@pytest.mark.asyncio
async def test_search_tool_knowledge_returns_real_content():
    """Previously always TypeError'd (n_results) -> [] every call; now returns facts."""
    mock_kb = _autospec_kb([{"content": "curl is a command-line tool", "metadata": {}}])
    librarian = KBLibrarian(mock_kb)

    result = await librarian.search_tool_knowledge("curl")

    assert result["documents_count"] > 0
    mock_kb.search.assert_any_call("curl tool", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_get_tool_instructions_returns_real_content():
    """Previously always TypeError'd (n_results) -> fell through to research; now parses KB hit."""
    mock_kb = _autospec_kb(
        [
            {
                "content": "Installation:\napt install curl\n\nUsage:\ncurl <url>\n",
                "metadata": {},
            }
        ]
    )
    librarian = KBLibrarian(mock_kb)

    instructions = await librarian.get_tool_instructions("curl")

    assert instructions is not None
    mock_kb.search.assert_called_once_with("curl installation usage", top_k=3, filters=RESEARCH_QUARANTINE_FILTER)
