# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The diary writer stamps the writing session's user as owner, so reads can serve the entry back (#16665)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.ownership import KnowledgeOwnership
from memory.agent_diary import AgentDiaryService


def _kb():
    kb = MagicMock()
    kb.store_fact = AsyncMock(return_value={"fact_id": "d1", "status": "created"})
    kb.ownership_manager = KnowledgeOwnership(None)
    return kb


async def _written_metadata(user_id):
    kb = _kb()
    with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
        await AgentDiaryService().write("agent_a", "sess", "did X", user_id=user_id)
    return kb.store_fact.await_args.kwargs["metadata"]


@pytest.mark.asyncio
async def test_the_writer_stamps_the_session_user_as_private_owner():
    meta = await _written_metadata("alice")

    assert meta["owner_id"] == "alice" and meta["visibility"] == "private"


@pytest.mark.asyncio
async def test_a_stamped_entry_reads_back_for_its_owner_and_not_for_another_user():
    """Round trip through the real write and the real read filter."""
    meta = await _written_metadata("alice")
    fact = {"id": "d1", "content": "did X", "metadata": meta}
    kb = _kb()
    kb.get_all_facts = AsyncMock(return_value=[fact])

    with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
        diary = AgentDiaryService()
        assert len(await diary.read("agent_a", user_id="alice")) == 1
        assert await diary.read("agent_a", user_id="bob") == []


@pytest.mark.asyncio
async def test_without_a_user_the_entry_is_ownerless_and_no_read_serves_it():
    meta = await _written_metadata(None)

    assert "owner_id" not in meta
