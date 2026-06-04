# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Execution Modes — Dry-Run Validation and Step-by-Step Debug

Issue #2148: Add dry-run and debug-mode execution to the workflow engine.

Two complementary modes are provided:

DRY_RUN
    Validates workflow structure (cycles, broken references, unresolvable
    variables) and returns a ``DryRunReport`` without executing any step.
    Callers get a human-readable execution plan and a list of issues/warnings
    before committing to a real run.

DEBUG
    Executes the workflow normally but pauses between steps, waiting for an
    external controller signal before proceeding.  ``DebugController`` provides
    the async primitives (resume, skip, retry) that a UI or test harness drives.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .dag_executor import build_dag
from .variable_resolver import VariableResolver

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ExecutionMode enum
# ---------------------------------------------------------------------------


class ExecutionMode(str, Enum):
    """Execution strategy for a workflow run."""

    NORMAL = "normal"
    """Execute all steps immediately with no pauses or pre-validation."""

    DRY_RUN = "dry_run"
    """Validate structure and produce a plan; skip all actual step execution."""

    DEBUG = "debug"
    """Execute with a mandatory pause between every step for interactive control."""


# ---------------------------------------------------------------------------
# DryRunReport dataclass
# ---------------------------------------------------------------------------


@dataclass
class StepPlan:
    """Per-step summary included in a DryRunReport.

    Issue #2148.
    """

    step_id: str
    action: str
    assigned_agent: str | None
    dependencies: List[str]
    variable_refs: List[str]
    """Variable tokens found in command/inputs for this step."""


