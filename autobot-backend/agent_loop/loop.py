# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Loop Implementation

The core agent execution loop implementing the Manus 6-step pattern:
    1. ANALYZE EVENTS    → Understand state from event stream
    2. SELECT TOOLS      → Choose based on plan + knowledge
    3. WAIT FOR EXECUTION → Sandbox executes tool
    4. ITERATE           → One tool per iteration, repeat
    5. SUBMIT RESULTS    → Deliver via message tools
    6. ENTER STANDBY     → Idle state, await new tasks

This module orchestrates the Planner, Event Stream, Parallel Executor,
and Think Tool into a cohesive execution system.
"""

import asyncio
import hashlib
import json
import time
import uuid
from typing import Any

from agent_loop.belief_state import BeliefStateUpdater
from agent_loop.pre_action_verifier import PreActionVerifier, VerifierResult, VerifierVerdict
from agent_loop.slack_hook import get_slack_hook
from agent_loop.think_tool import ThinkTool
from agent_loop.types import (
    AgentLoopConfig,
    AgentMessage,
    HumanQuestion,
    IterationResult,
    LoopOutcome,
    LoopPhase,
    LoopState,
    MessageType,
    SteeringEntry,
    TaskContext,
    ThinkCategory,
)
from autobot_shared.error_boundaries import (
    CRITICAL_ERROR_TYPES,
    FALLBACK_ERROR_TYPES,
    ErrorSeverity,
    classify_error,
)
from autobot_shared.logging_manager import get_logger
from events import EventStreamManager, EventType
from events.bus import PersistStrategy
from events.bus import publish_event as _bus_publish_event
from events.event_types import AGENT_ABSTAINED as EVT_AGENT_ABSTAINED
from events.event_types import APPROVAL_REQUIRED as EVT_APPROVAL_REQUIRED
from events.event_types import BELIEF_CACHE_HIT as EVT_BELIEF_CACHE_HIT
from events.event_types import HUMAN_ANSWER_RECEIVED as EVT_HUMAN_ANSWER_RECEIVED
from events.event_types import HUMAN_QUESTION as EVT_HUMAN_QUESTION
from events.event_types import STEERING_RECEIVED as EVT_STEERING_RECEIVED
from events.event_types import VERIFIER_VERDICT as EVT_VERIFIER_VERDICT
from events.types import (
    create_approval_required_event,
    create_human_question_event,
    create_message_event,
)
from planner import PlannerModule
from tools.parallel import ParallelToolExecutor

logger = get_logger(__name__)

# =============================================================================
# Approval Workflow – Sensitive Tool Classification (Issue #4092)
# =============================================================================

#: Tools that require explicit user approval before execution.
#: Covers file modifications, system commands, and deployment operations.
SENSITIVE_TOOLS: frozenset[str] = frozenset(
    {
        # File & filesystem mutations
        "write_file",
        "edit_file",
        "delete_file",
        "move_file",
        "copy_file",
        "create_directory",
        "remove_directory",
        # Shell / system commands
        "bash",
        "shell",
        "execute_command",
        "run_command",
        "terminal",
        "system_exec",
        # Deployment / infrastructure
        "deploy",
        "ansible",
        "docker",
        "kubectl",
        "helm",
        "terraform",
        # Git mutations (write-side)
        "git_push",
        "git_commit",
        "git_merge",
        "git_rebase",
        "git_reset",
        "git_force_push",
        # Network / HTTP mutations
        "http_post",
        "http_put",
        "http_patch",
        "http_delete",
        "send_request",
        # Code execution
        "code_interpreter",
    }
)

# =============================================================================
# Repetition-Halt Guard (Issue #3859, #3862, #3877)
# =============================================================================

# Sentinel key injected into tool_results when the repetition-halt guard fires.
# Presence of this key in tool_results lets _execute_iteration_phases detect
# a halt without inspecting the error string.  Issue #3877.
_HALT_SENTINEL = "__repetition_halt__"

# Sentinel key for stagnation halts (Issue #6627).
_STAGNATION_SENTINEL = "__stagnation_halt__"

# =============================================================================
# Agent Loop
# =============================================================================


class AgentLoop:
    """
    The main agent execution loop.

    Implements the Manus-inspired 6-step iteration pattern with
    event stream integration, planning, and parallel tool execution.
    """

    def __init__(
        self,
        event_stream: EventStreamManager,
        planner: PlannerModule | None = None,
        tool_executor: ParallelToolExecutor | None = None,
        think_tool: ThinkTool | None = None,
        config: AgentLoopConfig | None = None,
        agent_id: str | None = None,
    ):
        """
        Initialize the agent loop.

        Args:
            event_stream: Event stream manager for publishing/subscribing
            planner: Optional planner module for task decomposition
            tool_executor: Optional parallel tool executor
            think_tool: Optional think tool for reasoning
            config: Loop configuration
            agent_id: Optional agent identity (GH#11145). When set, the agent's
                ``forbidden_work`` manifest is resolved from ``AgentRegistry`` and
                applied to ``config.forbidden_tools`` so ``_check_forbidden`` hard-
                blocks out-of-manifest tools. When unset (the default), the loop
                runs as no particular agent and the manifest is empty (no change).
        """
        self.event_stream = event_stream
        self.planner = planner
        self.tool_executor = tool_executor
        self.think_tool = think_tool or ThinkTool()
        self.agent_id = agent_id
        self.config = self._resolve_forbidden_tools(config or AgentLoopConfig(), agent_id)
        self._belief_updater = BeliefStateUpdater(
            contradiction_surface_threshold=self.config.contradiction_surface_threshold
        )

        # Adversarial pre-action verifier (#10547)
        self._verifier: PreActionVerifier | None = (
            PreActionVerifier() if self.config.pre_action_verifier_enabled else None
        )

        # State
        self._state = LoopState.IDLE
        self._current_phase = LoopPhase.STANDBY
        self._current_context: TaskContext | None = None
        self._iteration_count = 0
        self._consecutive_errors = 0
        # Steering inbox: human guidance messages queued for the next iteration (#10543)
        self._steering_inbox: asyncio.Queue[SteeringEntry] = asyncio.Queue()
        # Human-answer inbox: answers arrive here via answer() and resolve ask_human() waits (#10553)
        self._human_answer_inbox: asyncio.Queue[tuple[str, str]] = asyncio.Queue()  # (question_id, answer)
        # Set while loop is suspended waiting for a human answer (#10553)
        self._waiting_for_human: bool = False
        # Issue #3877: explicit flag set when repetition halt fires; checked by
        # _should_continue() so the main while-loop exits on the very next guard
        # check rather than relying solely on _should_iterate()'s error detection.
        self._halted_on_repetition: bool = False
        # GH#6626: confidence-based abstention state
        self._abstained: bool = False
        self._abstention_reason: str | None = None
        # GH#6628: set when a CRITICAL error causes an immediate halt
        self._fatal_error: Exception | None = None
        self._fatal_reason: str | None = None
        # GH#8649: set when per-severity retry budget is exhausted in
        # _handle_iteration_error(); checked by _should_continue() so the guard
        # uses the correct severity-aware limit rather than max_consecutive_errors.
        self._error_budget_exhausted: bool = False
        # Issue #6627: semantic stagnation halt state
        self._halted_on_stagnation: bool = False
        self._halt_outcome: "LoopOutcome | None" = None
        self._halt_reason: str = ""

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def state(self) -> LoopState:
        """Get current loop state."""
        return self._state

    @property
    def phase(self) -> LoopPhase:
        """Get current loop phase."""
        return self._current_phase

    @property
    def context(self) -> TaskContext | None:
        """Get current task context."""
        return self._current_context

    @property
    def iteration_count(self) -> int:
        """Get current iteration count."""
        return self._iteration_count

    # =========================================================================
    # Main Entry Points
    # =========================================================================

    def _init_task_context(
        self,
        task_id: str,
        task_description: str,
        initial_context: dict | None,
    ) -> None:
        """
        Initialize task context and state for new task.

        Issue #665: Extracted from run_task to reduce function length.

        Args:
            task_id: Task identifier
            task_description: Description of the task
            initial_context: Optional initial context/metadata
        """
        self._current_context = TaskContext(
            task_id=task_id,
            description=task_description,
            metadata=initial_context or {},
        )
        self._state = LoopState.INITIALIZING
        self._iteration_count = 0
        self._consecutive_errors = 0
        self._halted_on_repetition = False
        self._abstained = False
        self._abstention_reason = None
        self._fatal_error = None
        self._fatal_reason = None
        self._halted_on_stagnation = False
        self._halt_outcome = None
        self._halt_reason = ""
        self._error_budget_exhausted = False
        # Clear any leftover steering messages from a previous run.
        self._steering_inbox = asyncio.Queue()
        # Clear answer inbox and waiting flag from a previous run (#10553).
        self._human_answer_inbox = asyncio.Queue()
        self._waiting_for_human = False

    async def _execute_main_loop(self) -> list[IterationResult]:
        """Execute the main iteration loop.

        Issue #665: Extracted from run_task to reduce function length.

        Returns:
            List of iteration results
        """
        self._state = LoopState.RUNNING
        results: list[IterationResult] = []

        while self._should_continue():
            iteration_result = await self._run_iteration()
            results.append(iteration_result)

            if not iteration_result.should_continue:
                break

        return results

    async def _create_task_plan(self, task_description: str, initial_context: dict | None) -> None:
        """Create execution plan if planner is available.

        Issue #620: Extracted from run_task to reduce function length.

        Args:
            task_description: Description of the task
            initial_context: Optional initial context/metadata
        """
        if self.planner:
            plan = await self.planner.create_plan(
                task_description,
                context=initial_context,
            )
            self._current_context.plan_id = plan.plan_id
            logger.info("AgentLoop: Plan created with %d steps", len(plan.steps))

    async def _finalize_task(self, results: list[IterationResult]) -> dict[str, Any]:
        """Finalize task execution and build result.

        Issue #620: Extracted from run_task to reduce function length.
        GH#6626: Emits agent_abstained event and skips completion-think when abstaining.

        Args:
            results: List of iteration results

        Returns:
            Dict with task results
        """
        self._state = LoopState.COMPLETING
        if not self._abstained and self.config.think_on_completion:
            await self._think_before_completion()

        self._state = LoopState.COMPLETED
        result = self._build_result(results)

        if self._abstained and self._current_context is not None:
            await _bus_publish_event(
                "global",
                EVT_AGENT_ABSTAINED,
                {
                    "task_id": self._current_context.task_id,
                    "abstained": True,
                    "abstention_reason": self._abstention_reason,
                    "iterations": len(results),
                    "think_count": len(self._current_context.think_history),
                },
                persist=PersistStrategy.MEMORY,
            )
            logger.info(
                "AgentLoop: task %s abstained — %s",
                self._current_context.task_id,
                self._abstention_reason,
            )

        return result

    async def run_task(
        self,
        task_description: str,
        task_id: str | None = None,
        initial_context: dict | None = None,
    ) -> dict[str, Any]:
        """Run a complete task through the agent loop.

        Issue #665, #620: Refactored to use extracted helper methods.

        Args:
            task_description: Description of the task to perform
            task_id: Optional task ID (generated if not provided)
            initial_context: Optional initial context/metadata

        Returns:
            Dict with task results
        """
        task_id = task_id or f"task-{uuid.uuid4().hex[:12]}"
        logger.info("AgentLoop: Starting task %s: %s", task_id, task_description[:100])

        self._init_task_context(task_id, task_description, initial_context)

        # Issue #4308: notify Slack that the agent has started
        slack = get_slack_hook()
        await slack.post_agent_status(
            agent_name="AgentLoop",
            status="started",
            message=f"Task {task_id}: {task_description[:120]}",
        )

        _task_start = time.monotonic()

        try:
            # Issue #620: Use helper for plan creation
            await self._create_task_plan(task_description, initial_context)

            results = await self._execute_main_loop()

            # Issue #620: Use helper for task finalization
            result = await self._finalize_task(results)

            # Issue #4308: notify Slack on successful task completion
            duration = time.monotonic() - _task_start
            await slack.post_task_completion(
                task_id=task_id,
                task_title=task_description[:80],
                agent_name="AgentLoop",
                summary=(
                    f"Completed {result.get('iterations', 0)} iteration(s), "
                    f"{result.get('tools_executed', 0)} tool(s) executed."
                ),
                status="completed",
                duration_seconds=duration,
            )
            return result

        except asyncio.CancelledError:
            self._state = LoopState.CANCELLED
            logger.warning("AgentLoop: Task %s cancelled", task_id)
            raise

        except Exception as e:
            self._state = LoopState.FAILED
            logger.error("AgentLoop: Task %s failed: %s", task_id, e)
            # Issue #4308: notify Slack on task failure
            duration = time.monotonic() - _task_start
            await slack.post_task_completion(
                task_id=task_id,
                task_title=task_description[:80],
                agent_name="AgentLoop",
                summary=f"Task failed: {e}",
                status="failed",
                duration_seconds=duration,
            )
            raise

        finally:
            self._current_phase = LoopPhase.STANDBY

    async def cancel(self) -> None:
        """Cancel the current task."""
        if self._state == LoopState.RUNNING:
            self._state = LoopState.CANCELLED
            logger.info("AgentLoop: Task cancellation requested")

    async def pause(self) -> None:
        """Pause the current task."""
        if self._state == LoopState.RUNNING:
            self._state = LoopState.PAUSED
            logger.info("AgentLoop: Task paused")

    async def resume(self) -> None:
        """Resume a paused task."""
        if self._state == LoopState.PAUSED:
            self._state = LoopState.RUNNING
            logger.info("AgentLoop: Task resumed")

    async def steer(self, steering_id: str, guidance: str) -> bool:
        """Queue a human steering message for the next ANALYZE_EVENTS phase (#10543).

        Steering is distinct from cancel/pause: the loop continues without
        interruption; the guidance is absorbed at the top of the next iteration
        and used to amend the current plan.  Returns False when no task is
        running (caller should surface a 409 / noop to the frontend).
        """
        if self._state != LoopState.RUNNING:
            logger.warning(
                "AgentLoop: steer() called while state=%s — message dropped (steering_id=%s)",
                self._state.name,
                steering_id,
            )
            return False
        entry = SteeringEntry(
            steering_id=steering_id,
            guidance=guidance,
            iteration=self._iteration_count,
        )
        await self._steering_inbox.put(entry)
        logger.info("AgentLoop: steering message queued (steering_id=%s)", steering_id)
        return True

    async def answer(self, question_id: str, answer_text: str) -> bool:
        """Deliver a human's answer to a suspended ask_human() call (#10553).

        Routes the answer into the ``_human_answer_inbox`` queue so the
        awaiting ``ask_human()`` coroutine picks it up immediately.
        Returns False when no task is running (caller should surface 409).
        Mirrors ``steer()`` — same guard logic, same inbox pattern.
        """
        if self._state not in (LoopState.RUNNING, LoopState.WAITING_FOR_HUMAN):
            logger.warning(
                "AgentLoop: answer() called while state=%s — dropped (question_id=%s)",
                self._state.name,
                question_id,
            )
            return False
        await self._human_answer_inbox.put((question_id, answer_text))
        logger.info("AgentLoop: human answer queued (question_id=%s)", question_id)
        return True

    # =========================================================================
    # Iteration Logic
    # =========================================================================

    async def _execute_iteration_phases(self, result: IterationResult) -> IterationResult:
        """
        Execute all phases of an iteration.

        Args:
            result: The IterationResult to populate

        Returns:
            Updated IterationResult with phase outcomes. Issue #620.
        """
        # Phase 1: Analyze Events
        self._current_phase = LoopPhase.ANALYZE_EVENTS
        events_context = await self._analyze_events()
        result.events_analyzed = len(events_context.get("events", []))

        # Issue #4528: inject first_turn_note into user content on first turn.
        # _analyze_events() sets context["first_turn_note"] on iteration 1 when
        # first_turn_priming_enabled=True, but nothing downstream consumed it.
        # Extract it here, append to the task description carried in events_context,
        # then clear it so subsequent iterations are not affected.
        first_turn_note = events_context.pop("first_turn_note", None)
        if first_turn_note and self.config.first_turn_priming_enabled:
            task_content = events_context.get("task_description", "")
            events_context["task_description"] = (
                task_content + "\n\n" + first_turn_note if task_content else first_turn_note
            )

        # Phase 2: Select Tools
        self._current_phase = LoopPhase.SELECT_TOOLS
        tools_to_execute = await self._select_tools(events_context)

        if not tools_to_execute:
            result.phase_completed = LoopPhase.SELECT_TOOLS
            result.should_continue = False
            return result

        # Phase 3: Execute Tools
        self._current_phase = LoopPhase.WAIT_FOR_EXECUTION

        # MVA-1434: pre-execution cache check — skip redundant tool calls when a
        # high-confidence assertion already covers the same tool+key.
        tools_to_run = tools_to_execute
        cached_results: dict[str, Any] = {}
        if self.config.belief_state_enabled and self._current_context:
            tools_to_run = []
            for tool in tools_to_execute:
                tool_name = tool.get("tool_name", "")
                tool_args = tool.get("args", tool.get("arguments", tool.get("parameters", {})))
                if not isinstance(tool_args, dict):
                    tool_args = {}
                cached_val = self._maybe_use_cached_assertion(tool_name, tool_args)
                if cached_val is not None:
                    cached_results[tool_name] = {"cached_assertion": cached_val}
                    await _bus_publish_event(
                        "global",
                        EVT_BELIEF_CACHE_HIT,
                        {
                            "task_id": self._current_context.task_id,
                            "tool_name": tool_name,
                            "iteration": self._iteration_count,
                        },
                        persist=PersistStrategy.MEMORY,
                    )
                    logger.info(
                        "AgentLoop: belief cache hit — skipping '%s' (iteration %d)",
                        tool_name,
                        self._iteration_count,
                    )
                else:
                    tools_to_run.append(tool)

        live_results = await self._execute_tools(tools_to_run) if tools_to_run else {}
        tool_results = {**cached_results, **live_results}

        # Issue #3877 / #3859: detect repetition-halt via sentinel key.
        # When halted: do not add any rejected tools to tools_executed and
        # stop iterating immediately so the LLM receives the error but the
        # loop does not re-propose the same tools indefinitely.
        if tool_results.pop(_HALT_SENTINEL, False):
            # Issue #3862: keep should_continue=False so the loop exits, but
            # surface the halt errors as tool_results so the LLM can adapt.
            # Issue #3859: tools_executed stays empty — no tool actually ran.
            result.tools_executed = []
            result.tool_results = tool_results
            result.should_continue = False
            result.phase_completed = LoopPhase.ITERATE
            return result

        # Only live executions count toward tools_executed; cached hits are not tools_executed.
        result.tools_executed = [t.get("tool_name", "unknown") for t in tools_to_run]
        result.tool_results = tool_results

        for tool_name in result.tools_executed:
            self._current_context.add_tool(tool_name)

        # MVA-1407: update belief state from live tool results when enabled.
        if self.config.belief_state_enabled and self._current_context:
            for tool_info in tools_to_run:
                tool_name = tool_info.get("tool_name", "")
                call_hash = self._compute_tool_call_hash(tool_info)
                raw_result = live_results.get(tool_name) or live_results.get(tool_info.get("id", ""))
                if raw_result is not None:
                    self._belief_updater.update(
                        self._current_context,
                        tool_name,
                        raw_result,
                        call_hash,
                        self._iteration_count,
                    )

        # Issue #6627: fingerprint observations and check for stagnation.
        self._record_observation_fingerprints(tool_results)
        if self._check_observation_stagnation():
            window = self.config.stagnation_window
            fingerprints = self._current_context.observation_fingerprints
            recent = fingerprints[-window:]
            avg_novelty = sum(f.novel_token_ratio for f in recent) / window
            self._halted_on_stagnation = True
            self._halt_outcome = LoopOutcome.STAGNATED
            self._halt_reason = (
                f"Halted: observation stagnation — avg novelty {avg_novelty:.3f} "
                f"< {self.config.min_observation_novelty} over {window} observations"
            )
            result.should_continue = False
            result.phase_completed = LoopPhase.ITERATE
            return result

        # Phase 4: Iterate
        self._current_phase = LoopPhase.ITERATE
        result.should_continue = await self._should_iterate(tool_results)

        if self._current_context.plan_id and self.planner:
            result.plan_progress = await self._get_plan_progress()

        result.phase_completed = LoopPhase.ITERATE
        self._consecutive_errors = 0
        self._error_budget_exhausted = False
        return result

    def _log_iteration_completion(self, start_time: float, result: IterationResult) -> None:
        """
        Log iteration completion details if configured.

        Args:
            start_time: Monotonic time when iteration started
            result: The completed IterationResult. Issue #620.
        """
        if self.config.log_iterations:
            duration = (time.monotonic() - start_time) * 1000
            logger.info(
                "AgentLoop: Iteration %d completed in %.1fms (tools: %s)",
                self._iteration_count,
                duration,
                result.tools_executed,
            )

    async def _run_iteration(self) -> IterationResult:
        """Run a single iteration of the agent loop."""
        self._iteration_count += 1
        start_time = time.monotonic()
        logger.debug("AgentLoop: Starting iteration %d", self._iteration_count)

        result = IterationResult(iteration_number=self._iteration_count)

        try:
            result = await self._execute_iteration_phases(result)
        except Exception as e:
            result.error = str(e)
            result.should_continue = await self._handle_iteration_error(e)
            self._current_context.add_error(str(e))

        self._log_iteration_completion(start_time, result)
        return result

    # =========================================================================
    # Phase Implementations
    # =========================================================================

    async def _drain_steering_inbox(self) -> list[SteeringEntry]:
        """Drain all pending steering messages from the inbox without blocking.

        Called at the top of ANALYZE_EVENTS each iteration (#10543).  Each
        drained entry is recorded in the trajectory and published to the live
        event bus so the frontend can surface an acknowledgement.
        """
        drained: list[SteeringEntry] = []
        while not self._steering_inbox.empty():
            try:
                entry = self._steering_inbox.get_nowait()
            except asyncio.QueueEmpty:
                break
            drained.append(entry)
            if self._current_context is not None:
                self._current_context.add_steering(entry)
            task_id = self._current_context.task_id if self._current_context else None
            await _bus_publish_event(
                f"task:{task_id}" if task_id else "global",
                EVT_STEERING_RECEIVED,
                {
                    "steering_id": entry.steering_id,
                    "guidance": entry.guidance,
                    "iteration": self._iteration_count,
                    "task_id": task_id,
                },
                persist=PersistStrategy.MEMORY,
            )
            logger.info(
                "AgentLoop: steering message absorbed (steering_id=%s, iteration=%d)",
                entry.steering_id,
                self._iteration_count,
            )
        return drained

    async def _analyze_events(self) -> dict[str, Any]:
        """
        Phase 1: Analyze recent events from the event stream.

        Drains the steering inbox first so that human guidance is always the
        highest-priority context for tool selection in this iteration (#10543).

        Returns context for tool selection.
        """
        # (#10543) Drain steering inbox BEFORE reading the event stream so that
        # any guidance queued since the last iteration is already in the context
        # when _select_tools() runs.  This is non-blocking (get_nowait) so the
        # loop never stalls waiting for a steering message that is not there.
        steering_entries = await self._drain_steering_inbox()

        events = await self.event_stream.get_latest(
            count=self.config.events_to_analyze,
            task_id=self._current_context.task_id if self._current_context else None,
        )

        # Filter out system events if configured
        if not self.config.include_system_events:
            events = [e for e in events if e.event_type != EventType.SYSTEM]

        # Build context from events
        context: dict[str, Any] = {
            "events": [e.to_dict() for e in events],
            "event_count": len(events),
            "event_types": list(set(e.event_type.name for e in events)),
            "recent_actions": [e.content for e in events if e.event_type == EventType.ACTION][-5:],
            "recent_observations": [e.content for e in events if e.event_type == EventType.OBSERVATION][-5:],
        }

        # (#10543) Inject steering guidance as a high-priority context amendment.
        # When present, _select_tools() must treat these as goal constraints that
        # supersede the original plan without restarting the loop.
        if steering_entries:
            context["steering_guidance"] = [e.to_dict() for e in steering_entries]
            context["has_steering"] = True
            logger.debug(
                "AgentLoop: %d steering message(s) injected into ANALYZE_EVENTS context",
                len(steering_entries),
            )

        # Issue #4481: inject a first-turn context hint so the LLM knows no
        # prior tool results exist yet.  Only added on iteration 1 (the very
        # first call) when the feature is enabled.
        if self.config.first_turn_priming_enabled and self._iteration_count == 1:
            context["first_turn_note"] = "Note: This is the first iteration — no tool results exist yet."

        return context

    async def _select_tools(
        self,
        events_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Phase 2: Select tools to execute based on context.

        This is where the agent decides what to do next.
        Returns list of tool specifications.
        """
        # If we have a plan, get the current step
        if self._current_context and self._current_context.plan_id and self.planner:
            plan = await self.planner.get_plan(self._current_context.plan_id)
            if plan:
                # Get next steps to execute (may be parallel)
                next_steps = plan.get_parallel_group()
                if next_steps:
                    # Convert plan steps to tool calls
                    # This would integrate with the LLM to determine actual tools
                    return await self._plan_steps_to_tools(next_steps, events_context)

        # Without a plan, we need LLM to select tools
        # This is a placeholder - actual implementation would call LLM
        return []

    async def _execute_tools(
        self,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Phase 3: Execute selected tools.

        Uses parallel executor if available and configured.
        """
        if not tools:
            return {}

        # Issue #3255 / #3877: Halt before execution if identical call repeated too often.
        # Setting _halted_on_repetition=True ensures _should_continue() terminates the
        # main while-loop immediately after this iteration, independent of whether
        # _should_iterate() correctly classifies the error result.
        repeated_tool = self._check_tool_call_repetition(tools)
        if repeated_tool is not None:
            halt_msg = (
                f"Halted: repetitive tool call detected for '{repeated_tool}' "
                f"(exceeded max_identical_tool_calls="
                f"{self.config.max_identical_tool_calls})"
            )
            # Issue #3877: include ALL tools in halt results so _should_iterate
            # sees every tool from the batch as having an error result.
            # Issue #3859: do NOT record any of these in tools_executed — the
            # sentinel key lets _execute_iteration_phases skip add_tool() calls
            # and set should_continue=False without calling _should_iterate.
            halt_results: dict[str, Any] = {
                _HALT_SENTINEL: True,
            }
            for tool in tools:
                t_name = tool.get("tool_name", "unknown")
                halt_results[t_name] = {"error": halt_msg}
            self._halted_on_repetition = True
            return halt_results

        # GH#11139: hard-block tools outside this agent's capability manifest
        # (forbidden_work) BEFORE the approval gate — a forbidden tool is never
        # offered for approval.
        forbidden_results = self._check_forbidden(tools)
        if forbidden_results:
            return forbidden_results

        # Issue #4092: Gate sensitive operations behind user approval.
        denied_results = await self._check_approvals(tools)
        if denied_results:
            return denied_results

        # Check if we need to think before certain tools
        await self._think_before_tools(tools)

        if self.tool_executor and self.config.enable_parallel_tools:
            # Use parallel executor
            from tools.parallel import create_tool_calls

            tool_calls = create_tool_calls(tools)
            return await self.tool_executor.execute_batch(
                tool_calls,
                task_id=(self._current_context.task_id if self._current_context else None),
            )

        # Sequential execution (fallback)
        results = {}
        for tool in tools:
            tool_name = tool.get("tool_name", "unknown")
            try:
                # This would integrate with actual tool dispatcher
                result = await self._dispatch_tool(tool)
                results[tool_name] = result
            except Exception as e:
                logger.error("Tool %s execution failed: %s", tool_name, e)
                results[tool_name] = {"error": "Tool execution failed"}

        return results

    async def _should_iterate(
        self,
        tool_results: dict[str, Any],
    ) -> bool:
        """
        Phase 4: Determine if we should continue iterating.

        Returns True if more iterations are needed.
        """
        # Check for cancellation/pause
        if self._state != LoopState.RUNNING:
            return False

        # Check iteration limit
        if self._iteration_count >= self.config.max_iterations:
            logger.warning(
                "AgentLoop: Max iterations (%d) reached",
                self.config.max_iterations,
            )
            return False

        # Check if plan is complete
        if self._current_context and self._current_context.plan_id and self.planner:
            plan = await self.planner.get_plan(self._current_context.plan_id)
            if plan and plan.is_complete:
                return False

        # Check if all tools succeeded
        all_succeeded = all("error" not in result for result in tool_results.values() if isinstance(result, dict))

        return all_succeeded

    # =========================================================================
    # Message Handling (Manus Pattern)
    # =========================================================================

    async def notify(self, content: str, metadata: dict | None = None) -> None:
        """
        Send a non-blocking notification to the user.

        Args:
            content: Message content
            metadata: Optional metadata
        """
        message = AgentMessage(
            message_type=MessageType.NOTIFY,
            content=content,
            metadata=metadata or {},
            task_id=self._current_context.task_id if self._current_context else None,
        )

        event = create_message_event(
            role="assistant",
            content=message.to_dict(),
            task_id=message.task_id,
        )
        await self.event_stream.publish(event)

    async def ask(
        self,
        content: str,
        options: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        """
        Send a blocking question to the user.

        Args:
            content: Question content
            options: Optional list of answer options
            metadata: Optional metadata

        Returns:
            User's response
        """
        message = AgentMessage(
            message_type=MessageType.ASK,
            content=content,
            options=options,
            metadata=metadata or {},
            task_id=self._current_context.task_id if self._current_context else None,
        )

        event = create_message_event(
            role="assistant",
            content=message.to_dict(),
            task_id=message.task_id,
        )
        await self.event_stream.publish(event)

        # Wait for user response
        # This would integrate with the event stream subscription
        # Placeholder - actual implementation would wait for user MESSAGE event
        return ""

    async def ask_human(
        self,
        question: str,
        choices: list[str] | None = None,
        escalation_policy: str | None = None,
        default_answer: str | None = None,
        question_id_override: str | None = None,
    ) -> str:
        """Emit a clarifying question, suspend the loop, and resume on answer (#10553).

        The loop state transitions to WAITING_FOR_HUMAN; the question is published
        to the live task channel so the in-app UI renders an answer affordance.
        Slack/push are notified via the existing hooks (fire-and-forget).
        The pending question is checkpointed to Redis so a restarted loop can
        detect it is still suspended.

        Returns the human's answer text (authoritative; injects into trajectory).
        Raises asyncio.TimeoutError only when escalation_policy="abandon" and the
        deadline passes; callers should treat that as TIMED_OUT_WAITING.
        """
        question_id = question_id_override or str(uuid.uuid4())
        task_id = self._current_context.task_id if self._current_context else None
        policy = escalation_policy or self.config.ask_human_escalation_policy
        timeout = self.config.ask_human_timeout_seconds

        hq = HumanQuestion(
            question_id=question_id,
            question=question,
            iteration=self._iteration_count,
            choices=choices,
            escalation_policy=policy,
            default_answer=default_answer,
        )
        if self._current_context is not None:
            self._current_context.add_human_question(hq)

        await self._checkpoint_question(hq, task_id)
        await self._emit_human_question(hq, task_id, timeout)

        prev_state = self._state
        self._state = LoopState.WAITING_FOR_HUMAN
        self._waiting_for_human = True
        try:
            return await self._wait_for_answer(hq, timeout, policy, default_answer)
        finally:
            self._waiting_for_human = False
            if self._state == LoopState.WAITING_FOR_HUMAN:
                self._state = prev_state
            await self._clear_question_checkpoint(question_id, task_id)

    async def _emit_human_question(
        self,
        hq: "HumanQuestion",
        task_id: str | None,
        timeout: int,
    ) -> None:
        """Publish HUMAN_QUESTION to the event bus + Slack/push (fire-and-forget)."""
        event = create_human_question_event(
            question_id=hq.question_id,
            question=hq.question,
            timeout_seconds=timeout,
            task_id=task_id,
            choices=hq.choices,
        )
        await self.event_stream.publish(event)
        channel = f"task:{task_id}" if task_id else "global"
        await _bus_publish_event(
            channel,
            EVT_HUMAN_QUESTION,
            {
                "question_id": hq.question_id,
                "question": hq.question,
                "choices": hq.choices,
                "timeout_seconds": timeout,
                "task_id": task_id,
                "iteration": hq.iteration,
            },
            persist=PersistStrategy.MEMORY,
        )
        slack = get_slack_hook()
        await slack.ask_human(
            question_id=hq.question_id,
            question=hq.question,
            choices=hq.choices,
            task_id=task_id,
        )
        logger.info(
            "AgentLoop: ask_human emitted (question_id=%s, policy=%s, timeout=%ds)",
            hq.question_id,
            hq.escalation_policy,
            timeout,
        )

    async def _wait_for_answer(
        self,
        hq: "HumanQuestion",
        timeout: int,
        policy: str,
        default_answer: str | None,
    ) -> str:
        """Wait up to *timeout* seconds for a human answer (#10553).

        Two sources are drained concurrently:
        1. ``_human_answer_inbox`` — direct in-process delivery via answer().
        2. Event stream subscription — delivery via the REST endpoint or any
           other channel that publishes a HUMAN_ANSWER event with matching id.

        Applies escalation policy when the deadline expires:
        - "abandon": raises asyncio.TimeoutError (caller sets TIMED_OUT_WAITING).
        - "default": returns default_answer (or "" if unset).
        - "re_ask": retries once; abandons after the second timeout.
        """

        async def _drain() -> str:
            # Race between in-process queue and event stream subscription.
            queue_task = asyncio.ensure_future(self._drain_answer_queue(hq.question_id))
            stream_task = asyncio.ensure_future(self._drain_answer_stream(hq.question_id))
            done, pending = await asyncio.wait({queue_task, stream_task}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            return next(iter(done)).result()

        try:
            answer = await asyncio.wait_for(_drain(), timeout=timeout)
        except asyncio.TimeoutError:
            if policy == "default":
                answer = default_answer or ""
                logger.warning(
                    "AgentLoop: ask_human timeout — using default answer (question_id=%s)",
                    hq.question_id,
                )
            elif policy == "re_ask":
                logger.warning("AgentLoop: ask_human timeout — re-asking once (question_id=%s)", hq.question_id)
                re_ask_task_id = self._current_context.task_id if self._current_context else None
                await self._emit_human_question(hq, re_ask_task_id, timeout)
                try:
                    answer = await asyncio.wait_for(_drain(), timeout=timeout)
                except asyncio.TimeoutError:
                    raise
            else:  # "abandon"
                raise

        task_id = self._current_context.task_id if self._current_context else None
        await _bus_publish_event(
            f"task:{task_id}" if task_id else "global",
            EVT_HUMAN_ANSWER_RECEIVED,
            {"question_id": hq.question_id, "answer": answer, "task_id": task_id},
            persist=PersistStrategy.MEMORY,
        )
        logger.info(
            "AgentLoop: ask_human resolved (question_id=%s, answer=%r)",
            hq.question_id,
            answer[:80],
        )
        return answer

    async def _drain_answer_queue(self, question_id: str) -> str:
        """Block until the in-process answer inbox yields the matching answer (#10553)."""
        while True:
            qid, ans = await self._human_answer_inbox.get()
            if qid == question_id:
                return ans
            # Unrelated question_id — put it back and retry.
            await self._human_answer_inbox.put((qid, ans))

    async def _drain_answer_stream(self, question_id: str) -> str:
        """Subscribe to the event stream and return when a HUMAN_ANSWER matches (#10553).

        Mirrors _request_approval's subscribe() pattern so remote answers (REST,
        Slack reply, mobile push) resolve the wait the moment they are published.
        """
        async for event in self.event_stream.subscribe(event_types=[EventType.HUMAN_ANSWER]):
            if event.content.get("question_id") == question_id:
                return event.content.get("answer", "")
        return ""  # stream exhausted (loop shutdown)

    async def _checkpoint_question(self, hq: "HumanQuestion", task_id: str | None) -> None:
        """Persist the pending question to Redis so a restart can detect suspension (#10553)."""
        try:
            from autobot_shared.redis_client import redis_set

            key = f"autobot:ask_human:{task_id or 'global'}:{hq.question_id}"
            await redis_set(key, json.dumps(hq.to_dict()), expire=self.config.ask_human_timeout_seconds + 60)
        except Exception as exc:
            logger.warning("AgentLoop: ask_human checkpoint failed (non-critical): %s", exc)

    async def _clear_question_checkpoint(self, question_id: str, task_id: str | None) -> None:
        """Remove the Redis checkpoint after the question is resolved or abandoned (#10553)."""
        try:
            from autobot_shared.redis_client import redis_delete

            key = f"autobot:ask_human:{task_id or 'global'}:{question_id}"
            await redis_delete(key)
        except Exception as exc:
            logger.warning("AgentLoop: ask_human checkpoint clear failed (non-critical): %s", exc)

    # =========================================================================
    # Think Tool Integration
    # =========================================================================

    async def _think_before_tools(
        self,
        tools: list[dict[str, Any]],
    ) -> None:
        """Think before executing certain tools."""
        if not self.config.mandatory_think_enabled:
            return

        # Check for git tools
        git_tools = {"git", "gh", "github"}
        has_git_tool = any(
            tool.get("tool_name", "").lower() in git_tools or "git" in tool.get("tool_name", "").lower()
            for tool in tools
        )

        if has_git_tool and self.config.think_on_git:
            context = f"About to execute git tools: {[t.get('tool_name') for t in tools]}"
            result = await self.think_tool.think(
                ThinkCategory.GIT_DECISION,
                context,
                task_id=(self._current_context.task_id if self._current_context else None),
            )
            if self._current_context:
                self._current_context.add_think(result)

    async def _think_before_completion(self) -> None:
        """Think before reporting task completion."""
        if not self._current_context:
            return

        belief_summary = ""
        if self.config.belief_state_enabled and self._current_context.assertions:
            active = [a for a in self._current_context.assertions.values() if a.is_active]
            top = sorted(active, key=lambda a: a.confidence, reverse=True)[:20]
            lines = [f"  {a.key} = {a.value!r} @ {a.confidence:.2f}" for a in top]
            belief_summary = "\nBelief state (top assertions):\n" + "\n".join(lines) + "\n"

        context = f"""
Task: {self._current_context.description}
Iterations: {self._iteration_count}
Tools executed: {len(self._current_context.tools_executed)}
Errors: {len(self._current_context.errors)}
Duration: {self._current_context.get_duration_ms():.0f}ms{belief_summary}
"""
        result = await self.think_tool.think(
            ThinkCategory.COMPLETION,
            context,
            task_id=self._current_context.task_id,
        )
        self._current_context.add_think(result)

    # =========================================================================
    # Helper Methods
    # =========================================================================

    # =========================================================================
    # Belief Cache (MVA-1434)
    # =========================================================================

    def _maybe_use_cached_assertion(self, tool_name: str, tool_args: dict) -> Any | None:
        """Return cached assertion value if a high-confidence belief covers this call.

        Returns None when belief state is disabled, no extractor key exists for the
        tool+args, the assertion is absent or refuted, or confidence is below the
        configured threshold.
        """
        from agent_loop.belief_state import build_extractor_key

        if not self._current_context:
            return None
        key = build_extractor_key(tool_name, tool_args)
        if not key:
            return None
        assertion = self._current_context.assertions.get(key)
        if assertion is None:
            return None
        if assertion.is_active and assertion.confidence >= self.config.belief_cache_threshold:
            return assertion.value
        return None

    # =========================================================================
    # Repetitive Tool-Call Detection (#3255)
    # =========================================================================

    @staticmethod
    def _compute_tool_call_hash(tool: dict[str, Any]) -> str:
        """Return a stable content hash for a tool call.

        The hash is derived from the tool name and its sorted arguments so that
        two calls with identical intent produce the same hash regardless of
        dict-insertion order.

        Issue #3255, #3868, #3874.
        """
        tool_name = tool.get("tool_name", "")
        args = tool.get("args", tool.get("arguments", tool.get("parameters", {})))
        # Issue #3874: preserve non-dict arg identity; {} would alias all
        # non-dict calls to the same bucket
        if not isinstance(args, dict):
            args = {"_raw": str(args), "_type": type(args).__name__}
        try:
            # Issue #3868: default=str handles datetime, bytes, custom objects
            canonical = json.dumps({"n": tool_name, "a": args}, sort_keys=True, default=str)
        except Exception:
            # Absolute fallback — should never be reached with default=str
            canonical = repr({"n": tool_name, "a": args})
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _check_tool_call_repetition(self, tools: list[dict[str, Any]]) -> str | None:
        """Check whether any pending tool call has been issued too many times.

        Returns the offending tool name if repetition is detected, else None.
        Records each call regardless so the counter accumulates across iterations.

        Issue #3255.
        """
        if not self._current_context:
            return None

        threshold = self.config.max_identical_tool_calls
        for tool in tools:
            call_hash = self._compute_tool_call_hash(tool)
            count = self._current_context.record_tool_call_hash(call_hash)
            tool_name = tool.get("tool_name", "unknown")
            if count >= threshold:
                logger.warning(
                    "AgentLoop: Detected repetitive tool call: %s called %d times "
                    "with identical args (threshold=%d)",
                    tool_name,
                    count,
                    threshold,
                )
                return tool_name
        return None

    # =========================================================================
    # Semantic Stagnation Detection (Issue #6627)
    # =========================================================================

    def _record_observation_fingerprints(self, tool_results: dict[str, Any]) -> None:
        """Fingerprint successful tool results and append to the task context.

        Error results (dicts with an "error" key) are skipped — only successful
        observations contribute to the novelty window.  Issue #6627.
        """
        if not self._current_context:
            return
        for result in tool_results.values():
            if isinstance(result, dict) and result.get("error"):
                continue
            self._current_context.record_observation(result, iteration=self._iteration_count)

    def _check_observation_stagnation(self) -> bool:
        """Return True when the recent observation window shows no novelty.

        Disabled when halt_on_stagnation=False or when the context is absent.
        Issue #6627.
        """
        if not self.config.halt_on_stagnation:
            return False
        if not self._current_context:
            return False
        fingerprints = self._current_context.observation_fingerprints
        window = self.config.stagnation_window
        if len(fingerprints) < window:
            return False
        recent = fingerprints[-window:]
        avg_novelty = sum(f.novel_token_ratio for f in recent) / window
        return avg_novelty < self.config.min_observation_novelty

    # =========================================================================
    # Approval Workflow (Issue #4092)
    # =========================================================================

    @staticmethod
    def _sensitive_tool_name(tool: dict[str, Any]) -> str | None:
        """Return the tool name if it is in SENSITIVE_TOOLS, else None."""
        name = tool.get("tool_name", "").lower()
        if name in SENSITIVE_TOOLS:
            return name
        # Also match by prefix so e.g. "bash_run" → "bash" is caught.
        for sensitive in SENSITIVE_TOOLS:
            if name.startswith(sensitive):
                return sensitive
        return None

    @staticmethod
    def _resolve_forbidden_tools(
        config: "AgentLoopConfig", agent_id: str | None
    ) -> "AgentLoopConfig":
        """Populate ``config.forbidden_tools`` from the agent's manifest (GH#11145).

        Reads ``forbidden_work`` off the agent's ``AgentProfile`` via
        ``AgentRegistry`` and returns a config with those tools hard-blocked. When
        no ``agent_id`` is given, or the config already carries an explicit
        ``forbidden_tools`` set, or the agent has no boundary, the config is
        returned unchanged. Registry resolution never raises into the loop — a
        lookup failure logs and falls back to the (unbounded) config.
        """
        if not agent_id or config.forbidden_tools:
            return config
        try:
            from dataclasses import replace

            from orchestration.agent_registry import AgentRegistry

            forbidden = AgentRegistry(initialize_defaults=True).forbidden_tools(agent_id)
        except Exception as exc:  # pragma: no cover - defensive; registry import/lookup
            logger.warning(
                "AgentLoop: could not resolve forbidden_work for agent '%s': %s",
                agent_id,
                exc,
            )
            return config
        if not forbidden:
            return config
        logger.info(
            "AgentLoop: agent '%s' forbidden_work manifest active (%d tools)",
            agent_id,
            len(forbidden),
        )
        return replace(config, forbidden_tools=forbidden)

    def _forbidden_tool_name(self, tool: dict[str, Any]) -> str | None:
        """Return the matched forbidden-tool name for *tool*, else None (GH#11139).

        Uses the same name/prefix matching as ``_sensitive_tool_name`` but against
        the agent's ``forbidden_work`` manifest (``config.forbidden_tools``).
        """
        forbidden = self.config.forbidden_tools
        if not forbidden:
            return None
        name = tool.get("tool_name", "").lower()
        if name in forbidden:
            return name
        for f in forbidden:
            if name.startswith(f):
                return f
        return None

    def _check_forbidden(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Hard-block the first tool the agent's manifest forbids (GH#11139).

        Returns a denial result dict (same shape as a user-denied approval) for
        the first forbidden tool, or ``{}`` when none are forbidden.
        """
        for tool in tools:
            matched = self._forbidden_tool_name(tool)
            if matched is not None:
                tool_name = tool.get("tool_name", "unknown")
                logger.warning(
                    "AgentLoop: tool '%s' blocked by agent forbidden_work manifest (matched '%s')",
                    tool_name,
                    matched,
                )
                return {
                    tool_name: {
                        "error": (
                            f"Tool '{tool_name}' is forbidden by this agent's capability "
                            f"manifest (matched '{matched}')"
                        )
                    }
                }
        return {}

    def _requires_approval(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return the subset of *tools* that require user approval.

        Returns an empty list when approval is disabled in the config.
        """
        if not self.config.require_approval_for_sensitive:
            return []
        return [t for t in tools if self._sensitive_tool_name(t) is not None]

    async def _check_approvals(
        self,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Request approval for every sensitive tool in *tools*.

        Iterates sequentially so the user sees one dialog at a time.
        Returns a non-empty error dict if any tool is denied (the remaining
        tools are skipped); returns ``{}`` when all are approved or when
        approval is not required.
        """
        for tool in self._requires_approval(tools):
            tool_name = tool.get("tool_name", "unknown")
            args = tool.get("args", tool.get("arguments", tool.get("parameters", {})))
            if not isinstance(args, dict):
                args = {"value": repr(args)}
            reason = tool.get("reason", "")

            # Adversarial pre-action verifier pass (#10547) — runs before human approval.
            verifier_result = await self._run_verifier(tool_name, args, reason)
            if verifier_result is not None:
                await self._record_verifier_verdict(verifier_result)
                if verifier_result.verdict == VerifierVerdict.BLOCK:
                    from agent_loop.pre_action_verifier import HARD_BLOCK

                    if HARD_BLOCK:
                        logger.warning(
                            "AgentLoop: verifier hard-blocked tool '%s' — %s",
                            tool_name,
                            verifier_result.rationale[:120],
                        )
                        return {
                            tool_name: {
                                "error": (
                                    f"Tool '{tool_name}' was hard-blocked by the adversarial "
                                    f"verifier (prob={verifier_result.refutation_probability:.2f}): "
                                    f"{verifier_result.rationale}"
                                )
                            }
                        }
                    # Soft-block: escalate to human with verifier rationale attached
                    tool = dict(tool)
                    tool["verifier_rationale"] = (
                        f"[Verifier BLOCK prob={verifier_result.refutation_probability:.2f}] "
                        f"{verifier_result.rationale}"
                    )

            approval_id = str(uuid.uuid4())
            approved = await self._request_approval(tool, approval_id)
            if not approved:
                logger.warning(
                    "AgentLoop: tool '%s' denied by user (approval_id=%s)",
                    tool_name,
                    approval_id,
                )
                return {
                    tool_name: {"error": (f"Tool '{tool_name}' was denied by the user " f"(approval_id={approval_id})")}
                }
        return {}

    async def _run_verifier(
        self,
        tool_name: str,
        args: dict[str, Any],
        reason: str,
    ) -> "VerifierResult | None":
        """Dispatch the adversarial verifier for *tool_name* and return its result.

        Returns None when the verifier is disabled or not configured.
        Errors are swallowed and logged — a broken verifier must not block the loop.
        """
        if self._verifier is None:
            return None
        task_id = self._current_context.task_id if self._current_context else None
        try:

            result = await self._verifier.verify(
                tool_name=tool_name,
                args=args,
                reason=reason,
                task_id=task_id,
            )
            return result
        except Exception as exc:
            logger.warning(
                "AgentLoop: pre-action verifier raised unexpectedly (%s: %r) — skipping",
                type(exc).__name__,
                exc,
            )
            return None

    async def _record_verifier_verdict(self, result: "VerifierResult") -> None:
        """Publish the verifier verdict to the event bus and task trajectory.

        The verdict is visible to the human at the approval gate so the operator
        sees "verifier flagged X" before deciding whether to approve.
        """
        task_id = self._current_context.task_id if self._current_context else None
        payload = result.to_dict()
        await _bus_publish_event(
            f"task:{task_id}" if task_id else "global",
            EVT_VERIFIER_VERDICT,
            payload,
            persist=PersistStrategy.MEMORY,
        )
        if self._current_context is not None:
            self._current_context.metadata.setdefault("verifier_verdicts", []).append(payload)
        logger.debug(
            "AgentLoop: verifier verdict recorded tool=%s verdict=%s prob=%.2f",
            result.tool_name,
            result.verdict.value,
            result.refutation_probability,
        )

    async def _request_approval(
        self,
        tool: dict[str, Any],
        approval_id: str,
    ) -> bool:
        """Emit APPROVAL_REQUIRED and wait for APPROVAL_RESPONSE.

        Returns True if the user approved, False if denied or timed out.
        Uses pub/sub subscribe() so the response is received instantly when
        the user approves — no 1-second polling window that could miss fast
        approvals or race against the event store.
        """
        tool_name = tool.get("tool_name", "unknown")
        args = tool.get("args", tool.get("arguments", tool.get("parameters", {})))
        task_id = self._current_context.task_id if self._current_context else None

        event = create_approval_required_event(
            approval_id=approval_id,
            tool_name=tool_name,
            arguments=args if isinstance(args, dict) else {"value": repr(args)},
            reason=f"Tool '{tool_name}' performs a sensitive operation and requires authorization.",
            risk_level="high",
            timeout_seconds=self.config.approval_timeout_seconds,
            task_id=task_id,
        )
        await self.event_stream.publish(event)
        # (#6486) Use unified bus so the single call reaches LiveEventManager
        # (WebSocket fan-out) without a separate explicit bridge.
        await _bus_publish_event(
            "global",
            EVT_APPROVAL_REQUIRED,
            {
                "approval_id": approval_id,
                "tool_name": tool_name,
                "arguments": args if isinstance(args, dict) else {"value": repr(args)},
                "reason": f"Tool '{tool_name}' performs a sensitive operation and requires authorization.",
                "risk_level": "high",
                "timeout_seconds": self.config.approval_timeout_seconds,
                "task_id": task_id,
            },
            persist=PersistStrategy.MEMORY,
        )
        logger.info(
            "AgentLoop: approval required for tool '%s' (approval_id=%s)",
            tool_name,
            approval_id,
        )

        # Issue #4308: mirror approval request to Slack (fire-and-forget)
        slack = get_slack_hook()
        await slack.request_approval(
            approval_id=approval_id,
            title=f"Approval required: {tool_name}",
            description=(
                f"Tool '{tool_name}' is requesting authorization to perform a "
                f"sensitive operation. Reply *approve* or *reject* in this thread."
            ),
            approval_type="tool",
            requested_by="AgentLoop",
        )

        # Use pub/sub subscribe() instead of polling get_latest().
        # subscribe() blocks on pubsub.listen() and yields the event the moment
        # it is published — no 1-second window that could miss the signal.
        async def _await_response() -> bool:
            # Do NOT filter by task_id here: if the frontend omits task_id in
            # the approval request the published event has task_id=None, which
            # the subscriber's task_id filter would skip even when approval_id
            # matches.  approval_id is a UUID — globally unique — so filtering
            # by it is sufficient and safe.
            async for resp_event in self.event_stream.subscribe(
                event_types=[EventType.APPROVAL_RESPONSE],
            ):
                if resp_event.content.get("approval_id") == approval_id:
                    decision: bool = resp_event.content.get("approved", False)
                    logger.info(
                        "AgentLoop: approval_id=%s decision=%s",
                        approval_id,
                        "approved" if decision else "denied",
                    )
                    return decision
            return False  # iterator exhausted without a match

        try:
            return await asyncio.wait_for(
                _await_response(),
                timeout=self.config.approval_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "AgentLoop: approval timed out for tool '%s' (approval_id=%s)",
                tool_name,
                approval_id,
            )
            return False

    def _should_continue(self) -> bool:
        """Check if the loop should continue.

        Issue #3877: Also returns False when a repetition halt has fired so the
        main while-loop exits even if _should_iterate() did not catch the error.
        GH#6626: Also returns False when confidence-based abstention fires.
        GH#6628: Returns False immediately when a fatal error has been recorded.
        """
        if self._halted_on_repetition:
            return False
        if self._fatal_error is not None:
            return False
        if self._halted_on_stagnation:
            return False
        if self._state not in (LoopState.RUNNING, LoopState.PAUSED, LoopState.WAITING_FOR_HUMAN):
            return False
        if self._iteration_count >= self.config.max_iterations:
            return False
        if self._error_budget_exhausted:
            return False
        if self.config.abstain_on_low_confidence and self._current_context is not None:
            window = self.config.confidence_window
            recent = self._current_context.think_history[-window:]
            if len(recent) >= window and all(t.confidence < self.config.min_confidence_floor for t in recent):
                self._abstained = True
                self._abstention_reason = (
                    f"confidence below {self.config.min_confidence_floor} " f"for {window} consecutive iterations"
                )
                logger.warning(
                    "AgentLoop: abstaining — %s",
                    self._abstention_reason,
                )
                return False
        return True

    def _max_retries_for_severity(self, severity: ErrorSeverity) -> int:
        """Return the configured retry budget for the given severity (GH#6628)."""
        mapping = {
            ErrorSeverity.CRITICAL: self.config.max_retries_critical,
            ErrorSeverity.HIGH: self.config.max_retries_high,
            ErrorSeverity.MEDIUM: self.config.max_retries_medium,
            ErrorSeverity.LOW: self.config.max_retries_low,
        }
        return mapping.get(severity, self.config.max_consecutive_errors)

    async def _try_fallback_strategy(self, error: Exception) -> None:
        """Placeholder hook for FALLBACK_ERROR_TYPES (GH#6628).

        Real fallback strategies are separate work; this logs the attempt.
        """
        logger.warning(
            "AgentLoop: Fallback-class error %s — fallback hook not yet implemented",
            type(error).__name__,
        )

    async def _handle_iteration_error(self, error: Exception) -> bool:
        """Handle an error during iteration (GH#6628: severity-aware).

        CRITICAL errors halt immediately without retry.  All other errors
        consume their per-severity retry budget before halting.
        """
        severity = classify_error(error)

        if isinstance(error, CRITICAL_ERROR_TYPES):
            self._fatal_error = error
            self._fatal_reason = f"Critical error {type(error).__name__} — halting without retry"
            logger.error(
                "AgentLoop: FATAL %s (severity=%s) — %s",
                type(error).__name__,
                severity.value,
                self._fatal_reason,
            )
            return False

        # FALLBACK errors intentionally do both: invoke the hook for recovery AND
        # consume the per-severity (MEDIUM) retry budget on the same error.
        if isinstance(error, FALLBACK_ERROR_TYPES):
            await self._try_fallback_strategy(error)

        self._consecutive_errors += 1
        max_for_severity = self._max_retries_for_severity(severity)

        logger.error(
            "AgentLoop: Iteration error (%d/%d, severity=%s): %s",
            self._consecutive_errors,
            max_for_severity,
            severity.value,
            error,
        )

        if self._consecutive_errors >= max_for_severity:
            logger.error(
                "AgentLoop: Retry budget exhausted (severity=%s, %d/%d), stopping",
                severity.value,
                self._consecutive_errors,
                max_for_severity,
            )
            self._error_budget_exhausted = True
            return False

        # Think about error recovery
        if self.config.mandatory_think_enabled:
            result = await self.think_tool.think(
                ThinkCategory.ERROR_RECOVERY,
                f"Error: {error}",
                task_id=(self._current_context.task_id if self._current_context else None),
            )
            if self._current_context:
                self._current_context.add_think(result)

        return True

    async def _plan_steps_to_tools(
        self,
        steps: list,
        events_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Convert plan steps to tool specifications."""
        # This would use LLM to determine actual tools from step descriptions
        # Placeholder implementation
        return []

    async def _dispatch_tool(
        self,
        tool: dict[str, Any],
    ) -> Any:
        """Dispatch a single tool call."""
        # This would integrate with actual tool system
        # Placeholder implementation
        return {"status": "executed"}

    async def _get_plan_progress(self) -> float:
        """Get current plan completion progress."""
        if not self._current_context or not self._current_context.plan_id:
            return 0.0

        if not self.planner:
            return 0.0

        plan = await self.planner.get_plan(self._current_context.plan_id)
        if not plan:
            return 0.0

        return plan.get_progress()

    def _resolve_outcome(self) -> LoopOutcome:
        """Map current loop state + halt flags to a LoopOutcome."""
        if self._abstained:
            return LoopOutcome.ABSTAINED
        if self._halted_on_stagnation:
            return LoopOutcome.STAGNATED
        if self._halted_on_repetition:
            return LoopOutcome.HALTED
        if self._halt_outcome == LoopOutcome.TIMED_OUT_WAITING:
            return LoopOutcome.TIMED_OUT_WAITING
        if self._state == LoopState.CANCELLED:
            return LoopOutcome.CANCELLED
        if self._state == LoopState.FAILED:
            return LoopOutcome.FAILED
        return LoopOutcome.COMPLETED

    def _build_result(
        self,
        iterations: list[IterationResult],
    ) -> dict[str, Any]:
        """Build the final task result."""
        if not self._current_context:
            return {"error": "No context"}

        outcome = self._resolve_outcome()
        result: dict[str, Any] = {
            "task_id": self._current_context.task_id,
            "description": self._current_context.description,
            "state": self._state.name,
            "outcome": outcome.value,
            "iterations": len(iterations),
            "tools_executed": len(self._current_context.tools_executed),
            "errors": self._current_context.errors,
            "duration_ms": self._current_context.get_duration_ms(),
            "plan_id": self._current_context.plan_id,
            "think_count": len(self._current_context.think_history),
        }
        if self._abstained:
            result["abstained"] = True
            result["abstention_reason"] = self._abstention_reason
        if self._fatal_reason:
            result["fatal_reason"] = self._fatal_reason
        # Issue #6627: surface stagnation halt details when set.
        if self._halted_on_stagnation:
            result["halt_outcome"] = outcome.name
            result["halt_reason"] = self._halt_reason
        return result
