# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LiveChatCandidate (#20843): pass/fail from the injected turn, criteria, judge, workspace, timeout, wiring."""

import asyncio
import threading
from pathlib import Path

import pytest

from autobot_shared.eventually import eventually
from eval.candidates import live_replay_candidate
from eval.live import LiveChatCandidate, LiveRunRecord, build_record
from eval.runner import RecordingUnusable, TrajectoryReplayer
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
async def test_a_wrong_tool_sequence_fails_and_the_unexpected_tool_is_a_forbidden_tool_category():
    record = LiveRunRecord(final_text="DEFAULT", tool_sequence=["web_search"])
    result = await _run(_candidate(record), _golden(criteria=_MATCHES, tools=["read_file"]))
    assert result.passed is False and result.failure_categories == ["forbidden_tool"]


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


@pytest.mark.asyncio
async def test_a_cancelled_workspace_allocation_is_still_removed(monkeypatch):
    from eval import live

    made = []
    real = live._make_workspace

    entered = threading.Event()

    def slow_make(root):
        import time

        entered.set()
        time.sleep(0.2)
        path = real(root)
        made.append(path)
        return path

    monkeypatch.setattr(live, "_make_workspace", slow_make)
    task = asyncio.ensure_future(live._allocate_workspace(""))
    await eventually(lambda: entered.is_set())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await eventually(lambda: made and not Path(made[0]).exists())
    assert made and not Path(made[0]).exists()


@pytest.mark.asyncio
async def test_a_workspace_that_cannot_be_removed_is_reported_by_name_not_path(monkeypatch, caplog):
    from eval import live

    def refuse(path):
        raise PermissionError("busy")

    monkeypatch.setattr(live.shutil, "rmtree", refuse)
    workspace = live._make_workspace("")
    try:
        with caplog.at_level("WARNING"):
            live._remove_workspace(workspace)
        assert Path(workspace).name in caplog.text and workspace not in caplog.text
    finally:
        monkeypatch.undo()
        live._remove_workspace(workspace)


@pytest.mark.asyncio
async def test_a_judge_that_raises_is_not_run_and_does_not_end_the_replay():
    async def broken(record, golden):
        raise ValueError("judge exploded")

    def fresh(golden, model, workspace):
        return LiveRunRecord(final_text="a long enough answer " * 5, used_knowledge=True)

    candidate = _candidate(fresh, judge=broken)
    await candidate.prepare()
    goldens = [_golden("knowledge_qa", criteria=_MATCHES), _golden("code_fix", criteria=_MATCHES)]
    report = await TrajectoryReplayer().run(goldens, candidate.runner_for("m1"))
    assert [o.classify() for o in report.outcomes][0] == "unmeasured" and len(report.outcomes) == 2


@pytest.mark.asyncio
async def test_a_grounded_golden_with_no_content_criteria_and_no_judge_is_not_run():
    with pytest.raises(RecordingUnusable, match="no content criteria"):
        await _run(_candidate(LiveRunRecord(final_text="ok")), _golden("knowledge_qa"))


@pytest.mark.asyncio
async def test_an_explicit_grounding_criterion_needs_a_populated_knowledge_base_on_any_task_class():
    async def empty():
        return "empty"

    grounding = [{"type": "resource_exists", "parameters": {"key": "grounded"}}]
    candidate = _candidate(LiveRunRecord(final_text="DEFAULT"), probe_kb=empty)
    with pytest.raises(RecordingUnusable, match="knowledge base is empty"):
        await _run(candidate, _golden("code_fix", criteria=_MATCHES + grounding))


@pytest.mark.asyncio
async def test_a_turn_that_answered_nothing_and_called_nothing_is_not_run_not_a_pass():
    with pytest.raises(RecordingUnusable, match="no answer"):
        await _run(_candidate(LiveRunRecord()), _golden("code_fix"))


@pytest.mark.asyncio
async def test_a_direct_single_model_candidate_carries_its_timeout_model_and_loop_stall():
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
    report = await TrajectoryReplayer().run([_golden()], candidate)  # the candidate itself, not runner_for
    (outcome,) = report.outcomes
    assert (outcome.model, outcome.failure_categories) == ("m1", ["loop_stall"])


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_a_non_positive_or_non_finite_timeout_is_refused(bad):
    with pytest.raises(ValueError, match="timeout"):
        LiveChatCandidate(["m1"], "ollama", timeout_s=bad)


def test_an_out_of_range_environment_timeout_is_clamped_to_the_registered_range(monkeypatch):
    monkeypatch.setenv("AUTOBOT_EVAL_LIVE_TIMEOUT_S", "0")
    assert LiveChatCandidate(["m1"], "ollama").timeout_s == 300.0  # non-positive: back to the default
    monkeypatch.setenv("AUTOBOT_EVAL_LIVE_TIMEOUT_S", "999999")
    assert LiveChatCandidate(["m1"], "ollama").timeout_s == 3600.0
    monkeypatch.setenv("AUTOBOT_EVAL_LIVE_TIMEOUT_S", "nan")
    assert LiveChatCandidate(["m1"], "ollama").timeout_s == 300.0


@pytest.mark.asyncio
async def test_an_endpoint_that_moves_to_a_public_one_after_prepare_is_refused_before_the_turn(monkeypatch):
    monkeypatch.delenv("AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER", raising=False)
    where = {"url": _LOCAL}
    ran = []

    async def resolve(model):
        return where["url"]

    def turn(golden, model, workspace):
        ran.append(1)
        return LiveRunRecord(final_text="DEFAULT")

    candidate = _candidate(turn)
    candidate.resolve_endpoint = resolve
    await candidate.prepare()
    where["url"] = "http://8.8.8.8:11434"
    with pytest.raises(RecordingUnusable):
        await candidate.runner_for("m1")(_golden(criteria=_MATCHES))
    assert ran == []
    monkeypatch.setenv("AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER", "true")
    await candidate.runner_for("m1")(_golden(criteria=_MATCHES))
    assert candidate.localities["m1"].local_only is False  # the report states the locality actually used
