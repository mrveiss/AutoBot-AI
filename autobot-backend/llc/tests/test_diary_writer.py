# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for AgentDiaryKbWriter (GH#8237)."""

import sys
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.diary_writer import AgentDiaryKbWriter, _format_diary_entry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kb_mock() -> AsyncMock:
    kb = AsyncMock()
    kb.store_fact = AsyncMock(return_value={"fact_id": "fact-001", "status": "created"})
    return kb


def _make_knowledge_module(kb_mock: AsyncMock) -> MagicMock:
    """Fake knowledge._composed module to avoid ChromaDB import chain."""
    mod = MagicMock()
    mod.get_knowledge_base = AsyncMock(return_value=kb_mock)
    return mod


def _make_tpl_modules(mock_learner_instance: AsyncMock) -> dict:
    """Return sys.modules patch dict for agents.task_pattern_learner.

    agents/__init__.py imports kb_librarian_agent which triggers the ChromaDB
    import chain that fails in the test environment.  We inject fake modules for
    ``agents`` and ``agents.task_pattern_learner`` to short-circuit that path.
    """
    mock_tpl_cls = MagicMock(return_value=mock_learner_instance)
    mock_tpl_mod = MagicMock()
    mock_tpl_mod.TaskPatternLearner = mock_tpl_cls
    # Provide a minimal LearnedStrategy stub so tests can construct return values
    mock_tpl_mod.LearnedStrategy = _FakeLearnedStrategy
    return {
        "agents": MagicMock(),
        "agents.task_pattern_learner": mock_tpl_mod,
    }


class _FakeLearnedStrategy:
    """Minimal stand-in for LearnedStrategy (avoids agents/__init__ import chain)."""

    def __init__(
        self,
        task_type: str = "",
        best_approach: str = "",
        best_prompt_template: str = "",
        avg_score: float = 0.0,
        sample_size: int = 0,
        confidence: float = 0.0,
        failure_patterns: Optional[list] = None,
    ) -> None:
        self.task_type = task_type
        self.best_approach = best_approach
        self.best_prompt_template = best_prompt_template
        self.avg_score = avg_score
        self.sample_size = sample_size
        self.confidence = confidence
        self.failure_patterns = failure_patterns or []


# ---------------------------------------------------------------------------
# _format_diary_entry
# ---------------------------------------------------------------------------


def test_format_diary_entry_minimal() -> None:
    entry = _format_diary_entry("run-1", "agent-A", None, "succeeded", None)
    assert "run-1" in entry
    assert "agent-A" in entry
    assert "succeeded" in entry


def test_format_diary_entry_with_work_item() -> None:
    entry = _format_diary_entry("run-2", "agent-B", "item-99", "failed", None)
    assert entry.startswith("[item-99]")
    assert "failed" in entry


def test_format_diary_entry_with_context() -> None:
    snap = {
        "title": "Fix login bug",
        "decisions": ["chose approach A", "rejected approach B"],
        "work_products": ["PR #123"],
        "comments_count": 3,
    }
    entry = _format_diary_entry("run-3", "agent-C", "item-1", "succeeded", snap)
    assert "Fix login bug" in entry
    assert "chose approach A" in entry
    assert "PR #123" in entry
    assert "3" in entry


def test_format_diary_entry_description_truncated() -> None:
    snap = {"description": "x" * 1000}
    entry = _format_diary_entry("run-4", "agent-D", None, "succeeded", snap)
    assert "x" * 500 in entry
    assert "x" * 501 not in entry


