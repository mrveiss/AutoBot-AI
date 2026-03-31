# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Execution Modes: Dry-Run and Step-by-Step Debug

Issue #2148: Workflow dry-run and step-by-step debug mode.

Provides three orthogonal execution modes that compose with WorkflowExecutor:

- NORMAL   — standard execution (no change to existing behaviour)
- DRY_RUN  — validate structure + produce a predicted execution plan; no
              real agent calls are made
- DEBUG    — execute normally but pause after each step and wait for a
              client signal (continue / skip / retry) before proceeding

Key classes
-----------
ExecutionMode
    Enum of NORMAL / DRY_RUN / DEBUG.

DryRunReport
    Immutable result of a dry-run validation pass.

DryRunValidator
    Stateless validator; call ``validate_workflow()`` to receive a
    DryRunReport without touching any agent or external resource.

DebugController
    Per-execution-session state machine for the DEBUG mode.  Each running
    workflow gets its own controller instance.  Thread-safe via
    ``asyncio.Event``.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ExecutionMode
# ---------------------------------------------------------------------------


class ExecutionMode(str, Enum):
    """Execution mode selector passed to WorkflowExecutor."""

    NORMAL = "normal"
    DRY_RUN = "dry_run"
    DEBUG = "debug"


# ---------------------------------------------------------------------------
# DryRunReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepPlan:
    """Predicted execution plan entry for a single workflow step."""

    step_id: str
    action: str
    assigned_agent: Optional[str]
    estimated_duration: float
    dependencies: List[str]
    parallel_group: int


@dataclass(frozen=True)
class DryRunReport:
    """
    Immutable result of a dry-run validation pass.

    Attributes
    ----------
    valid:
        True when the workflow passed all structural checks and can in
        principle be executed (warnings do not invalidate).
    execution_plan:
        Ordered list of StepPlan entries describing the predicted run order,
        parallel groups, and per-step metadata.
    issues:
        Fatal structural problems (broken references, cycles, missing
        required fields).  Any entry here sets ``valid=False``.
    warnings:
        Non-fatal observations (unreachable steps, missing optional fields,
        agents not registered).
    """

    valid: bool
    execution_plan: List[StepPlan]
    issues: List[str]
    warnings: List[str]


# ---------------------------------------------------------------------------
# DryRunValidator
# ---------------------------------------------------------------------------


