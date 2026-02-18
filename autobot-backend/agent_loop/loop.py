# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
import time
import uuid
from typing import Any, Optional

from agent_loop.think_tool import ThinkTool
from agent_loop.types import (
    AgentLoopConfig,
    AgentMessage,
    IterationResult,
    LoopPhase,
    LoopState,
    MessageType,
    TaskContext,
    ThinkCategory,
)
from backend.events.types import create_message_event
from backend.tools.parallel import ParallelToolExecutor
from events import EventStreamManager, EventType
from planner import PlannerModule

logger = logging.getLogger(__name__)


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
        planner: Optional[PlannerModule] = None,
        tool_executor: Optional[ParallelToolExecutor] = None,
        think_tool: Optional[ThinkTool] = None,
        config: Optional[AgentLoopConfig] = None,
    ):
        """
        Initialize the agent loop.

        Args:
            event_stream: Event stream manager for publishing/subscribing
            planner: Optional planner module for task decomposition
            tool_executor: Optional parallel tool executor
            think_tool: Optional think tool for reasoning
            config: Loop configuration
        """
        self.event_stream = event_stream
        self.planner = planner
        self.tool_executor = tool_executor
        self.think_tool = think_tool or ThinkTool()
        self.config = config or AgentLoopConfig()

        # State
        self._state = LoopState.IDLE
        self._current_phase = LoopPhase.STANDBY
        self._current_context: Optional[TaskContext] = None
        self._iteration_count = 0
        self._consecutive_errors = 0

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
    def context(self) -> Optional[TaskContext]:
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
        initial_context: Optional[dict],
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

    async def _create_task_plan(
        self, task_description: str, initial_context: Optional[dict]
    ) -> None:
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

        Args:
            results: List of iteration results

        Returns:
            Dict with task results
        """
        self._state = LoopState.COMPLETING
        if self.config.think_on_completion:
            await self._think_before_completion()

        self._state = LoopState.COMPLETED
        return self._build_result(results)

    async def run_task(
        self,
        task_description: str,
        task_id: Optional[str] = None,
        initial_context: Optional[dict] = None,
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

        try:
            # Issue #620: Use helper for plan creation
            await self._create_task_plan(task_description, initial_context)

            results = await self._execute_main_loop()

            # Issue #620: Use helper for task finalization
            return await self._finalize_task(results)

        except asyncio.CancelledError:
            self._state = LoopState.CANCELLED
            logger.warning("AgentLoop: Task %s cancelled", task_id)
            raise

        except Exception as e:
            self._state = LoopState.FAILED
            logger.error("AgentLoop: Task %s failed: %s", task_id, e)
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

    # =========================================================================
    # Iteration Logic
    # =========================================================================

    async def _execute_iteration_phases(
        self, result: IterationResult
    ) -> IterationResult:
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

        # Phase 2: Select Tools
        self._current_phase = LoopPhase.SELECT_TOOLS
        tools_to_execute = await self._select_tools(events_context)

        if not tools_to_execute:
            result.phase_completed = LoopPhase.SELECT_TOOLS
            result.should_continue = False
            return result

        # Phase 3: Execute Tools
        self._current_phase = LoopPhase.WAIT_FOR_EXECUTION
        tool_results = await self._execute_tools(tools_to_execute)
        result.tools_executed = [
            t.get("tool_name", "unknown") for t in tools_to_execute
        ]
        result.tool_results = tool_results

        for tool_name in result.tools_executed:
            self._current_context.add_tool(tool_name)

        # Phase 4: Iterate
        self._current_phase = LoopPhase.ITERATE
        result.should_continue = await self._should_iterate(tool_results)

        if self._current_context.plan_id and self.planner:
            result.plan_progress = await self._get_plan_progress()

        result.phase_completed = LoopPhase.ITERATE
        self._consecutive_errors = 0
        return result

    def _log_iteration_completion(
        self, start_time: float, result: IterationResult
    ) -> None:
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

    async def _analyze_events(self) -> dict[str, Any]:
        """
        Phase 1: Analyze recent events from the event stream.

        Returns context for tool selection.
        """
        events = await self.event_stream.get_latest(
            count=self.config.events_to_analyze,
            task_id=self._current_context.task_id if self._current_context else None,
        )

        # Filter out system events if configured
        if not self.config.include_system_events:
            events = [e for e in events if e.event_type != EventType.SYSTEM]

        # Build context from events
        context = {
            "events": [e.to_dict() for e in events],
            "event_count": len(events),
            "event_types": list(set(e.event_type.name for e in events)),
            "recent_actions": [
                e.content for e in events if e.event_type == EventType.ACTION
            ][-5:],
            "recent_observations": [
                e.content for e in events if e.event_type == EventType.OBSERVATION
            ][-5:],
        }

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

        # Check if we need to think before certain tools
        await self._think_before_tools(tools)

        if self.tool_executor and self.config.enable_parallel_tools:
            # Use parallel executor
            from tools.parallel import create_tool_calls

            tool_calls = create_tool_calls(tools)
            return await self.tool_executor.execute_batch(
                tool_calls,
                task_id=self._current_context.task_id
                if self._current_context
                else None,
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
                results[tool_name] = {"error": str(e)}

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
        all_succeeded = all(
            "error" not in result
            for result in tool_results.values()
            if isinstance(result, dict)
        )

        return all_succeeded

    # =========================================================================
    # Message Handling (Manus Pattern)
    # =========================================================================

    async def notify(self, content: str, metadata: Optional[dict] = None) -> None:
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
        options: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
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
            tool.get("tool_name", "").lower() in git_tools
            or "git" in tool.get("tool_name", "").lower()
            for tool in tools
        )

        if has_git_tool and self.config.think_on_git:
            context = (
                f"About to execute git tools: {[t.get('tool_name') for t in tools]}"
            )
            result = await self.think_tool.think(
                ThinkCategory.GIT_DECISION,
                context,
                task_id=self._current_context.task_id
                if self._current_context
                else None,
            )
            if self._current_context:
                self._current_context.add_think(result)

    async def _think_before_completion(self) -> None:
        """Think before reporting task completion."""
        if not self._current_context:
            return

        context = f"""
