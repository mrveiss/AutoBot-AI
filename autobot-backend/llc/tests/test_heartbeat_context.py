# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for HeartbeatContextBuilder and LLCRAGAssembler (GH#8236)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.context_builder import HeartbeatContextBuilder
from llc.kb.rag_assembler import AssemblerProfile, LLCContext, LLCRAGAssembler

# ----------------------------------------------------------------- Helpers


def _make_work_item(
    company_id: str = "co1",
    project_id: str | None = None,
    goal_id: uuid.UUID | None = None,
    title: str = "Fix login bug",
    description: str = "The login fails when...",
) -> MagicMock:
    wi = MagicMock()
    wi.id = uuid.uuid4()
    wi.company_id = company_id
    wi.project_id = uuid.UUID(project_id) if project_id else None
    wi.goal_id = goal_id
    wi.title = title
    wi.description = description
    wi.status = "todo"
    wi.priority = "high"
    wi.acceptance_criteria = "Login succeeds"
    return wi


def _make_goal(
    title: str = "Q1 Goals",
    level: int = 1,
) -> MagicMock:
    g = MagicMock()
    g.id = uuid.uuid4()
    g.title = title
    g.level = level
    return g


# --------------------------------------------------------- LLCRAGAssembler


@pytest.fixture
def assembler() -> LLCRAGAssembler:
    return LLCRAGAssembler()


@pytest.mark.asyncio
async def test_assemble_returns_empty_on_chromadb_failure(assembler: LLCRAGAssembler) -> None:
    with patch(
        "llc.kb.rag_assembler.LLCRAGAssembler._query_collection",
        new_callable=AsyncMock,
        side_effect=Exception("ChromaDB down"),
    ):
        ctx = await assembler.assemble(
            company_id="co1",
            profile=AssemblerProfile.HEARTBEAT,
        )

    assert isinstance(ctx, LLCContext)
    assert ctx.company_id == "co1"
    assert ctx.profile == AssemblerProfile.HEARTBEAT


@pytest.mark.asyncio
async def test_assemble_merges_chunks_from_collections(assembler: LLCRAGAssembler) -> None:
    async def fake_query(client, coll_name, query_text, n_results):
        return {
            "chunks": [
                {"content": f"doc from {coll_name}", "metadata": {}, "similarity_score": 0.9, "source": coll_name}
            ],
            "sources": [coll_name],
        }

    with (
        patch.object(assembler, "_query_collection", new=fake_query),
        patch(
            "builtins.__import__",
            side_effect=lambda name, *a, **kw: (
                MagicMock() if name == "utils.async_chromadb_client" else __import__(name, *a, **kw)
            ),
        ),
    ):
        ctx = await assembler.assemble(
            company_id="co1",
            profile=AssemblerProfile.HEARTBEAT,
            project_id="proj1",
            agent_id="agent1",
        )

    assert isinstance(ctx, LLCContext)


@pytest.mark.asyncio
async def test_assemble_profile_handoff(assembler: LLCRAGAssembler) -> None:
    ctx = await assembler.assemble(
        company_id="co1",
        profile=AssemblerProfile.HANDOFF,
    )
    assert ctx.profile == AssemblerProfile.HANDOFF


# ------------------------------------------------ HeartbeatContextBuilder


@pytest.fixture
def builder() -> HeartbeatContextBuilder:
    rag = AsyncMock(spec=LLCRAGAssembler)
    rag.assemble.return_value = LLCContext(
        company_id="co1",
        profile=AssemblerProfile.HEARTBEAT,
        chunks=[{"content": "some doc", "metadata": {}, "similarity_score": 0.8, "source": "co1:company"}],
        sources=["co1:company"],
        metadata={"total_results": 1},
    )
    goal_svc = AsyncMock()
    goal_svc.get.return_value = None
    goal_svc.get_ancestors.return_value = []

    work_svc = AsyncMock()
    work_svc.get.return_value = _make_work_item(company_id="co1", project_id=None)

    return HeartbeatContextBuilder(
        rag_assembler=rag,
        goal_service=goal_svc,
        work_item_service=work_svc,
    )


@pytest.mark.asyncio
async def test_build_fat_returns_required_keys(builder: HeartbeatContextBuilder) -> None:
    session = AsyncMock()
    work_item_id = uuid.uuid4()

    result = await builder.build(
        session=session,
        agent_id="agent1",
        work_item_id=work_item_id,
        context_mode="fat",
    )

    assert "work_item_id" in result
    assert "work_item_detail" in result
    assert "goal_ancestry" in result
    assert "company_context" in result
    assert "project_context" in result
    assert "agent_memory" in result
    assert "similar_past_work" in result


@pytest.mark.asyncio
async def test_build_thin_returns_minimal_keys(builder: HeartbeatContextBuilder) -> None:
    session = AsyncMock()
    work_item_id = uuid.uuid4()

    result = await builder.build(
        session=session,
        agent_id="agent1",
        work_item_id=work_item_id,
        context_mode="thin",
    )

    assert "work_item_id" in result
    assert "api_base" in result


@pytest.mark.asyncio
async def test_build_unknown_mode_raises(builder: HeartbeatContextBuilder) -> None:
    session = AsyncMock()
    with pytest.raises(ValueError, match="Unknown context_mode"):
        await builder.build(
            session=session,
            agent_id="agent1",
            work_item_id=uuid.uuid4(),
            context_mode="superduper",
        )


@pytest.mark.asyncio
async def test_build_fat_missing_work_item_raises(builder: HeartbeatContextBuilder) -> None:
    builder.work_item_service.get.return_value = None
    session = AsyncMock()

    with pytest.raises(ValueError, match="not found"):
        await builder.build(
            session=session,
            agent_id="agent1",
            work_item_id=uuid.uuid4(),
            context_mode="fat",
        )


@pytest.mark.asyncio
async def test_build_fat_with_goal_ancestry(builder: HeartbeatContextBuilder) -> None:
    goal_id = uuid.uuid4()
    wi = _make_work_item(company_id="co1", goal_id=goal_id)
    builder.work_item_service.get.return_value = wi

    parent_goal = _make_goal(title="Top Level", level=0)
    child_goal = _make_goal(title="Project Goal", level=1)
    child_goal.id = goal_id
    builder.goal_service.get.return_value = child_goal
    builder.goal_service.get_ancestors.return_value = [parent_goal]

    session = AsyncMock()
    result = await builder.build(
        session=session,
        agent_id="agent1",
        work_item_id=wi.id,
        context_mode="fat",
    )

    assert len(result["goal_ancestry"]) == 2
    assert result["goal_ancestry"][0]["title"] == "Top Level"
    assert result["goal_ancestry"][1]["title"] == "Project Goal"


@pytest.mark.asyncio
async def test_build_fat_rag_failure_graceful(builder: HeartbeatContextBuilder) -> None:
    builder.rag_assembler.assemble.side_effect = Exception("RAG down")

    session = AsyncMock()
    result = await builder.build(
        session=session,
        agent_id="agent1",
        work_item_id=uuid.uuid4(),
        context_mode="fat",
    )

    assert result["company_context"] == {"chunks": [], "sources": []}


@pytest.mark.asyncio
async def test_build_fat_parallel_queries_invoked(builder: HeartbeatContextBuilder) -> None:
    wi = _make_work_item(company_id="co1", project_id=str(uuid.uuid4()))
    builder.work_item_service.get.return_value = wi

    session = AsyncMock()
    await builder.build(
        session=session,
        agent_id="agent1",
        work_item_id=wi.id,
        context_mode="fat",
    )

    assert builder.rag_assembler.assemble.call_count >= 2