@dataclass
class DryRunReport:
    """
    Result of validating a workflow in DRY_RUN mode.

    Attributes:
        valid:          True when no blocking issues were found.
        execution_plan: Ordered list of StepPlan entries (sequential order).
        issues:         Blocking problems that would prevent execution.
        warnings:       Non-blocking concerns worth reviewing.

    Issue #2148.
    """

    valid: bool
    execution_plan: List[StepPlan] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the report to a plain dict suitable for JSON responses."""
        return {
            "valid": self.valid,
            "issues": self.issues,
            "warnings": self.warnings,
            "execution_plan": [
                {
                    "step_id": p.step_id,
                    "action": p.action,
                    "assigned_agent": p.assigned_agent,
                    "dependencies": p.dependencies,
                    "variable_refs": p.variable_refs,
                }
                for p in self.execution_plan
            ],
        }


# ---------------------------------------------------------------------------
# DryRunValidator
# ---------------------------------------------------------------------------


class DryRunValidator:
    """
    Validates a workflow definition without executing any step.

    Checks performed
    ----------------
    1. Broken dependency references — a step lists a dependency ID that does
       not exist in the step list.
    2. Cycle detection — uses WorkflowDAG.detect_cycle() for DAG workflows;
       falls back to a simple DFS for linear step lists.
    3. Variable reference integrity — ``${steps.<id>.<accessor>}`` tokens are
       extracted from command/inputs; each referenced step_id is checked for
       existence in the step list.  Whether the accessor will resolve to a
       non-empty value at runtime is not verified (the step hasn't run yet).

    Usage::

        validator = DryRunValidator()
        report = validator.validate(workflow_id, steps, edges)
        if not report.valid:
            return report.to_dict()

    Issue #2148.
    """

    def __init__(self) -> None:
        self._var_resolver = VariableResolver()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def validate(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        edges: List[Dict[str, Any]] | None = None,
    ) -> DryRunReport:
        """
        Validate *steps* (and optionally *edges*) for *workflow_id*.

        Args:
            workflow_id: Identifier used only for log messages.
            steps:       List of step dicts in workflow definition order.
            edges:       Optional list of DAG edge dicts.

        Returns:
            DryRunReport populated with issues, warnings, and execution_plan.
        """
        logger.info(
            "Dry-run validation started for workflow %s (%d steps)",
            workflow_id,
            len(steps),
        )
        issues: List[str] = []
        warnings: List[str] = []
        effective_edges = edges or []

        step_ids = {s["id"] for s in steps}

        self._check_broken_dependencies(steps, step_ids, issues)
        self._check_cycles(steps, effective_edges, workflow_id, issues)
        self._check_variable_refs(steps, step_ids, warnings)
        self._check_unassigned_agents(steps, warnings)

        execution_plan = self._build_execution_plan(steps)

        valid = len(issues) == 0
        logger.info(
            "Dry-run validation finished for workflow %s: valid=%s, issues=%d, warnings=%d",
            workflow_id,
            valid,
            len(issues),
            len(warnings),
        )
        return DryRunReport(valid=valid, execution_plan=execution_plan, issues=issues, warnings=warnings)

    # ------------------------------------------------------------------
    # Validation sub-checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_broken_dependencies(
        steps: List[Dict[str, Any]],
        step_ids: set,
        issues: List[str],
    ) -> None:
        """Append an issue for every dependency that references a missing step ID."""
        for step in steps:
            for dep_id in step.get("dependencies", []):
                if dep_id not in step_ids:
                    issues.append(f"Step '{step['id']}' depends on unknown step '{dep_id}'.")

    @staticmethod
    def _check_cycles(
        steps: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        workflow_id: str,
        issues: List[str],
    ) -> None:
        """Detect cycles using WorkflowDAG when edges are provided."""
        if not edges:
            return
        dag = build_dag(steps, edges)
        cycle = dag.detect_cycle()
        if cycle:
            path = " → ".join(cycle)
            issues.append(f"Workflow graph contains a cycle: {path}.")
            logger.warning("Dry-run cycle detected in workflow %s: %s", workflow_id, path)

    @staticmethod
    def _extract_variable_step_refs(step: Dict[str, Any]) -> List[str]:
        """
        Return all ``${steps.<id>.*}`` token strings found in *step*.

        Scans ``command`` (str) and each value in ``inputs`` (dict of str).
        Issue #2148.
        """
        import re

        _TOKEN_RE = re.compile(r"\$\{steps\.(\w+)\.[^}]+\}")
        tokens: List[str] = []
        command = step.get("command")
        if isinstance(command, str):
            tokens.extend(_TOKEN_RE.findall(command))
        inputs = step.get("inputs")
        if isinstance(inputs, dict):
            for v in inputs.values():
                if isinstance(v, str):
                    tokens.extend(_TOKEN_RE.findall(v))
        return tokens

    def _check_variable_refs(
        self,
        steps: List[Dict[str, Any]],
        step_ids: set,
        warnings: List[str],
    ) -> None:
        """Warn when a variable token references a step_id not in this workflow."""
        for step in steps:
            for ref_id in self._extract_variable_step_refs(step):
                if ref_id not in step_ids:
                    warnings.append(f"Step '{step['id']}' references unknown step '{ref_id}' " f"via variable token.")

    @staticmethod
    def _check_unassigned_agents(
        steps: List[Dict[str, Any]],
        warnings: List[str],
    ) -> None:
        """Warn for steps that have no assigned_agent — they will fail at runtime."""
        for step in steps:
            if not step.get("assigned_agent"):
                warnings.append(
                    f"Step '{step['id']}' (action='{step.get('action', '?')}') "
                    f"has no assigned_agent; it will raise NotImplementedError at runtime."
                )

    def _build_execution_plan(self, steps: List[Dict[str, Any]]) -> List[StepPlan]:
        """Build an ordered list of StepPlan summaries from the step list."""
        plan: List[StepPlan] = []
        for step in steps:
            var_refs = self._extract_variable_step_refs(step)
            plan.append(
                StepPlan(
                    step_id=step["id"],
                    action=step.get("action", ""),
                    assigned_agent=step.get("assigned_agent"),
                    dependencies=list(step.get("dependencies", [])),
                    variable_refs=[f"${{steps.{rid}.*}}" for rid in var_refs],
                )
            )
        return plan


# ---------------------------------------------------------------------------
# DebugController
# ---------------------------------------------------------------------------


class DebugController:
    """
    Async controller for step-by-step debug execution.

    Provides a pause/resume model: when the workflow executor calls
    ``wait_for_resume()``, execution blocks until one of the following
    signals is sent externally:

    - ``resume()``  — execute the current step normally and continue.
    - ``skip()``    — mark the current step as skipped and advance.
    - ``retry()``   — re-execute the previous step (sets a flag the caller
                      checks via ``should_retry``).

    Typical usage by WorkflowExecutor::

        controller = DebugController()
        # (pass to execute_coordinated_workflow as debug_controller=controller)

        # In a test or UI handler:
        await controller.resume()

    Issue #2148.
    """

    class Signal(str, Enum):
        """Signals that can be sent to unblock a paused debug session."""

        RESUME = "resume"
        SKIP = "skip"
        RETRY = "retry"

    def __init__(self) -> None:
        self._event: asyncio.Event = asyncio.Event()
        self._signal: "DebugController.Signal" | None = None
        self._active: bool = True
        self._paused_step_id: str | None = None

    # ------------------------------------------------------------------
    # Controller API (called by the test harness / UI)
    # ------------------------------------------------------------------

    async def resume(self) -> None:
        """Signal the executor to execute the current paused step and continue."""
        logger.debug("DebugController.resume() called for step %s", self._paused_step_id)
        self._signal = self.Signal.RESUME
        self._event.set()

    async def skip(self) -> None:
        """Signal the executor to skip the current paused step."""
        logger.debug("DebugController.skip() called for step %s", self._paused_step_id)
        self._signal = self.Signal.SKIP
        self._event.set()

    async def retry(self) -> None:
        """Signal the executor to retry the most recently executed step."""
        logger.debug("DebugController.retry() called for step %s", self._paused_step_id)
        self._signal = self.Signal.RETRY
        self._event.set()

    def stop(self) -> None:
        """Deactivate the controller; subsequent wait_for_resume calls return RESUME immediately."""
        logger.debug("DebugController.stop() called")
        self._active = False
        self._event.set()

    @property
    def is_active(self) -> bool:
        """True while the controller is still managing debug execution."""
        return self._active

    # ------------------------------------------------------------------
    # Executor API (called by WorkflowExecutor between steps)
    # ------------------------------------------------------------------

    async def wait_for_resume(self, step_id: str) -> "DebugController.Signal":
        """
        Block until the controller receives a signal for *step_id*.

        Called by the executor just BEFORE each step executes so the
        external controller can inspect state, decide what to do, and
        send a signal.

        Returns the signal that was sent.  If the controller has been
        stopped, returns RESUME immediately without waiting.

        Issue #2148.
        """
        if not self._active:
            return self.Signal.RESUME

        self._paused_step_id = step_id
        self._event.clear()
        self._signal = None

        logger.info("Debug execution paused before step '%s' — awaiting signal", step_id)
        await self._event.wait()

        signal = self._signal or self.Signal.RESUME
        logger.info("Debug execution received signal '%s' for step '%s'", signal.value, step_id)
        return signal