Task: {self._current_context.description}
Iterations: {self._iteration_count}
Tools executed: {len(self._current_context.tools_executed)}
Errors: {len(self._current_context.errors)}
Duration: {self._current_context.get_duration_ms():.0f}ms
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

    def _should_continue(self) -> bool:
        """Check if the loop should continue."""
        if self._state not in (LoopState.RUNNING, LoopState.PAUSED):
            return False
        if self._iteration_count >= self.config.max_iterations:
            return False
        if self._consecutive_errors >= self.config.max_consecutive_errors:
            return False
        return True

    async def _handle_iteration_error(self, error: Exception) -> bool:
        """Handle an error during iteration."""
        self._consecutive_errors += 1

        logger.error(
            "AgentLoop: Iteration error (%d consecutive): %s",
            self._consecutive_errors,
            error,
        )

        if self._consecutive_errors >= self.config.max_consecutive_errors:
            logger.error("AgentLoop: Max consecutive errors reached, stopping")
            return False

        # Think about error recovery
        if self.config.mandatory_think_enabled:
            result = await self.think_tool.think(
                ThinkCategory.ERROR_RECOVERY,
                f"Error: {error}",
                task_id=self._current_context.task_id
                if self._current_context
                else None,
            )
            if self._current_context:
                self._current_context.add_think(result)

        return True  # Continue after error

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

    def _build_result(
        self,
        iterations: list[IterationResult],
    ) -> dict[str, Any]:
        """Build the final task result."""
        if not self._current_context:
            return {"error": "No context"}

        return {
            "task_id": self._current_context.task_id,
            "description": self._current_context.description,
            "state": self._state.name,
            "iterations": len(iterations),
            "tools_executed": len(self._current_context.tools_executed),
            "errors": self._current_context.errors,
            "duration_ms": self._current_context.get_duration_ms(),
            "plan_id": self._current_context.plan_id,
            "think_count": len(self._current_context.think_history),
        }
