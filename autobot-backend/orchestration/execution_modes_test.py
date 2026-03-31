# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for execution_modes.py — Issue #2148.

Covers:
- DryRunValidator: valid workflow, broken references, duplicate IDs,
  cycle detection, agent registration warnings, unreachable-step warnings.
- DebugController: start/end session, pause/resume, skip, retry with params.
- WorkflowExecutor integration: DRY_RUN returns report, DEBUG pauses per
  group, NORMAL mode is unaffected.
"""

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import pytest

from orchestration.execution_modes import (
    DebugController,
    DebugSessionState,
    DebugStepResult,
    DryRunReport,
    DryRunValidator,
    ExecutionMode,
    StepPlan,
)
from orchestration.workflow_executor import WorkflowExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step(
    step_id: str,
    action: str = "do_thing",
    agent: Optional[str] = None,
    deps: Optional[List[str]] = None,
) -> Dict[str, Any]:
    step: Dict[str, Any] = {"id": step_id, "action": action}
    if agent:
        step["assigned_agent"] = agent
    if deps:
        step["dependencies"] = deps
    return step


def _make_executor() -> WorkflowExecutor:
    """Create a WorkflowExecutor with no-op callbacks."""
    return WorkflowExecutor(
        agent_registry={},
        agent_interactions=[],
        reserve_agent_callback=lambda _: None,
        release_agent_callback=lambda _: None,
        update_performance_callback=lambda *_: None,
    )


# ---------------------------------------------------------------------------
# ExecutionMode enum
# ---------------------------------------------------------------------------


class TestExecutionMode:
    def test_values(self):
        assert ExecutionMode.NORMAL == "normal"
        assert ExecutionMode.DRY_RUN == "dry_run"
        assert ExecutionMode.DEBUG == "debug"

    def test_from_string(self):
        assert ExecutionMode("dry_run") is ExecutionMode.DRY_RUN


# ---------------------------------------------------------------------------
# DryRunValidator — valid workflow
# ---------------------------------------------------------------------------


class TestDryRunValidatorValid:
    def test_single_step_valid(self):
        steps = [_make_step("s1")]
        report = DryRunValidator().validate_workflow(steps)
        assert report.valid is True
        assert report.issues == []
        assert len(report.execution_plan) == 1

    def test_two_independent_steps_same_group(self):
        steps = [_make_step("a"), _make_step("b")]
        report = DryRunValidator().validate_workflow(steps)
        assert report.valid is True
        plan_by_id = {p.step_id: p for p in report.execution_plan}
        assert plan_by_id["a"].parallel_group == plan_by_id["b"].parallel_group

    def test_linear_dependency_chain(self):
        steps = [_make_step("a"), _make_step("b", deps=["a"]), _make_step("c", deps=["b"])]
        report = DryRunValidator().validate_workflow(steps)
        assert report.valid is True
        assert len(report.execution_plan) == 3
        plan_by_id = {p.step_id: p for p in report.execution_plan}
        assert plan_by_id["a"].parallel_group < plan_by_id["b"].parallel_group
        assert plan_by_id["b"].parallel_group < plan_by_id["c"].parallel_group

    def test_step_plan_fields_populated(self):
        steps = [_make_step("s1", action="run_cmd", agent="agent-1")]
        report = DryRunValidator().validate_workflow(steps)
        plan = report.execution_plan[0]
        assert isinstance(plan, StepPlan)
        assert plan.step_id == "s1"
        assert plan.action == "run_cmd"
        assert plan.assigned_agent == "agent-1"
        assert plan.parallel_group == 0


# ---------------------------------------------------------------------------
# DryRunValidator — issue detection (fatal)
# ---------------------------------------------------------------------------


class TestDryRunValidatorIssues:
    def test_missing_id_field(self):
        steps = [{"action": "do_it"}]  # no 'id'
        report = DryRunValidator().validate_workflow(steps)
        assert report.valid is False
        assert any("missing required field 'id'" in i for i in report.issues)

    def test_missing_action_field(self):
        steps = [{"id": "s1"}]  # no 'action'
        report = DryRunValidator().validate_workflow(steps)
        assert report.valid is False
        assert any("missing required field 'action'" in i for i in report.issues)

    def test_duplicate_step_ids(self):
        steps = [_make_step("dup"), _make_step("dup")]
        report = DryRunValidator().validate_workflow(steps)
        assert report.valid is False
        assert any("Duplicate step id 'dup'" in i for i in report.issues)

    def test_broken_dependency_reference(self):
        steps = [_make_step("s1", deps=["ghost"])]
        report = DryRunValidator().validate_workflow(steps)
        assert report.valid is False
        assert any("'ghost' does not exist" in i for i in report.issues)

    def test_broken_edge_source(self):
        steps = [_make_step("a")]
        edges = [{"source": "ghost", "target": "a"}]
        report = DryRunValidator().validate_workflow(steps, edges)
        assert report.valid is False
        assert any("'ghost'" in i for i in report.issues)

    def test_broken_edge_target(self):
        steps = [_make_step("a")]
        edges = [{"source": "a", "target": "ghost"}]
        report = DryRunValidator().validate_workflow(steps, edges)
        assert report.valid is False
        assert any("'ghost'" in i for i in report.issues)

    def test_cycle_via_dependencies(self):
        steps = [_make_step("a", deps=["b"]), _make_step("b", deps=["a"])]
        report = DryRunValidator().validate_workflow(steps)
        assert report.valid is False
        assert any("Cycle detected" in i for i in report.issues)

    def test_cycle_via_edges(self):
        steps = [_make_step("a"), _make_step("b")]
        edges = [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},
        ]
        report = DryRunValidator().validate_workflow(steps, edges)
        assert report.valid is False
        assert any("Cycle detected" in i for i in report.issues)

    def test_execution_plan_empty_on_issues(self):
        """Execution plan must not be generated when there are fatal issues."""
        steps = [{"action": "do_it"}]  # no 'id'
        report = DryRunValidator().validate_workflow(steps)
        assert report.execution_plan == []


# ---------------------------------------------------------------------------
# DryRunValidator — warning detection (non-fatal)
# ---------------------------------------------------------------------------


class TestDryRunValidatorWarnings:
    def test_agent_not_registered(self):
        steps = [_make_step("s1", agent="unknown-agent")]
        validator = DryRunValidator(registered_agent_ids=["known-agent"])
        report = validator.validate_workflow(steps)
        assert report.valid is True  # warning only
        assert any("'unknown-agent' is not registered" in w for w in report.warnings)

    def test_no_warning_when_agent_registered(self):
        steps = [_make_step("s1", agent="known-agent")]
        validator = DryRunValidator(registered_agent_ids=["known-agent"])
        report = validator.validate_workflow(steps)
        assert not any("is not registered" in w for w in report.warnings)

    def test_no_agent_check_when_registry_empty(self):
        steps = [_make_step("s1", agent="any-agent")]
        report = DryRunValidator().validate_workflow(steps)
        assert not any("is not registered" in w for w in report.warnings)

    def test_unreachable_step_warning(self):
        steps = [_make_step("a"), _make_step("b"), _make_step("orphan")]
        # Edge only connects a→b; 'orphan' has no incoming or outgoing edges
        edges = [{"source": "a", "target": "b"}]
        report = DryRunValidator().validate_workflow(steps, edges)
        assert report.valid is True
        assert any("'orphan' is unreachable" in w for w in report.warnings)

    def test_no_reachability_check_without_edges(self):
        """Linear workflow (no edges) must not trigger reachability warnings."""
        steps = [_make_step("a"), _make_step("b")]
        report = DryRunValidator().validate_workflow(steps)
        assert not any("unreachable" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# DebugController — session lifecycle
# ---------------------------------------------------------------------------


class TestDebugControllerLifecycle:
    def test_start_returns_unique_ids(self):
        ctrl = DebugController()
        id1 = ctrl.start_debug_session("exec-1")
        id2 = ctrl.start_debug_session("exec-2")
        assert id1 != id2

    def test_get_session_returns_session(self):
        ctrl = DebugController()
        sid = ctrl.start_debug_session("exec-1")
        session = ctrl.get_session(sid)
        assert session is not None
        assert session.session_id == sid
        assert session.execution_id == "exec-1"

    def test_get_session_unknown_returns_none(self):
        ctrl = DebugController()
        assert ctrl.get_session("no-such-id") is None

    def test_end_session_removes_it(self):
        ctrl = DebugController()
        sid = ctrl.start_debug_session("exec-1")
        ctrl.end_session(sid)
        assert ctrl.get_session(sid) is None

    def test_end_unknown_session_noop(self):
        ctrl = DebugController()
        ctrl.end_session("ghost")  # should not raise


# ---------------------------------------------------------------------------
# DebugController — pause / continue
# ---------------------------------------------------------------------------


class TestDebugControllerPauseResume:
    @pytest.mark.asyncio
    async def test_pause_and_continue(self):
        ctrl = DebugController()
        sid = ctrl.start_debug_session("exec-1")
        step_result = DebugStepResult(
            step_id="s1", status="completed", result={"success": True}, error=None
        )

        async def _continue_soon():
            await asyncio.sleep(0.01)
            ctrl.continue_session(sid)

        asyncio.create_task(_continue_soon())
        action = await ctrl.pause_after_step(sid, step_result)

        assert action == "continue"
        session = ctrl.get_session(sid)
        assert session is not None
        assert session.step_history[0].step_id == "s1"
        assert session.state == DebugSessionState.RUNNING

    @pytest.mark.asyncio
    async def test_pause_and_skip(self):
        ctrl = DebugController()
        sid = ctrl.start_debug_session("exec-1")
        step_result = DebugStepResult(
            step_id="s2", status="completed", result=None, error=None
        )

        async def _skip_soon():
            await asyncio.sleep(0.01)
            ctrl.skip_step(sid)

        asyncio.create_task(_skip_soon())
        action = await ctrl.pause_after_step(sid, step_result)
        assert action == "skip"

    @pytest.mark.asyncio
    async def test_pause_and_retry(self):
        ctrl = DebugController()
        sid = ctrl.start_debug_session("exec-1")
        step_result = DebugStepResult(
            step_id="s3", status="failed", result=None, error="timeout"
        )
        modified = {"timeout": 120}

        async def _retry_soon():
            await asyncio.sleep(0.01)
            ctrl.retry_step(sid, modified_params=modified)

        asyncio.create_task(_retry_soon())
        action = await ctrl.pause_after_step(sid, step_result)
        assert action == "retry"
        session = ctrl.get_session(sid)
        assert session is not None
        assert session.pending_retry_params == modified

    @pytest.mark.asyncio
    async def test_step_history_accumulates(self):
        ctrl = DebugController()
        sid = ctrl.start_debug_session("exec-1")

        for i in range(3):
            result = DebugStepResult(
                step_id=f"s{i}", status="completed", result={"success": True}, error=None
            )

            async def _continue(s=sid):
                await asyncio.sleep(0.01)
                ctrl.continue_session(s)

            asyncio.create_task(_continue())
            await ctrl.pause_after_step(sid, result)

        session = ctrl.get_session(sid)
        assert session is not None
        assert len(session.step_history) == 3


# ---------------------------------------------------------------------------
# DebugController — error paths
# ---------------------------------------------------------------------------


class TestDebugControllerErrors:
    def test_continue_not_waiting_raises(self):
        ctrl = DebugController()
        sid = ctrl.start_debug_session("exec-1")
        # Session starts in RUNNING state — continue should raise
        with pytest.raises(RuntimeError, match="WAITING"):
            ctrl.continue_session(sid)

    def test_skip_unknown_session_raises(self):
        ctrl = DebugController()
        with pytest.raises(KeyError):
            ctrl.skip_step("unknown")

    def test_retry_not_waiting_raises(self):
        ctrl = DebugController()
        sid = ctrl.start_debug_session("exec-1")
        with pytest.raises(RuntimeError, match="WAITING"):
            ctrl.retry_step(sid)


# ---------------------------------------------------------------------------
# WorkflowExecutor integration — DRY_RUN mode
# ---------------------------------------------------------------------------


class TestWorkflowExecutorDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_report(self):
        executor = _make_executor()
        steps = [_make_step("s1"), _make_step("s2", deps=["s1"])]
        result = await executor.execute_coordinated_workflow(
            workflow_id="wf-test",
            steps=steps,
            context={},
            mode=ExecutionMode.DRY_RUN,
        )
        assert result["status"] == "dry_run_complete"
        assert "dry_run_report" in result
        report: DryRunReport = result["dry_run_report"]
        assert report.valid is True
        assert len(report.execution_plan) == 2

    @pytest.mark.asyncio
    async def test_dry_run_with_broken_ref_returns_issues(self):
        executor = _make_executor()
        steps = [_make_step("s1", deps=["ghost"])]
        result = await executor.execute_coordinated_workflow(
            workflow_id="wf-broken",
            steps=steps,
            context={},
            mode=ExecutionMode.DRY_RUN,
        )
        report: DryRunReport = result["dry_run_report"]
        assert report.valid is False
        assert any("ghost" in issue for issue in report.issues)

    @pytest.mark.asyncio
    async def test_dry_run_uses_provided_validator(self):
        executor = _make_executor()
        steps = [_make_step("s1", agent="special-agent")]
        validator = DryRunValidator(registered_agent_ids=["other-agent"])
        result = await executor.execute_coordinated_workflow(
            workflow_id="wf-val",
            steps=steps,
            context={},
            mode=ExecutionMode.DRY_RUN,
            dry_run_validator=validator,
        )
        report: DryRunReport = result["dry_run_report"]
        assert any("special-agent" in w for w in report.warnings)

    @pytest.mark.asyncio
    async def test_dry_run_no_agent_calls(self):
        """DRY_RUN must never touch _simulate_step_execution."""
        executor = _make_executor()
        steps = [_make_step("s1")]
        with patch.object(executor, "_simulate_step_execution", new_callable=AsyncMock) as mock_sim:
            await executor.execute_coordinated_workflow(
                workflow_id="wf-no-exec",
                steps=steps,
                context={},
                mode=ExecutionMode.DRY_RUN,
            )
            mock_sim.assert_not_called()


# ---------------------------------------------------------------------------
# WorkflowExecutor integration — DEBUG mode
# ---------------------------------------------------------------------------


class TestWorkflowExecutorDebug:
    @pytest.mark.asyncio
    async def test_debug_mode_requires_controller(self):
        executor = _make_executor()
        with pytest.raises(ValueError, match="debug_controller"):
            await executor.execute_coordinated_workflow(
                workflow_id="wf",
                steps=[_make_step("s1")],
                context={},
                mode=ExecutionMode.DEBUG,
                debug_session_id="some-id",
                # debug_controller intentionally omitted
            )

    @pytest.mark.asyncio
    async def test_debug_mode_requires_session_id(self):
        executor = _make_executor()
        ctrl = DebugController()
        with pytest.raises(ValueError, match="debug_session_id"):
            await executor.execute_coordinated_workflow(
                workflow_id="wf",
                steps=[_make_step("s1")],
                context={},
                mode=ExecutionMode.DEBUG,
                debug_controller=ctrl,
                # debug_session_id intentionally omitted
            )

    @pytest.mark.asyncio
    async def test_debug_pauses_after_each_group(self):
        """
        Verify that _debug_pause_after_group is called once per step group
        when mode=DEBUG.  We patch out _execute_step_group to inject a
        synthetic step_result so we can drive the flow without real agent
        execution.
        """
        executor = _make_executor()
        ctrl = DebugController()
        sid = ctrl.start_debug_session("exec-debug")
        steps = [_make_step("a"), _make_step("b", deps=["a"])]

        # _execute_step_group is called per group; we inject results for pause logic.
        async def _fake_group(group, exec_ctx, ctx):
            for step in group:
                step_id = step["id"]
                exec_ctx["step_results"][step_id] = {"success": True}
                step["status"] = "completed"

        pause_calls: List[str] = []

        async def _fake_pause(group, exec_ctx, dbg_ctrl, dbg_sid):
            for step in group:
                pause_calls.append(step["id"])

        with (
            patch.object(executor, "_execute_step_group", side_effect=_fake_group),
            patch.object(executor, "_debug_pause_after_group", side_effect=_fake_pause),
        ):
            await executor.execute_coordinated_workflow(
                workflow_id="wf-debug",
                steps=steps,
                context={},
                mode=ExecutionMode.DEBUG,
                debug_controller=ctrl,
                debug_session_id=sid,
            )

        # Both steps should have triggered a pause call (one per group)
        assert "a" in pause_calls
        assert "b" in pause_calls


# ---------------------------------------------------------------------------
# WorkflowExecutor integration — NORMAL mode unchanged
# ---------------------------------------------------------------------------


class TestWorkflowExecutorNormalUnchanged:
    @pytest.mark.asyncio
    async def test_normal_mode_no_dry_run_report(self):
        """NORMAL mode must not inject a dry_run_report key."""
        executor = _make_executor()
        steps = [_make_step("s1")]

        # _execute_step_group raises NotImplementedError (via _simulate_step_execution)
        # in the current codebase; we patch it to avoid that.
        async def _noop_group(group, exec_ctx, ctx):
            for step in group:
                sid = step["id"]
                exec_ctx["step_results"][sid] = {"success": True}
                step["status"] = "completed"

        with patch.object(executor, "_execute_step_group", side_effect=_noop_group):
            result = await executor.execute_coordinated_workflow(
                workflow_id="wf-normal",
                steps=steps,
                context={},
                mode=ExecutionMode.NORMAL,
            )

        assert "dry_run_report" not in result
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_default_mode_is_normal(self):
        """Calling without mode= must behave as NORMAL."""
        executor = _make_executor()
        steps = [_make_step("s1")]

        async def _noop_group(group, exec_ctx, ctx):
            for step in group:
                exec_ctx["step_results"][step["id"]] = {"success": True}
                step["status"] = "completed"

        with patch.object(executor, "_execute_step_group", side_effect=_noop_group):
            result = await executor.execute_coordinated_workflow(
                workflow_id="wf-default",
                steps=steps,
                context={},
            )

        assert result["status"] == "completed"
        assert "dry_run_report" not in result
