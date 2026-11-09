# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LiveChatCandidate (#20843): pass/fail from the injected turn, criteria, judge, workspace, timeout, wiring."""

import asyncio
from pathlib import Path

import pytest

from eval.candidates import live_replay_candidate
from eval.live import LiveChatCandidate, LiveRunRecord, build_record
from eval.runner import TrajectoryReplayer
from eval.store import GoldenTrajectory

_LOCAL = "http://127.0.0.1:11434"


def _golden(task_class="code_fix", criteria=None, tools=None, mode="subsequence", status="completed"):
    return GoldenTrajectory(
        "g1",
        task_class,
        {"prompt": "do it"},
        tools or [],
        0.9,
        expected_status=status,
        tool_match=mode,
        success_criteria=criteria if criteria is not None else [],
    )


_MATCHES = [{"type": "output_pattern", "parameters": {"pattern": "DEFAULT"}, "description": "mentions default"}]


async def _kb_populated():
    return "populated"


async def _resolve(model):
    return _LOCAL


def _candidate(record_or_fn, **kw):
    async def turn(golden, model, workspace):
        return record_or_fn(golden, model, workspace) if callable(record_or_fn) else record_or_fn

    kw.setdefault("resolve_provider", lambda: "ollama")
    kw.setdefault("probe_kb", _kb_populated)
    return LiveChatCandidate(["m1"], "ollama", turn_runner=turn, resolve_endpoint=_resolve, **kw)


async def _run(candidate, golden):
    await candidate.prepare()
    return await candidate.runner_for("m1")(golden)


@pytest.mark.asyncio
async def test_a_clean_run_that_meets_its_criteria_passes_and_carries_the_pins():
    result = await _run(_candidate(LiveRunRecord(final_text="uses DEFAULT_TIMEOUT")), _golden(criteria=_MATCHES))
    assert result.passed is True and result.failure_categories == []
    assert (result.model, result.provider, result.tokens) == ("m1", "ollama", None)


@pytest.mark.asyncio
async def test_a_missed_criterion_fails_with_false_done_and_the_criterion_detail():
    result = await _run(_candidate(LiveRunRecord(final_text="done, all good")), _golden(criteria=_MATCHES))
    assert result.passed is False and result.failure_categories == ["false_done"]
    assert "mentions default" in result.criteria_detail


@pytest.mark.asyncio
async def test_a_wrong_tool_sequence_fails_even_with_no_category():
    record = LiveRunRecord(final_text="DEFAULT", tool_sequence=["web_search"])
    result = await _run(_candidate(record), _golden(criteria=_MATCHES, tools=["read_file"]))
    assert result.passed is False and result.failure_categories == []


@pytest.mark.asyncio
async def test_a_status_other_than_expected_fails():
    record = LiveRunRecord(final_text="DEFAULT", final_status="awaiting_approval")
    assert (await _run(_candidate(record), _golden(criteria=_MATCHES))).passed is False


@pytest.mark.asyncio
async def test_the_heuristic_false_done_is_labelled_in_the_detail():
    record = LiveRunRecord(final_text="all done", execution_history=[{"tool": "t", "status": "error"}])
    result = await _run(_candidate(record), _golden())
    assert result.failure_categories == ["false_done"] and "heuristic: false_done" in result.criteria_detail


@pytest.mark.asyncio
async def test_the_judge_runs_only_on_grounded_goldens_and_its_verdict_becomes_the_category():
    seen = []

    async def judge(record, golden):
        seen.append(golden.task_class)
        return True

    def fresh(golden, model, workspace):
        return LiveRunRecord(final_text="short", used_knowledge=True)

    grounded = await _run(_candidate(fresh, judge=judge), _golden("knowledge_qa"))
    ungrounded = await _run(_candidate(fresh, judge=judge), _golden("code_fix"))
    assert grounded.failure_categories == ["unsupported_claim"] and ungrounded.failure_categories == []
    assert seen == ["knowledge_qa"]


@pytest.mark.asyncio
async def test_each_turn_gets_its_own_throwaway_workspace_that_is_gone_afterwards():
    seen = []

    def turn(golden, model, workspace: Path):
        assert workspace.is_dir()
        seen.append(workspace)
        return LiveRunRecord(final_text="x")

    await _run(_candidate(turn), _golden())
    await _run(_candidate(turn), _golden())
    assert len(set(seen)) == 2 and not any(p.exists() for p in seen)


@pytest.mark.asyncio
async def test_the_workspace_is_removed_when_the_turn_raises():
    seen = []

    def turn(golden, model, workspace):
        seen.append(workspace)
        raise ConnectionError("down")

    with pytest.raises(Exception):
        await _run(_candidate(turn), _golden())
    assert seen and not seen[0].exists()


@pytest.mark.asyncio
async def test_a_live_timeout_is_a_failed_loop_stall_not_unmeasured():
    async def slow(golden, model, workspace):
        await asyncio.sleep(5)

    candidate = LiveChatCandidate(
        ["m1"],
        "ollama",
        turn_runner=slow,
        resolve_endpoint=_resolve,
        timeout_s=0.05,
        resolve_provider=lambda: "ollama",
        probe_kb=_kb_populated,
    )
    await candidate.prepare()
    report = await TrajectoryReplayer().run([_golden()], candidate.runner_for("m1"))
    (outcome,) = report.outcomes
    assert (outcome.passed, outcome.failure_categories, outcome.model) == (False, ["loop_stall"], "m1")
    assert outcome.classify() == "regression"


def test_the_factory_returns_a_live_candidate_and_unknown_models_are_refused():
    candidate = live_replay_candidate(["m1"], "ollama")
    assert isinstance(candidate, LiveChatCandidate)
    with pytest.raises(ValueError):
        candidate.runner_for("other")


def test_build_record_reads_the_graph_state_fields():
    state = {
        "all_llm_responses": ["", "first", "final answer"],
        "execution_history": [{"tool": "web_search", "status": "success"}],
        "tool_loop_count": 1,
        "iteration_count": 3,
        "used_knowledge": True,
        "rag_citations": [{"id": 1}],
    }
    record = build_record([{"type": "response", "content": "x", "metadata": {}}], state)
    assert (record.final_text, record.tool_sequence, record.final_status) == (
        "final answer",
        ["web_search"],
        "completed",
    )
    assert (record.tool_loop_count, record.iteration_count, record.used_knowledge) == (1, 3, True)
    assert build_record([], {"pending_approval": {"x": 1}}).final_status == "awaiting_approval"
    assert build_record([], {"error": "boom"}).final_status == "error"
