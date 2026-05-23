# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for LLCGoal model, GoalService, and /llc/goals API routes (GH#8212)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from llc.models.goal import GoalLevel, GoalStatus, LLCGoal
from llc.services.goal import GoalService


# ----------------------------------------------------------------- Fixtures


@pytest.fixture
def svc() -> GoalService:
    return GoalService()


def _make_goal(
    company_id: str = "co1",
    title: str = "Test Goal",
    level: str = GoalLevel.VISION.value,
    parent_goal_id: uuid.UUID | None = None,
) -> LLCGoal:
    g = LLCGoal(
        company_id=company_id,
        title=title,
        level=level,
        status=GoalStatus.DRAFT.value,
        parent_goal_id=parent_goal_id,
    )
    g.id = uuid.uuid4()
    return g


# --------------------------------------------------------- GoalService CRUD


@pytest.mark.asyncio
async def test_create_goal(svc: GoalService) -> None:
    session = AsyncMock()
    session.flush = AsyncMock()

    with patch.object(svc, "_index_goal", new=AsyncMock()):
        goal = await svc.create(
            session,
            company_id="co1",
            title="Vision 2030",
            level=GoalLevel.VISION,
        )

    assert goal.company_id == "co1"
    assert goal.title == "Vision 2030"
    assert goal.level == GoalLevel.VISION.value
    assert goal.status == GoalStatus.DRAFT.value
    assert goal.parent_goal_id is None
    session.add.assert_called_once_with(goal)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_goal_with_parent(svc: GoalService) -> None:
    parent_id = uuid.uuid4()
    session = AsyncMock()
    session.flush = AsyncMock()

    with patch.object(svc, "_index_goal", new=AsyncMock()):
        goal = await svc.create(
            session,
            company_id="co1",
            title="Key Result 1",
            level=GoalLevel.KEY_RESULT,
            parent_goal_id=parent_id,
        )

    assert goal.parent_goal_id == parent_id
    assert goal.level == GoalLevel.KEY_RESULT.value


@pytest.mark.asyncio
async def test_get_goal_not_found(svc: GoalService) -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    result = await svc.get(session, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_goal_found(svc: GoalService) -> None:
    goal = _make_goal()
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = goal
    session.execute = AsyncMock(return_value=mock_result)

    result = await svc.get(session, goal.id)
    assert result is goal


@pytest.mark.asyncio
async def test_update_goal(svc: GoalService) -> None:
    goal = _make_goal(title="Old Title")
    session = AsyncMock()
    session.flush = AsyncMock()

    with patch.object(svc, "get", new=AsyncMock(return_value=goal)), \
         patch.object(svc, "_index_goal", new=AsyncMock()):
        updated = await svc.update(session, goal.id, title="New Title")

    assert updated is goal
    assert goal.title == "New Title"


@pytest.mark.asyncio
async def test_update_goal_not_found(svc: GoalService) -> None:
    session = AsyncMock()
    with patch.object(svc, "get", new=AsyncMock(return_value=None)):
        result = await svc.update(session, uuid.uuid4(), title="X")
    assert result is None


@pytest.mark.asyncio
async def test_delete_goal_found(svc: GoalService) -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 1
    session.execute = AsyncMock(return_value=mock_result)

    deleted = await svc.delete(session, uuid.uuid4())
    assert deleted is True


@pytest.mark.asyncio
async def test_delete_goal_not_found(svc: GoalService) -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    session.execute = AsyncMock(return_value=mock_result)

    deleted = await svc.delete(session, uuid.uuid4())
    assert deleted is False


# ------------------------------------------------------ Ancestry traversal


@pytest.mark.asyncio
async def test_get_ancestors_empty_for_root(svc: GoalService) -> None:
    root = _make_goal()
    session = AsyncMock()

    with patch.object(svc, "get", new=AsyncMock(return_value=root)):
        ancestors = await svc.get_ancestors(session, root.id)

    assert ancestors == []


@pytest.mark.asyncio
async def test_get_ancestors_chain(svc: GoalService) -> None:
    vision = _make_goal(title="Vision", level=GoalLevel.VISION.value)
    mission = _make_goal(title="Mission", level=GoalLevel.MISSION.value)
    objective = _make_goal(title="Objective", level=GoalLevel.OBJECTIVE.value)
    mission.parent_goal_id = vision.id
    objective.parent_goal_id = mission.id

    lookup = {vision.id: vision, mission.id: mission, objective.id: objective}

    async def _get(session: object, goal_id: uuid.UUID) -> LLCGoal | None:
        return lookup.get(goal_id)

    session = AsyncMock()
    with patch.object(svc, "get", new=_get):
        ancestors = await svc.get_ancestors(session, objective.id)

    assert len(ancestors) == 2
    assert ancestors[0] is vision
    assert ancestors[1] is mission


@pytest.mark.asyncio
async def test_get_subtree_single_node(svc: GoalService) -> None:
    root = _make_goal()
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    with patch.object(svc, "get", new=AsyncMock(return_value=root)):
        subtree = await svc.get_subtree(session, root.id)

    assert len(subtree) == 1
    assert subtree[0] is root


@pytest.mark.asyncio
async def test_get_subtree_with_children(svc: GoalService) -> None:
    vision = _make_goal(title="Vision")
    mission1 = _make_goal(title="Mission 1")
    mission2 = _make_goal(title="Mission 2")
    mission1.parent_goal_id = vision.id
    mission2.parent_goal_id = vision.id

    call_count = 0

    async def _execute(stmt: object) -> MagicMock:
        nonlocal call_count
        result = MagicMock()
        if call_count == 0:
            result.scalars.return_value.all.return_value = [mission1, mission2]
        else:
            result.scalars.return_value.all.return_value = []
        call_count += 1
        return result

    session = AsyncMock()
    session.execute = _execute

    with patch.object(svc, "get", new=AsyncMock(return_value=vision)):
        subtree = await svc.get_subtree(session, vision.id)

    assert len(subtree) == 3


# ------------------------------------------------------- KB indexing


@pytest.mark.asyncio
async def test_index_goal_upserts_to_chroma(svc: GoalService) -> None:
    goal = _make_goal(company_id="co_test", title="Vision 2030")
    goal.description = "Long-term vision statement"

    mock_collection = AsyncMock()
    mock_client = AsyncMock()
    mock_client.get_or_create_collection = AsyncMock(return_value=mock_collection)

    with patch(
        "llc.services.goal.get_async_chromadb_client",
        new=AsyncMock(return_value=mock_client),
    ):
        await svc._index_goal(goal)

    mock_collection.upsert.assert_awaited_once()
    call_kwargs = mock_collection.upsert.call_args
    assert call_kwargs.kwargs["ids"] == [str(goal.id)]
    assert "Vision 2030" in call_kwargs.kwargs["documents"][0]


@pytest.mark.asyncio
async def test_index_goal_swallows_chroma_error(svc: GoalService) -> None:
    goal = _make_goal()

    with patch(
        "llc.services.goal.get_async_chromadb_client",
        new=AsyncMock(side_effect=RuntimeError("chroma down")),
    ):
        await svc._index_goal(goal)