class DryRunValidator:
    """
    Stateless workflow validator for dry-run mode.

    Call ``validate_workflow()`` with the same ``steps`` + ``edges``
    payload that would be passed to ``WorkflowExecutor.execute_coordinated_workflow()``.
    No agent calls or external I/O are performed.

    Issue #2148.
    """

    # Required fields that every step must carry
    _REQUIRED_STEP_FIELDS: List[str] = ["id", "action"]

    def __init__(self, registered_agent_ids: Optional[List[str]] = None) -> None:
        """
        Args:
            registered_agent_ids: Optional list of known agent IDs.  When
                provided, steps whose ``assigned_agent`` is absent from this
                list generate a warning.
        """
        self._registered_agents: List[str] = registered_agent_ids or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_workflow(
        self,
        steps: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]] = None,
    ) -> DryRunReport:
        """
        Validate *steps* + *edges* and return a DryRunReport.

        Args:
            steps: List of workflow step dicts (same format as
                WorkflowExecutor accepts).
            edges: Optional list of DAG edge dicts.

        Returns:
            DryRunReport with ``valid``, ``execution_plan``, ``issues``,
            ``warnings``.
        """
        effective_edges: List[Dict[str, Any]] = edges or []
        issues: List[str] = []
        warnings: List[str] = []

        self._check_required_fields(steps, issues)
        self._check_duplicate_ids(steps, issues)
        self._check_dependency_references(steps, issues)
        self._check_edge_references(steps, effective_edges, issues)
        self._check_cycle(steps, effective_edges, issues)
        self._check_agent_registration(steps, warnings)
        self._check_reachability(steps, effective_edges, warnings)

        execution_plan = self._build_execution_plan(steps) if not issues else []
        valid = len(issues) == 0

        logger.info(
            "Dry-run validation: valid=%s, %d issue(s), %d warning(s)",
            valid,
            len(issues),
            len(warnings),
        )
        return DryRunReport(
            valid=valid,
            execution_plan=execution_plan,
            issues=issues,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Structural checks — populate issues (fatal)
    # ------------------------------------------------------------------

    def _check_required_fields(
        self,
        steps: List[Dict[str, Any]],
        issues: List[str],
    ) -> None:
        """Verify every step carries the minimum required fields."""
        for idx, step in enumerate(steps):
            for field_name in self._REQUIRED_STEP_FIELDS:
                if not step.get(field_name):
                    issues.append(
                        f"Step[{idx}]: missing required field '{field_name}'"
                    )

    def _check_duplicate_ids(
        self,
        steps: List[Dict[str, Any]],
        issues: List[str],
    ) -> None:
        """Detect duplicate step IDs."""
        seen: Dict[str, int] = {}
        for step in steps:
            sid = step.get("id")
            if sid is None:
                continue
            if sid in seen:
                issues.append(f"Duplicate step id '{sid}'")
            seen[sid] = 1

    def _check_dependency_references(
        self,
        steps: List[Dict[str, Any]],
        issues: List[str],
    ) -> None:
        """Verify all ``dependencies`` entries reference existing step IDs."""
        known_ids = {s.get("id") for s in steps if s.get("id")}
        for step in steps:
            for dep in step.get("dependencies", []):
                if dep not in known_ids:
                    issues.append(
                        f"Step '{step.get('id')}': dependency '{dep}' does not exist"
                    )

    def _check_edge_references(
        self,
        steps: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        issues: List[str],
    ) -> None:
        """Verify all edge source/target IDs reference existing steps."""
        known_ids = {s.get("id") for s in steps if s.get("id")}
        for edge in edges:
            src, tgt = edge.get("source"), edge.get("target")
            if src and src not in known_ids:
                issues.append(f"Edge source '{src}' does not reference a known step")
            if tgt and tgt not in known_ids:
                issues.append(f"Edge target '{tgt}' does not reference a known step")

    def _check_cycle(
        self,
        steps: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        issues: List[str],
    ) -> None:
        """Detect cycles via depth-first search on the dependency graph."""
        # Build adjacency from both dependency lists and explicit edges
        adj: Dict[str, List[str]] = {s["id"]: [] for s in steps if s.get("id")}

        for step in steps:
            sid = step.get("id")
            if not sid:
                continue
            for dep in step.get("dependencies", []):
                if dep in adj:
                    adj[dep].append(sid)  # dep must complete before sid → dep → sid

        for edge in edges:
            src, tgt = edge.get("source"), edge.get("target")
            if src in adj and tgt in adj:
                adj[src].append(tgt)

        visited: set = set()
        in_stack: set = set()

        def _dfs(node: str) -> Optional[str]:
            visited.add(node)
            in_stack.add(node)
            for neighbour in adj.get(node, []):
                if neighbour not in visited:
                    cycle_node = _dfs(neighbour)
                    if cycle_node:
                        return cycle_node
                elif neighbour in in_stack:
                    return neighbour
            in_stack.discard(node)
            return None

        for node in list(adj):
            if node not in visited:
                cycle_node = _dfs(node)
                if cycle_node:
                    issues.append(
                        f"Cycle detected involving step '{cycle_node}'"
                    )
                    break  # Report first cycle only

    # ------------------------------------------------------------------
    # Structural checks — populate warnings (non-fatal)
    # ------------------------------------------------------------------

    def _check_agent_registration(
        self,
        steps: List[Dict[str, Any]],
        warnings: List[str],
    ) -> None:
        """Warn when a step's assigned_agent is not in the known registry."""
        if not self._registered_agents:
            return
        for step in steps:
            agent_id = step.get("assigned_agent")
            if agent_id and agent_id not in self._registered_agents:
                warnings.append(
                    f"Step '{step.get('id')}': agent '{agent_id}' is not registered"
                )

    def _check_reachability(
        self,
        steps: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        warnings: List[str],
    ) -> None:
        """Warn about steps that are disconnected from all roots (unreachable)."""
        if not edges:
            return  # Linear workflow — all steps implicitly reachable

        known_ids = {s.get("id") for s in steps if s.get("id")}
        has_incoming: set = {e["target"] for e in edges if e.get("target") in known_ids}
        roots = known_ids - has_incoming

        reachable: set = set()
        queue = list(roots)
        outgoing: Dict[str, List[str]] = {sid: [] for sid in known_ids}
        for edge in edges:
            src, tgt = edge.get("source"), edge.get("target")
            if src in outgoing:
                outgoing[src].append(tgt)

        while queue:
            nid = queue.pop()
            if nid in reachable:
                continue
            reachable.add(nid)
            queue.extend(outgoing.get(nid, []))

        unreachable = known_ids - reachable
        for nid in sorted(unreachable):
            warnings.append(f"Step '{nid}' is unreachable from any root node")

    # ------------------------------------------------------------------
    # Execution plan builder
    # ------------------------------------------------------------------

    def _build_execution_plan(self, steps: List[Dict[str, Any]]) -> List[StepPlan]:
        """
        Build an ordered execution plan mirroring WorkflowExecutor's
        ``_group_steps_by_dependency`` logic.

        Returns a list of StepPlan entries annotated with their parallel group
        index so callers can see which steps would run concurrently.
        """
        step_map = {s["id"]: s for s in steps if s.get("id")}
        remaining = list(step_map)
        completed: set = set()
        plan: List[StepPlan] = []
        group_index = 0

        while remaining:
            ready_ids = [
                sid
                for sid in remaining
                if all(dep in completed for dep in step_map[sid].get("dependencies", []))
            ]
            if not ready_ids:
                # Circular dependency already caught by _check_cycle; just bail
                logger.warning("Aborting execution plan build: unresolvable dependencies")
                break

            for sid in ready_ids:
                step = step_map[sid]
                plan.append(
                    StepPlan(
                        step_id=sid,
                        action=step.get("action", ""),
                        assigned_agent=step.get("assigned_agent"),
                        estimated_duration=float(step.get("estimated_duration", 0.0)),
                        dependencies=list(step.get("dependencies", [])),
                        parallel_group=group_index,
                    )
                )
                remaining.remove(sid)
            completed.update(ready_ids)
            group_index += 1

        return plan


# ---------------------------------------------------------------------------
# DebugController
# ---------------------------------------------------------------------------


class DebugSessionState(str, Enum):
    """Lifecycle states of a debug session."""

    WAITING = "waiting"   # Paused — waiting for client action
    RUNNING = "running"   # Step is executing
    DONE = "done"         # Session completed or aborted


@dataclass
class DebugStepResult:
    """
    Result record stored after each step completes in DEBUG mode.

    Issue #2148.
    """

    step_id: str
    status: str            # "completed" | "failed" | "skipped"
    result: Optional[Dict[str, Any]]
    error: Optional[str]


@dataclass
class DebugSession:
    """
    Mutable state for one DEBUG-mode workflow execution.

    Do not create directly — use ``DebugController.start_debug_session()``.
    """

    session_id: str
    execution_id: str
    state: DebugSessionState = DebugSessionState.WAITING
    current_step_id: Optional[str] = None
    step_history: List[DebugStepResult] = field(default_factory=list)
    # Modified params supplied by a retry_step() call; consumed once.
    pending_retry_params: Optional[Dict[str, Any]] = None
    # Signals
    _resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    _skip_flag: bool = False
    _retry_flag: bool = False


class DebugController:
    """
    Per-execution debug session manager.

    Maintains a registry of active DebugSession objects keyed by session ID.
    The workflow executor calls ``pause_after_step()`` after each step; it
    blocks until the client calls ``continue_session()``, ``skip_step()``, or
    ``retry_step()``.

    All public methods are coroutine-safe.  A single DebugController instance
    can manage multiple concurrent debug sessions (one per workflow run).

    Issue #2148.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, DebugSession] = {}

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_debug_session(self, execution_id: str) -> str:
        """
        Create and register a new debug session for *execution_id*.

        Args:
            execution_id: Workflow execution identifier (for correlation).

        Returns:
            Unique session_id string.
        """
        session_id = str(uuid.uuid4())
        session = DebugSession(
            session_id=session_id,
            execution_id=execution_id,
            state=DebugSessionState.RUNNING,
        )
        self._sessions[session_id] = session
        logger.info(
            "Debug session %s started for execution %s", session_id, execution_id
        )
        return session_id

    def get_session(self, session_id: str) -> Optional[DebugSession]:
        """Return the DebugSession for *session_id*, or None if not found."""
        return self._sessions.get(session_id)

    def end_session(self, session_id: str) -> None:
        """Mark session as DONE and remove it from the registry."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.state = DebugSessionState.DONE
            logger.info("Debug session %s ended", session_id)

    # ------------------------------------------------------------------
    # Execution-thread API (called by the workflow executor coroutine)
    # ------------------------------------------------------------------

    async def pause_after_step(
        self,
        session_id: str,
        step_result: DebugStepResult,
    ) -> str:
        """
        Record *step_result* and pause until a client action arrives.

        Called by the workflow executor after every step in DEBUG mode.
        Blocks until ``continue_session()``, ``skip_step()``, or
        ``retry_step()`` is called from another coroutine (e.g. a WebSocket
        handler).

        Args:
            session_id: Active debug session identifier.
            step_result: Result of the step that just completed.

        Returns:
            Action string: ``"continue"`` | ``"skip"`` | ``"retry"``.

        Raises:
            KeyError: If *session_id* is not registered.
        """
        session = self._sessions[session_id]
        session.step_history.append(step_result)
        session.current_step_id = step_result.step_id
        session.state = DebugSessionState.WAITING
        session._resume_event.clear()
        session._skip_flag = False
        session._retry_flag = False

        logger.debug(
            "Debug session %s: paused after step %s — waiting for client",
            session_id,
            step_result.step_id,
        )

        await session._resume_event.wait()
        session.state = DebugSessionState.RUNNING

        if session._retry_flag:
            return "retry"
        if session._skip_flag:
            return "skip"
        return "continue"

    # ------------------------------------------------------------------
    # Client-thread API (called by WebSocket / REST handler)
    # ------------------------------------------------------------------

    def continue_session(self, session_id: str) -> None:
        """
        Signal the paused workflow to proceed to the next step.

        Args:
            session_id: Active debug session identifier.

        Raises:
            KeyError: If *session_id* is not registered.
            RuntimeError: If the session is not in WAITING state.
        """
        session = self._get_waiting_session(session_id)
        logger.info("Debug session %s: continue signal received", session_id)
        session._resume_event.set()

    def skip_step(self, session_id: str) -> None:
        """
        Signal the paused workflow to skip the current step's successor.

        The executor will mark the *next* step as skipped and move on.

        Args:
            session_id: Active debug session identifier.

        Raises:
            KeyError: If *session_id* is not registered.
            RuntimeError: If the session is not in WAITING state.
        """
        session = self._get_waiting_session(session_id)
        session._skip_flag = True
        logger.info("Debug session %s: skip signal received", session_id)
        session._resume_event.set()

    def retry_step(
        self, session_id: str, modified_params: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Signal the paused workflow to re-execute the current step.

        Args:
            session_id: Active debug session identifier.
            modified_params: Optional dict of parameters to override on the
                step before re-execution.  Stored in
                ``session.pending_retry_params`` for the executor to consume.

        Raises:
            KeyError: If *session_id* is not registered.
            RuntimeError: If the session is not in WAITING state.
        """
        session = self._get_waiting_session(session_id)
        session._retry_flag = True
        session.pending_retry_params = modified_params or {}
        logger.info(
            "Debug session %s: retry signal received (params=%s)",
            session_id,
            modified_params,
        )
        session._resume_event.set()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_waiting_session(self, session_id: str) -> DebugSession:
        """Return a session that is in WAITING state, or raise."""
        session = self._sessions[session_id]  # KeyError propagates intentionally
        if session.state != DebugSessionState.WAITING:
            raise RuntimeError(
                f"Debug session {session_id} is in state '{session.state}', "
                "expected WAITING"
            )
        return session