# ---------------------------------------------------------------------------
# AgentDiaryKbWriter.write_from_run — routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_from_run_calls_diary_and_patterns() -> None:
    writer = AgentDiaryKbWriter()
    with (
        patch.object(writer, "_write_diary_entry", new=AsyncMock()) as m_diary,
        patch.object(writer, "_write_patterns", new=AsyncMock()) as m_patterns,
    ):
        await writer.write_from_run(
            run_id="run-1",
            agent_id="agent-A",
            status="succeeded",
            work_item_id="item-1",
            context_snapshot={"title": "Do something"},
        )

    m_diary.assert_awaited_once()
    m_patterns.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_from_run_skips_non_terminal_status() -> None:
    writer = AgentDiaryKbWriter()
    with (
        patch.object(writer, "_write_diary_entry", new=AsyncMock()) as m_diary,
        patch.object(writer, "_write_patterns", new=AsyncMock()) as m_patterns,
    ):
        await writer.write_from_run(run_id="run-x", agent_id="agent-A", status="running")

    m_diary.assert_not_awaited()
    m_patterns.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_from_run_failed_status_is_terminal() -> None:
    writer = AgentDiaryKbWriter()
    with (
        patch.object(writer, "_write_diary_entry", new=AsyncMock()) as m_diary,
        patch.object(writer, "_write_patterns", new=AsyncMock()),
    ):
        await writer.write_from_run(run_id="run-f", agent_id="agent-A", status="failed")

    m_diary.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_from_run_handles_diary_exception() -> None:
    writer = AgentDiaryKbWriter()
    with (
        patch.object(writer, "_write_diary_entry", new=AsyncMock(side_effect=RuntimeError("KB down"))),
        patch.object(writer, "_write_patterns", new=AsyncMock()),
    ):
        # Must not raise — write_from_run is fully best-effort
        await writer.write_from_run(run_id="run-err", agent_id="agent-A", status="succeeded")


# ---------------------------------------------------------------------------
# _write_diary_entry — calls AgentDiaryService.write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_diary_entry_calls_agent_diary_write() -> None:
    mock_diary_svc = AsyncMock()
    mock_diary_svc.write = AsyncMock(return_value="fact-001")

    kb_mock = _make_kb_mock()
    knowledge_mod = _make_knowledge_module(kb_mock)

    with patch.dict(sys.modules, {"knowledge._composed": knowledge_mod}):
        with patch("memory.agent_diary.AgentDiaryService", return_value=mock_diary_svc):
            with patch.object(AgentDiaryKbWriter, "_upsert_with_llc_metadata", new=AsyncMock()):
                writer = AgentDiaryKbWriter()
                await writer._write_diary_entry(
                    run_id="run-1",
                    agent_id="agent-A",
                    status="succeeded",
                    work_item_id="item-1",
                    context_snapshot={"title": "My task"},
                )

    mock_diary_svc.write.assert_awaited_once()
    call_kwargs = mock_diary_svc.write.call_args.kwargs
    assert call_kwargs["agent_name"] == "agent-A"
    assert call_kwargs["session_id"] == "run-1"
    assert call_kwargs["topic"] == "heartbeat"
    assert "item-1" in call_kwargs["entry"]


@pytest.mark.asyncio
async def test_write_diary_entry_swallows_exception() -> None:
    with patch("memory.agent_diary.AgentDiaryService", side_effect=RuntimeError("no diary")):
        writer = AgentDiaryKbWriter()
        # Must not raise
        await writer._write_diary_entry(
            run_id="r", agent_id="a", status="succeeded", work_item_id=None, context_snapshot=None
        )


# ---------------------------------------------------------------------------
# _upsert_with_llc_metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_with_llc_metadata_calls_store_fact() -> None:
    kb_mock = _make_kb_mock()
    knowledge_mod = _make_knowledge_module(kb_mock)

    with patch.dict(sys.modules, {"knowledge._composed": knowledge_mod}):
        writer = AgentDiaryKbWriter()
        await writer._upsert_with_llc_metadata(
            agent_id="agent-A",
            fact_id="fact-001",
            entry="diary text",
            run_id="run-1",
            work_item_id="item-1",
        )

    kb_mock.store_fact.assert_awaited_once()
    call_kwargs = kb_mock.store_fact.call_args.kwargs
    meta = call_kwargs["metadata"]
    assert meta["run_id"] == "run-1"
    assert meta["work_item_id"] == "item-1"
    assert meta["category"] == "AGENT_DIARY"
    assert meta["date"] != ""


