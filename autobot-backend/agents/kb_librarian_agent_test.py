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

#15255: ``__init__`` separately called ``config.get(...)`` four times, where
``config`` (``from config import config``) is the SSOT
``autobot_shared.ssot_config`` singleton -- it has no ``.get()``, so every
*real* construction of this class (``KBLibrarianAgent()`` in
``api/workflow.py``'s librarian step handler, and via ``get_kb_librarian()``
in ``api/kb_librarian.py`` / ``agent_orchestration/coordinator.py`` /
``agent_orchestration/agent_execution.py``) raised ``AttributeError``. The
tests above never caught this because ``_agent_with_mock_kb`` bypasses
``__init__`` entirely via ``object.__new__``. The tests below exercise the
real constructor.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock
from unittest.mock import create_autospec

import pytest

import agents.kb_librarian_agent as kb_agent_module
from agents.kb_librarian_agent import KBLibrarianAgent
from autobot_shared.ssot_config import config as ssot_config
from knowledge.ownership import KnowledgeOwnership
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge_base import KnowledgeBase


def _agent_with_mock_kb(results):
    agent = object.__new__(KBLibrarianAgent)
    agent.knowledge_base = create_autospec(KnowledgeBase, instance=True)
    agent.knowledge_base.search.return_value = results
    agent.knowledge_base.ownership_manager = KnowledgeOwnership(None)  # #16665: the real visibility decision
    return agent


@contextmanager
def _mocked_init_dependencies():
    """Patch everything ``__init__`` needs besides config_manager (#15255)."""
    with (
        mock.patch.object(kb_agent_module, "get_agent_provider_explicit", return_value="ollama"),
        mock.patch.object(kb_agent_module, "get_agent_endpoint_explicit", return_value="http://127.0.0.1:11434"),
        mock.patch.object(kb_agent_module, "get_agent_model_explicit", return_value="test-model"),
        mock.patch.object(kb_agent_module, "get_llm_service", return_value=mock.Mock()),
    ):
        yield


def test_init_raises_with_pre_fix_ssot_singleton_binding():
    """#15255 contrast mutation: red. The pre-fix ``config`` binding (the SSOT
    singleton) has no ``.get()`` and breaks construction."""
    with _mocked_init_dependencies(), mock.patch.object(kb_agent_module, "config_manager", ssot_config):
        with pytest.raises(AttributeError):
            KBLibrarianAgent()


def test_init_reads_runtime_defaults_via_config_manager():
    """#15255: green. Real construction reads defaults through config_manager.get()."""
    with _mocked_init_dependencies():
        agent = KBLibrarianAgent()

    assert agent.max_results == 5
    assert agent.similarity_threshold == 0.6
    assert agent.auto_summarize is False
    assert agent.auto_learning_enabled is True


@pytest.mark.asyncio
async def test_search_knowledge_returns_real_content_not_empty_list():
    agent = _agent_with_mock_kb(
        [
            {
                "content": "AutoBot uses Redis for caching",
                "metadata": {"source": "docs", "owner_id": "alice", "visibility": "private"},
                "score": 0.87,
            }
        ]
    )

    results = await agent.search_knowledge("how does autobot cache", limit=5, user_id="alice")

    assert results != []
    assert results[0]["content"] == "AutoBot uses Redis for caching"
    assert results[0]["source"] == "docs"
    agent.knowledge_base.search.assert_called_once_with(
        "how does autobot cache", top_k=5, filters=RESEARCH_QUARANTINE_FILTER
    )


@pytest.mark.asyncio
async def test_search_knowledge_never_returns_another_users_private_fact():
    """#16665: user B's search does not see user A's private fact; A and a platform fact are unaffected."""
    private = {"content": "alice only", "metadata": {"owner_id": "alice", "visibility": "private"}, "score": 0.9}
    platform = {"content": "for everyone", "metadata": {"owner_id": "admin", "visibility": "system"}, "score": 0.8}
    agent = _agent_with_mock_kb([private, platform])

    for_bob = await agent.search_knowledge("q", user_id="bob")
    for_alice = await agent.search_knowledge("q", user_id="alice")
    for_nobody = await agent.search_knowledge("q")

    assert [r["content"] for r in for_bob] == ["for everyone"]
    assert [r["content"] for r in for_alice] == ["alice only", "for everyone"]
    assert for_nobody == []


@pytest.mark.asyncio
async def test_process_query_and_answer_question_are_scoped_to_the_user():
    private = {"content": "alice only", "metadata": {"owner_id": "alice", "visibility": "private"}, "score": 0.9}
    agent = _agent_with_mock_kb([private])
    agent.enabled, agent.max_results, agent.auto_summarize = True, 5, False

    assert (await agent.process_query("q", user_id="bob"))["documents"] == []
    assert len((await agent.process_query("q", user_id="alice"))["documents"]) == 1
    assert (
        await agent.get_context_for_question("q", user_id="bob") == "No relevant information found in knowledge base."
    )


@pytest.mark.asyncio
async def test_search_knowledge_empty_kb_returns_empty_list():
    agent = _agent_with_mock_kb([])

    results = await agent.search_knowledge("nothing relevant", limit=5)

    assert results == []


@pytest.mark.asyncio
async def test_kb_resolved_lazily_from_canonical_accessor():
    """#18122 S4: no private KnowledgeBase at construction; the factory instance is used at first use."""
    with _mocked_init_dependencies():
        agent = KBLibrarianAgent()
    assert agent.knowledge_base is None
    kb = create_autospec(KnowledgeBase, instance=True)
    kb.get_stats.return_value = {"total_facts": 1}
    with mock.patch.object(kb_agent_module, "get_knowledge_base_async", mock.AsyncMock(return_value=kb)):
        assert await agent.get_knowledge_stats() == {"total_facts": 1}


@pytest.mark.asyncio
async def test_unavailable_canonical_kb_surfaces_as_error_not_a_private_instance():
    """#18122 D2: a failed init / cooldown (None) is reported, never papered over with a new KB."""
    with _mocked_init_dependencies():
        agent = KBLibrarianAgent()
    with mock.patch.object(kb_agent_module, "get_knowledge_base_async", mock.AsyncMock(return_value=None)):
        assert await agent.get_knowledge_stats() == {"error": "Failed to retrieve knowledge base stats"}


def _answering_agent(accessor_kb=None):
    agent = object.__new__(KBLibrarianAgent)
    agent.knowledge_base = accessor_kb
    agent.auto_learning_enabled = True
    agent.llm = mock.Mock(chat=mock.AsyncMock(return_value=mock.Mock(content="ok")))
    agent._trigger_auto_learning = mock.AsyncMock()
    return agent


@pytest.mark.asyncio
async def test_answer_question_skips_auto_learning_when_kb_unavailable():
    """#19156 review: an unavailable KB is not 'no results' -- auto-learning would fail per file."""
    agent = _answering_agent()
    with mock.patch.object(kb_agent_module, "get_knowledge_base_async", mock.AsyncMock(return_value=None)):
        result = await agent.answer_question("what is redis?")

    agent._trigger_auto_learning.assert_not_awaited()
    assert result["knowledge_base_results"] == []
    assert result["answer"] == "ok"


@pytest.mark.asyncio
async def test_answer_question_auto_learns_when_kb_up_but_empty():
    """#19156 review: a reachable-but-empty KB keeps the 'no results -> auto-learn' behaviour."""
    agent = _answering_agent(accessor_kb=_agent_with_mock_kb([]).knowledge_base)
    await agent.answer_question("what is redis?")

    agent._trigger_auto_learning.assert_awaited_once_with("what is redis?")
