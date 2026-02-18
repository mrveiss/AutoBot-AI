# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hierarchical Agent for subordinate task delegation.

Issue #657: Implements Agent Zero's subordinate agent pattern where complex
tasks can be delegated to child agents for better task decomposition.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from backend.chat_workflow.models import AgentContext
from backend.utils.errors import RepairableException

logger = logging.getLogger(__name__)


@dataclass
class DelegationResult:
    """Result from a subordinate agent's task execution."""

    agent_id: str
    task: str
    result: str
    success: bool
    execution_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class HierarchicalAgent:
    """
    Agent capable of delegating tasks to subordinate agents.

    Issue #657: Implements Agent Zero's pattern for task decomposition:
    - Root agent (level 0) can delegate to subordinates
    - Subordinates can further delegate up to max_depth
    - Results flow back to parent agents

    Attributes:
        context: Agent hierarchy context (level, parent, etc.)
        subordinates: Map of subordinate agent IDs to agents
        task_callback: Callback for executing tasks (injected by manager)
        history: Execution history for this agent

    Usage:
        # Create root agent
        root = HierarchicalAgent(
            context=AgentContext(agent_id="root", level=0),
            task_callback=execute_task_fn
        )

        # Delegate subtask
        result = await root.delegate(
            task="Install npm packages",
            reason="Independent setup step"
        )
    """

    def __init__(
        self,
        context: AgentContext,
        task_callback: Optional[Callable] = None,
    ):
        """
        Initialize hierarchical agent.

        Args:
            context: Agent hierarchy context
            task_callback: Async callback for task execution
        """
        self.context = context
        self.subordinates: Dict[str, "HierarchicalAgent"] = {}
        self.task_callback = task_callback
        self.history: List[Dict[str, Any]] = []

        logger.info(
            "[Issue #657] HierarchicalAgent created: id=%s, level=%d, parent=%s",
            context.agent_id[:8] if len(context.agent_id) > 8 else context.agent_id,
            context.level,
            context.parent_id[:8]
            if context.parent_id and len(context.parent_id) > 8
            else context.parent_id,
        )

    def _validate_delegation_depth(self) -> None:
        """
        Validate that delegation depth allows further delegation.

        Issue #665: Extracted from delegate() for single responsibility.

        Raises:
            RepairableException: If max delegation depth exceeded
        """
        if not self.context.can_delegate():
            raise RepairableException(
                message=f"Maximum delegation depth ({self.context.max_depth}) reached",
                suggestion="Complete this task directly instead of delegating further",
            )

    def _create_subordinate(
        self, subordinate_id: str, task: str, reason: str
    ) -> tuple["HierarchicalAgent", "AgentContext"]:
        """
        Create a subordinate agent with its context.

        Issue #665: Extracted from delegate() for single responsibility.

        Args:
            subordinate_id: UUID for the new subordinate
            task: Task description (for logging)
            reason: Delegation reason (for logging)

        Returns:
            Tuple of (subordinate agent, subordinate context)

        Raises:
            RepairableException: If subordinate context creation fails
        """
        try:
            sub_context = self.context.create_subordinate_context(subordinate_id)
        except ValueError as e:
            raise RepairableException(
                message=str(e),
                suggestion="Complete this task directly instead of delegating further",
            )

        subordinate = HierarchicalAgent(
            context=sub_context,
            task_callback=self.task_callback,
        )
        self.subordinates[subordinate_id] = subordinate

        logger.info(
            "[Issue #657] Agent %s delegating to %s: %s (reason: %s)",
            self.context.agent_id[:8],
            subordinate_id[:8],
            task[:100],
            reason,
        )

        return subordinate, sub_context

    async def _execute_sync_delegation(
        self,
        subordinate: "HierarchicalAgent",
        subordinate_id: str,
        task: str,
        sub_context: "AgentContext",
        start_time: float,
    ) -> DelegationResult:
        """
        Execute delegation synchronously and wait for result.

        Issue #665: Extracted from delegate() for single responsibility.
        """
        import time

        result = await subordinate.execute(task)
        execution_time = time.time() - start_time

        logger.info(
            "[Issue #657] Subordinate %s completed in %.2fs",
            subordinate_id[:8],
            execution_time,
        )

        return DelegationResult(
            agent_id=subordinate_id,
            task=task,
            result=result,
            success=True,
            execution_time=execution_time,
            metadata={"level": sub_context.level},
        )

    def _execute_async_delegation(
        self,
        subordinate: "HierarchicalAgent",
        subordinate_id: str,
        task: str,
        sub_context: "AgentContext",
    ) -> DelegationResult:
        """
        Start delegation in background (fire and forget).

        Issue #665: Extracted from delegate() for single responsibility.
        """
        asyncio.create_task(subordinate.execute(task))

        return DelegationResult(
            agent_id=subordinate_id,
            task=task,
            result="Task started in background",
            success=True,
            metadata={
                "level": sub_context.level,
                "async": True,
            },
        )

    def _record_delegation_history(
        self, subordinate_id: str, task: str, reason: str
    ) -> None:
        """
        Record delegation action in agent history.

        Issue #620.
        """
        import time

        self.history.append(
            {
                "action": "delegate",
                "subordinate_id": subordinate_id,
                "task": task,
                "reason": reason,
                "timestamp": time.time(),
            }
        )

    def _create_failed_delegation_result(
        self,
        subordinate_id: str,
        task: str,
        start_time: float,
        error: Exception,
    ) -> DelegationResult:
        """
        Create a DelegationResult for a failed delegation.

        Issue #620.
        """
        import time

        execution_time = time.time() - start_time
        logger.error(
            "[Issue #657] Subordinate %s failed: %s",
            subordinate_id[:8],
            str(error),
        )

        return DelegationResult(
            agent_id=subordinate_id,
            task=task,
            result="",
            success=False,
            execution_time=execution_time,
            error=str(error),
        )

    async def delegate(
        self,
        task: str,
        reason: str,
        wait_for_result: bool = True,
    ) -> DelegationResult:
        """
        Delegate a task to a subordinate agent.

        Creates a new subordinate agent to handle the specified task.
        The subordinate operates with its own context and can further
        delegate if needed (up to max_depth).

        Issue #665: Refactored to extract helper methods.
        Issue #620: Further refactored to reduce function length.

        Args:
            task: Task description for the subordinate
            reason: Reason for delegation (for logging/debugging)
            wait_for_result: Whether to wait for subordinate to complete

        Returns:
            DelegationResult with subordinate's execution result

        Raises:
            RepairableException: If max delegation depth exceeded
        """
        import time

        start_time = time.time()
        self._validate_delegation_depth()

        subordinate_id = str(uuid.uuid4())
        subordinate, sub_context = self._create_subordinate(
            subordinate_id, task, reason
        )
        self._record_delegation_history(subordinate_id, task, reason)

        try:
            if wait_for_result:
                return await self._execute_sync_delegation(
                    subordinate, subordinate_id, task, sub_context, start_time
                )
            return self._execute_async_delegation(
                subordinate, subordinate_id, task, sub_context
            )
        except Exception as e:
            return self._create_failed_delegation_result(
                subordinate_id, task, start_time, e
            )

    async def execute(self, task: str) -> str:
        """
        Execute a task, potentially delegating subtasks.

        Args:
            task: Task to execute

        Returns:
            Result string from task execution
        """
        import time

        start_time = time.time()

        logger.info(
            "[Issue #657] Agent %s (level %d) executing: %s",
            self.context.agent_id[:8],
            self.context.level,
            task[:100],
        )

        try:
            if self.task_callback:
                result = await self.task_callback(task, self)
            else:
                # Default: just return task acknowledgment
                result = f"Task received at level {self.context.level}: {task}"

            execution_time = time.time() - start_time

            # Record execution in history
            self.history.append(
                {
                    "action": "execute",
                    "task": task,
                    "result_length": len(str(result)),
                    "execution_time": execution_time,
                    "timestamp": time.time(),
                }
            )

            return result

        except Exception as e:
            logger.error(
                "[Issue #657] Agent %s execution failed: %s",
                self.context.agent_id[:8],
                str(e),
            )
            raise

    async def delegate_parallel(
        self,
        tasks: List[Dict[str, str]],
    ) -> List[DelegationResult]:
        """
        Delegate multiple tasks in parallel.

        Args:
            tasks: List of dicts with 'task' and 'reason' keys

        Returns:
            List of DelegationResults in same order as input
        """
        if not tasks:
            return []

        # Check if we can delegate all tasks
        remaining_depth = self.context.max_depth - self.context.level
        if remaining_depth <= 0:
            raise RepairableException(
                message="Cannot delegate: at maximum depth",
                suggestion="Execute tasks directly instead of delegating",
            )

        logger.info(
            "[Issue #657] Agent %s delegating %d tasks in parallel",
            self.context.agent_id[:8],
            len(tasks),
        )

        # Create delegation coroutines
        coros = [
            self.delegate(
                task=t.get("task", ""),
                reason=t.get("reason", "Parallel execution"),
                wait_for_result=True,
            )
            for t in tasks
        ]

        # Execute in parallel
        results = await asyncio.gather(*coros, return_exceptions=True)

        return self._process_parallel_results(results, tasks)

    def _process_parallel_results(
        self,
        results: List[Any],
        tasks: List[Dict[str, str]],
    ) -> List[DelegationResult]:
        """
        Convert parallel execution results, handling exceptions. Issue #620.

        Args:
            results: Raw results from asyncio.gather (may include exceptions)
            tasks: Original task list for error context

        Returns:
            List of DelegationResults with exceptions converted to failed results
        """
        processed = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                processed.append(
                    DelegationResult(
                        agent_id="error",
                        task=tasks[i].get("task", ""),
                        result="",
                        success=False,
                        error=str(r),
                    )
                )
            else:
                processed.append(r)
        return processed

    def get_subordinate(self, agent_id: str) -> Optional["HierarchicalAgent"]:
        """Get a subordinate agent by ID."""
        return self.subordinates.get(agent_id)

    def get_all_subordinates(self) -> List["HierarchicalAgent"]:
        """Get all subordinate agents."""
        return list(self.subordinates.values())

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about this agent's delegations."""
        delegation_count = sum(1 for h in self.history if h.get("action") == "delegate")
        execution_count = sum(1 for h in self.history if h.get("action") == "execute")

        return {
            "agent_id": self.context.agent_id,
            "level": self.context.level,
            "subordinate_count": len(self.subordinates),
            "delegation_count": delegation_count,
            "execution_count": execution_count,
            "can_delegate": self.context.can_delegate(),
            "history_length": len(self.history),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert agent state to dictionary."""
        return {
            "context": self.context.to_dict(),
            "subordinate_ids": list(self.subordinates.keys()),
            "history": self.history,
            "statistics": self.get_statistics(),
        }