@pytest.mark.asyncio
async def test_upsert_swallows_kb_exception() -> None:
    knowledge_mod = MagicMock()
    knowledge_mod.get_knowledge_base = AsyncMock(side_effect=RuntimeError("chroma down"))

    with patch.dict(sys.modules, {"knowledge._composed": knowledge_mod}):
        writer = AgentDiaryKbWriter()
        # Must not raise
        await writer._upsert_with_llc_metadata(
            agent_id="agent-A", fact_id="f1", entry="x", run_id="r1", work_item_id=None
        )


# ---------------------------------------------------------------------------
# _write_patterns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_patterns_skips_when_no_outcomes() -> None:
    kb_mock = _make_kb_mock()
    knowledge_mod = _make_knowledge_module(kb_mock)

    with patch.dict(sys.modules, {"knowledge._composed": knowledge_mod}):
        writer = AgentDiaryKbWriter()
        await writer._write_patterns("run-1", "agent-A", "succeeded", {"outcomes": []})

    kb_mock.store_fact.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_patterns_skips_when_no_snapshot() -> None:
    kb_mock = _make_kb_mock()
    knowledge_mod = _make_knowledge_module(kb_mock)

    with patch.dict(sys.modules, {"knowledge._composed": knowledge_mod}):
        writer = AgentDiaryKbWriter()
        await writer._write_patterns("run-1", "agent-A", "succeeded", None)

    kb_mock.store_fact.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_patterns_indexes_learned_strategy() -> None:
    strategy = _FakeLearnedStrategy(
        task_type="llc_heartbeat",
        best_approach="use step-by-step decomposition",
        best_prompt_template="Decompose: {goal}",
        avg_score=0.85,
        sample_size=5,
        confidence=0.9,
        failure_patterns=["rushed commits"],
    )
    mock_learner = AsyncMock()
    mock_learner.learn_from_outcomes = AsyncMock(return_value=strategy)

    kb_mock = _make_kb_mock()
    knowledge_mod = _make_knowledge_module(kb_mock)
    tpl_modules = _make_tpl_modules(mock_learner)

    snap = {
        "task_type": "llc_heartbeat",
        "outcomes": [{"score": 0.9, "strategy_used": "decompose", "rationale": "worked"}],
    }

    with patch.dict(sys.modules, {"knowledge._composed": knowledge_mod, **tpl_modules}):
        writer = AgentDiaryKbWriter()
        await writer._write_patterns("run-1", "agent-A", "succeeded", snap)

    kb_mock.store_fact.assert_awaited_once()
    call_kwargs = kb_mock.store_fact.call_args.kwargs
    assert call_kwargs["metadata"]["type"] == "pattern"
    assert "use step-by-step" in call_kwargs["content"]


@pytest.mark.asyncio
async def test_write_patterns_swallows_learner_exception() -> None:
    mock_learner = AsyncMock()
    mock_learner.learn_from_outcomes = AsyncMock(side_effect=RuntimeError("LLM down"))
    tpl_modules = _make_tpl_modules(mock_learner)

    snap = {"outcomes": [{"score": 0.5, "strategy_used": "x"}]}

    with patch.dict(sys.modules, tpl_modules):
        writer = AgentDiaryKbWriter()
        # Must not raise
        await writer._write_patterns("run-1", "agent-A", "failed", snap)


# ---------------------------------------------------------------------------
# RoutineScheduler.on_run_complete hook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_run_complete_calls_writer_for_terminal_status() -> None:
    from llc.scheduler.routine_scheduler import RoutineScheduler

    scheduler = RoutineScheduler()
    calls = []

    async def fake_write_from_run(self_inst, **kw):
        calls.append(kw)

    with patch.object(AgentDiaryKbWriter, "write_from_run", fake_write_from_run):
        await scheduler.on_run_complete(
            run_id="run-1",
            agent_id="agent-A",
            status="succeeded",
            work_item_id="item-1",
            context_snapshot={"title": "Task A"},
        )

    assert len(calls) == 1
    assert calls[0] == {
        "run_id": "run-1",
        "agent_id": "agent-A",
        "status": "succeeded",
        "work_item_id": "item-1",
        "context_snapshot": {"title": "Task A"},
        "company_id": None,
        "session": None,
    }


