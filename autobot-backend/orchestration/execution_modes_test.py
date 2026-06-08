# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for execution_modes.py

Issue #2148: Dry-run validation and step-by-step debug mode.

Covers:
- ExecutionMode enum values and str identity
- DryRunValidator: valid workflow, broken deps, cycles, bad var refs, unassigned agents
- DryRunReport.to_dict() serialisation
- DebugController: resume, skip, stop signals
- WorkflowExecutor.execute_coordinated_workflow integration for DRY_RUN and DEBUG modes
"""

import asyncio
import logging

import pytest

from autobot_shared.logging_manager import get_logger

from .execution_modes import (
    DebugController,
    DryRunReport,
    DryRunValidator,
    ExecutionMode,
    StepPlan,
)
from .workflow_executor import WorkflowExecutor

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOOP_CALLBACKS = dict(
    agent_registry={},
    agent_interactions=[],
    reserve_agent_callback=lambda _: None,
    release_agent_callback=lambda _: None,
    update_performance_callback=lambda _id, _ok, _t: None,
)


def _make_executor() -> WorkflowExecutor:
    return WorkflowExecutor(**_NOOP_CALLBACKS)


def _make_steps(n: int = 2) -> list:
    """Build a minimal list of *n* linear steps."""
    return [
        {
            "id": f"step_{i}",
            "action": f"action_{i}",
            "assigned_agent": f"agent_{i}",
            "inputs": {},
            "dependencies": [] if i == 0 else [f"step_{i - 1}"],
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# ExecutionMode
# ---------------------------------------------------------------------------


class TestExecutionMode:
    def test_string_values(self) -> None:
        assert ExecutionMode.NORMAL == "normal"
        assert ExecutionMode.DRY_RUN == "dry_run"
        assert ExecutionMode.DEBUG == "debug"

    def test_enum_identity(self) -> None:
        assert ExecutionMode("normal") is ExecutionMode.NORMAL
        assert ExecutionMode("dry_run") is ExecutionMode.DRY_RUN
        assert ExecutionMode("debug") is ExecutionMode.DEBUG


# ---------------------------------------------------------------------------
# DryRunValidator
# ---------------------------------------------------------------------------


class TestDryRunValidator:
    def setup_method(self) -> None:
        self.validator = DryRunValidator()

    def test_valid_workflow_no_issues(self) -> None:
        steps = _make_steps(3)
        report = self.validator.validate("wf_valid", steps)

        assert report.valid is True
        assert report.issues == []
        assert len(report.execution_plan) == 3

    def test_broken_dependency_is_an_issue(self) -> None:
        steps = [
            {
                "id": "a",
                "action": "do_a",
                "assigned_agent": "ag1",
                "inputs": {},
                "dependencies": [],
            },
            {
                "id": "b",
                "action": "do_b",
                "assigned_agent": "ag2",
                "inputs": {},
                "dependencies": ["nonexistent"],
            },
        ]
        report = self.validator.validate("wf_broken_dep", steps)

        assert report.valid is False
        assert any("nonexistent" in issue for issue in report.issues)

    def test_cycle_detection_is_an_issue(self) -> None:
        steps = [
            {
                "id": "a",
                "type": "step",
                "action": "a",
                "assigned_agent": "ag",
                "inputs": {},
                "dependencies": [],
            },
            {
                "id": "b",
                "type": "step",
                "action": "b",
                "assigned_agent": "ag",
                "inputs": {},
                "dependencies": [],
            },
        ]
        edges = [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},  # cycle
        ]
        report = self.validator.validate("wf_cycle", steps, edges)

        assert report.valid is False
        assert any("cycle" in issue.lower() for issue in report.issues)

    def test_unknown_variable_ref_is_a_warning(self) -> None:
        steps = [
            {
                "id": "step_1",
                "action": "use_output",
                "assigned_agent": "ag",
                "inputs": {},
                "command": "${steps.ghost_step.output}",
                "dependencies": [],
            }
        ]
        report = self.validator.validate("wf_var_ref", steps)

        # ghost_step is not in the step list — should warn but not block
        assert report.valid is True
        assert any("ghost_step" in w for w in report.warnings)

    def test_unassigned_agent_is_a_warning(self) -> None:
        steps = [{"id": "orphan", "action": "do_thing", "inputs": {}, "dependencies": []}]
        report = self.validator.validate("wf_no_agent", steps)

        assert report.valid is True
        assert any("orphan" in w for w in report.warnings)

    def test_execution_plan_order_matches_steps(self) -> None:
        steps = _make_steps(4)
        report = self.validator.validate("wf_plan", steps)

        plan_ids = [p.step_id for p in report.execution_plan]
        step_ids = [s["id"] for s in steps]
        assert plan_ids == step_ids

    def test_step_plan_variable_refs_extracted(self) -> None:
        steps = [
            {
                "id": "consumer",
                "action": "consume",
                "assigned_agent": "ag",
                "inputs": {"val": "${steps.producer.output.result}"},
                "dependencies": [],
            }
        ]
        report = self.validator.validate("wf_var_plan", steps)
        plan = report.execution_plan[0]

        assert len(plan.variable_refs) == 1
        assert "producer" in plan.variable_refs[0]


# ---------------------------------------------------------------------------
# DryRunReport.to_dict
# ---------------------------------------------------------------------------


class TestDryRunReport:
    def test_to_dict_shape(self) -> None:
        plan = [StepPlan("s1", "act", "ag", [], [])]
        report = DryRunReport(valid=True, execution_plan=plan, issues=[], warnings=["w1"])

        d = report.to_dict()
        assert d["valid"] is True
        assert d["issues"] == []
        assert d["warnings"] == ["w1"]
        assert len(d["execution_plan"]) == 1
        assert d["execution_plan"][0]["step_id"] == "s1"

    def test_to_dict_invalid_report(self) -> None:
        report = DryRunReport(valid=False, issues=["bad dep"], warnings=[])
        d = report.to_dict()

        assert d["valid"] is False
        assert "bad dep" in d["issues"]


# ---------------------------------------------------------------------------
# DebugController
# ---------------------------------------------------------------------------


class TestDebugController:
    @pytest.mark.asyncio
    async def test_resume_signal(self) -> None:
        ctrl = DebugController()
        asyncio.get_running_loop().call_soon(lambda: asyncio.ensure_future(ctrl.resume()))
        signal = await ctrl.wait_for_resume("step_1")
        assert signal == DebugController.Signal.RESUME

    @pytest.mark.asyncio
    async def test_skip_signal(self) -> None:
        ctrl = DebugController()
        asyncio.get_running_loop().call_soon(lambda: asyncio.ensure_future(ctrl.skip()))
        signal = await ctrl.wait_for_resume("step_1")
        assert signal == DebugController.Signal.SKIP

    @pytest.mark.asyncio
    async def test_retry_signal(self) -> None:
        ctrl = DebugController()
        asyncio.get_running_loop().call_soon(lambda: asyncio.ensure_future(ctrl.retry()))
        signal = await ctrl.wait_for_resume("step_1")
        assert signal == DebugController.Signal.RETRY

    @pytest.mark.asyncio
    async def test_stop_returns_resume_immediately(self) -> None:
        ctrl = DebugController()
        ctrl.stop()
        signal = await ctrl.wait_for_resume("step_1")
        assert signal == DebugController.Signal.RESUME

    def test_is_active_starts_true(self) -> None:
        ctrl = DebugController()
        assert ctrl.is_active is True

    def test_stop_sets_is_active_false(self) -> None:
        ctrl = DebugController()
        ctrl.stop()
        assert ctrl.is_active is False


# ---------------------------------------------------------------------------
# WorkflowExecutor integration: DRY_RUN mode
# ---------------------------------------------------------------------------


class TestWorkflowExecutorDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_report_dict(self) -> None:
        executor = _make_executor()
        steps = _make_steps(2)

        result = await executor.execute_coordinated_workflow(
            "wf_dr_1",
            steps,
            context={},
            mode=ExecutionMode.DRY_RUN,
        )

        assert result["mode"] == "dry_run"
        assert result["workflow_id"] == "wf_dr_1"
        assert "valid" in result
        assert "execution_plan" in result
        assert "issues" in result
        assert "warnings" in result

    @pytest.mark.asyncio
    async def test_dry_run_does_not_execute_steps(self) -> None:
        """Verify that DRY_RUN never calls _execute_coordinated_step."""
        executor = _make_executor()
        steps = _make_steps(3)
        executed: list = []

        original = executor._execute_coordinated_step

        async def _spy(step, exec_ctx, ctx):
            executed.append(step["id"])
            return await original(step, exec_ctx, ctx)

        executor._execute_coordinated_step = _spy  # type: ignore[method-assign]

        await executor.execute_coordinated_workflow(
            "wf_dr_spy",
            steps,
            context={},
            mode=ExecutionMode.DRY_RUN,
        )

        assert executed == [], "DRY_RUN must not execute any step"

    @pytest.mark.asyncio
    async def test_dry_run_detects_broken_dependency(self) -> None:
        executor = _make_executor()
        steps = [
            {
                "id": "x",
                "action": "a",
                "assigned_agent": "ag",
                "inputs": {},
                "dependencies": ["missing"],
            },
        ]

        result = await executor.execute_coordinated_workflow(
            "wf_dr_broken",
            steps,
            context={},
            mode=ExecutionMode.DRY_RUN,
        )

        assert result["valid"] is False
        assert any("missing" in i for i in result["issues"])


# ---------------------------------------------------------------------------
# WorkflowExecutor integration: DEBUG mode
# ---------------------------------------------------------------------------


class TestWorkflowExecutorDebugMode:
    @pytest.mark.asyncio
    async def test_debug_mode_skip_marks_step_skipped(self) -> None:
        """When the controller sends SKIP, the step dict should have status=skipped."""
        executor = _make_executor()
        steps = _make_steps(1)
        ctrl = DebugController()

        # Schedule an immediate skip signal so wait_for_resume unblocks right away.
        task = asyncio.ensure_future(
            executor.execute_coordinated_workflow(
                "wf_dbg_skip",
                steps,
                context={},
                mode=ExecutionMode.DEBUG,
                debug_controller=ctrl,
            )
        )
        # Let the executor reach wait_for_resume, then fire skip
        await asyncio.sleep(0)
        await ctrl.skip()
        result = await task

        # Step was skipped, so it should appear in step_results
        step_id = steps[0]["id"]
        assert result["step_results"][step_id]["skipped"] is True

    @pytest.mark.asyncio
    async def test_debug_mode_without_controller_falls_back_to_normal(self, caplog) -> None:
        """DEBUG without a controller logs a warning and falls back to NORMAL execution."""
        executor = _make_executor()
        steps = _make_steps(1)

        with caplog.at_level(logging.WARNING, logger="autobot-backend.orchestration.workflow_executor"):
            await executor.execute_coordinated_workflow(
                "wf_dbg_no_ctrl",
                steps,
                context={},
                mode=ExecutionMode.DEBUG,
                debug_controller=None,
            )

        assert any("debug_controller" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_normal_mode_unchanged(self) -> None:
        """NORMAL mode must still reach the step executor and produce an execution_context."""
        executor = _make_executor()
        steps = _make_steps(1)

        result = await executor.execute_coordinated_workflow(
            "wf_normal",
            steps,
            context={},
            mode=ExecutionMode.NORMAL,
        )

        # NORMAL mode should have the standard execution_context keys
        assert "workflow_id" in result
        assert "step_results" in result
        assert "status" in result

    @pytest.mark.asyncio
    async def test_notification_config_injected_into_execution_context(self) -> None:
        """Issue #3172: notification_config passed to execute_coordinated_workflow
        must appear in the returned execution_context so _resolve_notification_config
        can locate it and fire notifications.
        """
        executor = _make_executor()
        steps = _make_steps(1)
        cfg = {"workflow_id": "wf_nc", "channels": {}}

        result = await executor.execute_coordinated_workflow(
            "wf_nc",
            steps,
            context={},
            notification_config=cfg,
        )

        assert result.get("notification_config") is cfg

    @pytest.mark.asyncio
    async def test_notification_config_defaults_to_none(self) -> None:
        """Issue #3172: when notification_config is not supplied the key is
        present in execution_context with value None so the resolver can safely
        call .get() without a KeyError.
        """
        executor = _make_executor()
        steps = _make_steps(1)

        result = await executor.execute_coordinated_workflow(
            "wf_no_nc",
            steps,
            context={},
        )

        assert "notification_config" in result
        assert result["notification_config"] is None

    @pytest.mark.asyncio
    async def test_dag_path_fires_send_workflow_notification(self) -> None:
        """Issue #3172: DAG execution path must call _send_workflow_notification.

        Before the fix, execute_coordinated_workflow returned early from
        _execute_dag_workflow without reaching the notification calls in the
        linear path, so notifications were silently dropped for any workflow
        that used condition nodes.
        """
        import unittest.mock

        executor = _make_executor()
        # A condition-type node + edges triggers workflow_has_condition_nodes → DAG path.
        steps = [
            {
                "id": "cond",
                "type": "condition",
                "action": "check",
                "assigned_agent": "a0",
                "inputs": {},
                "dependencies": [],
            },
            {
                "id": "step_a",
                "type": "step",
                "action": "act",
                "assigned_agent": "a1",
                "inputs": {},
                "dependencies": ["cond"],
            },
        ]
        edges = [{"from": "cond", "to": "step_a", "condition": "true"}]
        cfg = {"workflow_id": "wf_dag_notif", "channels": {}}

        mock_notify = unittest.mock.AsyncMock()
        with unittest.mock.patch.object(executor, "_send_workflow_notification", mock_notify):
            await executor.execute_coordinated_workflow(
                "wf_dag_notif",
                steps,
                context={},
                edges=edges,
                notification_config=cfg,
            )

        mock_notify.assert_called_once()
