# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The legacy essential-story path (tiered context off) reads as the turn's user, else nothing (#16665)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow.models import WorkflowSession
from chat_workflow.tiered_context_sources import prepend_memory_context
from knowledge.ownership import KnowledgeOwnership


def _facts():
    def fact(fid, content, **meta):
        return {"fact_id": fid, "content": content, "metadata": {"quality_score": 0.5, **meta}}

    return [
        fact("a", "alice private story", owner_id="alice", visibility="private"),
        fact("s", "platform story", owner_id="admin", visibility="system"),
    ]


async def _prompt(**session_meta):
    kb = MagicMock()
    kb.get_all_facts = AsyncMock(return_value=_facts())
    kb.ownership_manager = KnowledgeOwnership(None)
    kb.record_fact_access = AsyncMock()
    session = WorkflowSession(session_id="s1", workflow=None, metadata=session_meta)
    with (
        patch("chat_history.layers.TIERED_CONTEXT_ENABLED", False),
        patch("knowledge._composed.get_knowledge_base", AsyncMock(return_value=kb)),
        patch("memory.essential_story.EssentialStoryGenerator._get_cached", AsyncMock(return_value=None)),
        patch("memory.essential_story.EssentialStoryGenerator._set_cached", AsyncMock()),
        patch("memory.essential_story.EssentialStoryGenerator._get_token_budget", AsyncMock(return_value=600)),
    ):
        return await prepend_memory_context("SYSTEM", session, "hi", "m")


@pytest.mark.asyncio
async def test_the_turn_user_gets_their_own_story_and_not_another_users():
    mine, theirs = await _prompt(user_id="alice"), await _prompt(user_id="bob")

    assert "alice private story" in mine
    assert "alice private story" not in theirs and "platform story" in theirs


@pytest.mark.asyncio
async def test_a_turn_with_no_user_gets_no_story_at_all():
    """Not the non-private SYSTEM_SCOPE view: nothing."""
    assert await _prompt() == "SYSTEM"