@pytest.mark.asyncio
async def test_on_run_complete_ignores_cancelled_status() -> None:
    from llc.scheduler.routine_scheduler import RoutineScheduler

    scheduler = RoutineScheduler()
    calls = []

    async def fake_write_from_run(self_inst, **kw):
        calls.append(kw)

    with patch.object(AgentDiaryKbWriter, "write_from_run", fake_write_from_run):
        await scheduler.on_run_complete(run_id="run-x", agent_id="agent-A", status="cancelled")

    assert calls == []


@pytest.mark.asyncio
async def test_on_run_complete_swallows_writer_exception() -> None:
    from llc.scheduler.routine_scheduler import RoutineScheduler

    scheduler = RoutineScheduler()

    async def failing_write(self_inst, **kw):
        raise RuntimeError("writer failed")

    with patch.object(AgentDiaryKbWriter, "write_from_run", failing_write):
        # Must not raise
        await scheduler.on_run_complete(run_id="run-err", agent_id="agent-A", status="failed")


# ---------------------------------------------------------------------------
# Write guard tests (GH#8598)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_from_run_enforces_write_guard_on_ancestor_work_item() -> None:
    """Verify write_from_run() raises HTTPException(403) if requester writes to ancestor's work item."""
    from unittest.mock import AsyncMock, patch

    from fastapi import HTTPException

    writer = AgentDiaryKbWriter()
    mock_session = AsyncMock()
    company_id = "child-company-id"
    work_item_id = "work-item-id"

    with patch.object(
        writer, "_check_write_guard", new=AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden"))
    ):
        with pytest.raises(HTTPException) as exc_info:
            await writer.write_from_run(
                run_id="run-1",
                agent_id="agent-A",
                status="succeeded",
                work_item_id=work_item_id,
                company_id=company_id,
                session=mock_session,
            )
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_write_from_run_skips_guard_when_no_company_id() -> None:
    """Verify write_from_run() does not call guard if company_id is not provided."""
    from unittest.mock import AsyncMock, patch

    writer = AgentDiaryKbWriter()

    with patch.object(writer, "_write_diary_entry", new=AsyncMock()):
        with patch.object(writer, "_write_patterns", new=AsyncMock()):
            with patch.object(writer, "_check_write_guard", new=AsyncMock()) as mock_guard:
                await writer.write_from_run(
                    run_id="run-1",
                    agent_id="agent-A",
                    status="succeeded",
                    work_item_id="work-item-id",
                    company_id=None,  # No company_id, guard should not be called
                    session=None,
                )

                # Guard should not be called if company_id is None
                mock_guard.assert_not_called()


@pytest.mark.asyncio
async def test_check_write_guard_queries_work_item_company() -> None:
    """Verify _check_write_guard() fetches work item and calls assert_not_writing_to_ancestor_kb()."""
    import uuid
    from unittest.mock import AsyncMock, MagicMock, patch

    writer = AgentDiaryKbWriter()
    mock_session = AsyncMock()
    work_item_id = str(uuid.uuid4())
    company_id = "requester-company-id"
    work_item_company_id = "work-item-company-id"

    # Mock the work_item lookup
    mock_work_item = MagicMock()
    mock_work_item.company_id = work_item_company_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_work_item
    mock_session.execute.return_value = mock_result

    with patch("llc.kb.diary_writer.assert_not_writing_to_ancestor_kb", new=AsyncMock()) as mock_guard:
        await writer._check_write_guard(work_item_id, company_id, mock_session)

        # Guard should be called with the correct parameters
        mock_guard.assert_awaited_once_with(
            requester_org_id=company_id,
            target_org_id=work_item_company_id,
            session=mock_session,
        )
