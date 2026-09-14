# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /multi-source/search filters results by the caller's access (#16665).

Uses the real KnowledgeOwnership.check_access rather than mocking it away, so
this proves the route's own filtering wiring, not just that a mock was called.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.ownership import KnowledgeOwnership


def _make_kb(search_results: list) -> MagicMock:
    kb = MagicMock()
    kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    kb.search = AsyncMock(return_value={"results": search_results})
    return kb


def _current_user(user_id: str, role: str = "user") -> dict:
    return {"user_id": user_id, "role": role}


@pytest.mark.asyncio
async def test_multi_source_search_hides_another_users_private_fact():
    from api.knowledge_search_aggregator import search
    from api.schemas_knowledge import SearchRequest

    mine = {"id": "f1", "content": "mine", "metadata": {"owner_id": "u1", "visibility": "private"}}
    others_private = {
        "id": "f2",
        "content": "not mine",
        "metadata": {"owner_id": "u99", "visibility": "private"},
    }
    kb = _make_kb([mine, others_private])

    with patch("api.knowledge_search_aggregator.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)):
        result = await search(
            MagicMock(), SearchRequest(query="test", include_sources=["facts"]), current_user=_current_user("u1")
        )

    ids = {f["id"] for f in result["facts"]}
    assert ids == {"f1"}, f"user u1 must not see u99's private fact: {result['facts']}"


@pytest.mark.asyncio
async def test_multi_source_search_lets_an_admin_read_another_users_private_fact():
    from api.knowledge_search_aggregator import search
    from api.schemas_knowledge import SearchRequest

    others_private = {
        "id": "f2",
        "content": "not mine",
        "metadata": {"owner_id": "u99", "visibility": "private"},
    }
    kb = _make_kb([others_private])

    with patch("api.knowledge_search_aggregator.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)):
        result = await search(
            MagicMock(),
            SearchRequest(query="test", include_sources=["facts"]),
            current_user=_current_user("u2", role="admin"),
        )

    ids = {f["id"] for f in result["facts"]}
    assert ids == {"f2"}, "an explicit admin read must see every fact (#16665)"
