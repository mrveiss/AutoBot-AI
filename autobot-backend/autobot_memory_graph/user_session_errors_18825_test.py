# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A graph failure in the session readers surfaces; it is never an empty list (#18825).

Both readers used to log and ``return []``, so the activities route answered an empty 200
while the graph was down. These run through the real ``AutoBotMemoryGraph`` mixin.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from autobot_memory_graph import AutoBotMemoryGraph
from autobot_memory_graph.owner_scope import UNSCOPED_ALL_USERS


def _graph() -> AutoBotMemoryGraph:
    graph = AutoBotMemoryGraph()
    graph._initialized = True
    graph.redis_client = Mock()
    return graph


@pytest.mark.asyncio
async def test_a_graph_failure_in_get_session_activities_is_raised_not_emptied():
    graph = _graph()
    graph._fetch_and_filter_activities = AsyncMock(side_effect=ConnectionError("graph down"))
    with pytest.raises(ConnectionError):
        await graph.get_session_activities("s1")


@pytest.mark.asyncio
async def test_get_session_activities_still_returns_newest_first():
    graph = _graph()
    graph._fetch_and_filter_activities = AsyncMock(
        return_value=[{"metadata": {"timestamp": "2026-01-01"}}, {"metadata": {"timestamp": "2026-02-01"}}]
    )
    activities = await graph.get_session_activities("s1")
    assert [a["metadata"]["timestamp"] for a in activities] == ["2026-02-01", "2026-01-01"]


@pytest.mark.asyncio
async def test_a_graph_failure_in_get_user_sessions_is_raised_not_emptied():
    graph = _graph()
    graph.get_relations = AsyncMock(side_effect=ConnectionError("graph down"))
    with pytest.raises(ConnectionError):
        await graph.get_user_sessions("u1")


@pytest.mark.asyncio
async def test_get_user_sessions_joins_owned_and_collaborative_without_duplicates():
    graph = _graph()
    owned = {"id": "e1", "metadata": {"session_id": "s1"}}
    shared = {"id": "e2", "metadata": {"session_id": "s2", "collaborators": ["u1"]}}
    stranger = {"id": "e3", "metadata": {"session_id": "s3", "collaborators": ["u9"]}}
    graph.get_relations = AsyncMock(return_value={"relations": [{"to": "e1"}]})
    graph.get_entity = AsyncMock(return_value=owned)
    graph.search_entities = AsyncMock(return_value=[owned, shared, stranger])
    sessions = await graph.get_user_sessions("u1")
    assert sessions == [owned, shared]
    assert graph.get_relations.await_args.kwargs["owner"] is UNSCOPED_ALL_USERS
