# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Distributed Agent Management Module

Issue #381: Extracted from agent_orchestrator.py god class refactoring.
Contains distributed agent registration, health monitoring, and lifecycle management.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from constants.threshold_constants import TimingConstants, WorkStealingConfig

from .types import DistributedAgentInfo

if TYPE_CHECKING:
    from agents.base_agent import AgentHealth, BaseAgent

logger = logging.getLogger(__name__)


class DistributedAgentManager:
    """Manages distributed agent lifecycle and health monitoring."""

    def __init__(
        self,
        builtin_agents: Dict[str, Callable],
        health_check_interval: float = 30.0,
        stale_task_timeout_seconds: int = WorkStealingConfig.STALE_TASK_TIMEOUT_SECONDS,
        grace_period_seconds: int = WorkStealingConfig.GRACE_PERIOD_SECONDS,
        max_reassignments: int = WorkStealingConfig.MAX_REASSIGNMENTS,
        progress_ttl_seconds: int = WorkStealingConfig.PROGRESS_TTL_SECONDS,
    ):
        """
        Initialize the distributed agent manager.

        Args:
            builtin_agents: Dict of agent type to agent class/factory
            health_check_interval: Interval for health checks in seconds
            stale_task_timeout_seconds: Seconds a task may be silent before reassignment
            grace_period_seconds: Minimum task age before it is eligible for stealing
            max_reassignments: Hard cap on how many times one task may be stolen
            progress_ttl_seconds: Recent-progress window that marks a task as alive

        Issue #2109: work-stealing parameters added.
        """
        self.distributed_agents: Dict[str, DistributedAgentInfo] = {}
        self.builtin_distributed_agents = builtin_agents
        self.health_check_interval = health_check_interval
        self.health_monitor_task: Optional[asyncio.Task] = None
        self.is_running = False

        # Work-stealing configuration (Issue #2109)
        self.stale_task_timeout_seconds = stale_task_timeout_seconds
        self.grace_period_seconds = grace_period_seconds
        self.max_reassignments = max_reassignments
        self.progress_ttl_seconds = progress_ttl_seconds

        # task_id -> assigned_at (UTC) — set when add_active_task is called
        self._task_assigned_at: Dict[str, datetime] = {}
        # task_id -> last_progress_at (UTC) — updated via report_task_progress
        self._task_last_progress: Dict[str, datetime] = {}
        # task_id -> reassignment_count
        self._task_reassignment_count: Dict[str, int] = {}

    async def start(self, event_emitter: Optional[Any] = None) -> bool:
        """Start distributed agent management.

        Args:
            event_emitter: Optional async callable(channel, event_type, payload)
                forwarded to the health-monitor loop for work-stealing events.
                Typically ``publish_live_event`` from live_event_manager.

        Issue #2109: event_emitter parameter added for work-stealing events.
        """
        if self.is_running:
            logger.warning("Distributed mode already running")
            return True

        try:
            self.is_running = True

            # Initialize built-in distributed agents
            await self._initialize_distributed_agents()

            # Start health monitoring (includes work-stealing cycle)
            self.health_monitor_task = asyncio.create_task(
                self._health_monitor_loop(event_emitter)
            )

            logger.info("Distributed agent mode started successfully")
            return True

        except Exception as e:
            logger.error("Failed to start distributed mode: %s", e)
            self.is_running = False
            return False

    async def stop(self) -> None:
        """Stop distributed agent management."""
        if not self.is_running:
            return

        self.is_running = False

        # Cancel health monitoring
        if self.health_monitor_task:
            self.health_monitor_task.cancel()

        # Shutdown distributed agents
        for agent_id in list(self.distributed_agents.keys()):
            await self.unregister_agent(agent_id)

        logger.info("Distributed agent mode stopped")

    async def _initialize_distributed_agents(self) -> None:
        """Initialize built-in distributed agents."""
        for agent_type, agent_class in self.builtin_distributed_agents.items():
            try:
                agent = agent_class()
                await self.register_agent(agent)
                logger.info("Initialized distributed agent: %s", agent_type)
            except Exception as e:
                logger.error(
                    f"Failed to initialize distributed agent {agent_type}: {e}"
                )

    async def register_agent(self, agent: "BaseAgent") -> bool:
        """Register a distributed agent."""
        try:
            agent_id = agent.agent_id

            # Initialize agent communication
            if not agent.communication_protocol:
                await agent.initialize_communication(agent.get_capabilities())

            # Perform health check
            health = await agent.health_check()

            # Register agent
            self.distributed_agents[agent_id] = DistributedAgentInfo(
                agent=agent,
                health=health,
                last_health_check=datetime.now(),
                active_tasks=set(),
            )

            logger.info("Registered distributed agent: %s", agent_id)
            return True

        except Exception as e:
            logger.error("Failed to register distributed agent: %s", e)
            return False

    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister a distributed agent."""
        try:
            if agent_id not in self.distributed_agents:
                return False

            agent_info = self.distributed_agents[agent_id]
            await agent_info.agent.shutdown_communication()
            del self.distributed_agents[agent_id]

            logger.info("Unregistered distributed agent: %s", agent_id)
            return True

        except Exception as e:
            logger.error("Failed to unregister distributed agent %s: %s", agent_id, e)
            return False

    async def _check_single_agent_health(
        self, agent_id: str, agent_info: DistributedAgentInfo
    ) -> Tuple[str, Optional["AgentHealth"], Optional[Exception]]:
        """Check health of single agent (Issue #334 - extracted helper)."""
        try:
            health = await agent_info.agent.health_check()
            return (agent_id, health, None)
        except Exception as e:
            return (agent_id, None, e)

    def _process_health_result(
        self,
        agent_id: str,
        health: Optional["AgentHealth"],
        error: Optional[Exception],
    ) -> None:
        """Process a single health check result (Issue #334 - extracted helper)."""
        agent_info = self.distributed_agents.get(agent_id)
        if not agent_info:
            return

        if error:
            logger.error(
                f"Health check failed for distributed agent {agent_id}: {error}"
            )
            return

        if not health:
            return

        agent_info.health = health
        agent_info.last_health_check = datetime.now()

        if health.status.value != "healthy":
            logger.warning(
                f"Distributed agent {agent_id} health issue: {health.status.value}"
            )

    async def _run_health_checks(self, agents_snapshot: list) -> None:
        """Run parallel health checks on agents (Issue #334 - extracted helper)."""
        results = await asyncio.gather(
            *[
                self._check_single_agent_health(aid, ainfo)
                for aid, ainfo in agents_snapshot
            ],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.error("Health check task failed: %s", result)
                continue
            agent_id, health, error = result
            self._process_health_result(agent_id, health, error)

    async def _health_monitor_loop(self, event_emitter: Optional[Any] = None) -> None:
        """Background health monitoring for distributed agents.

        Each cycle:
        1. Run parallel health checks on all registered agents.
        2. Detect and reassign stale tasks (Issue #2109 work-stealing).

        Args:
            event_emitter: Optional async callable(channel, event_type, payload)
                used to broadcast task_reassigned events via LiveEventManager.
        """
        while self.is_running:
            try:
                agents_snapshot = list(self.distributed_agents.items())
                if agents_snapshot:
                    await self._run_health_checks(agents_snapshot)
                await self._detect_and_steal_stale_tasks(event_emitter)
                await asyncio.sleep(self.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in distributed health monitor: %s", e)
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

    def get_healthy_agents(self) -> list:
        """Get list of healthy distributed agents."""
        return [
            info.agent
            for info in self.distributed_agents.values()
            if info.health.status.value == "healthy"
        ]

    def get_agent_info(self, agent_id: str) -> Optional[DistributedAgentInfo]:
        """Get info for a specific agent."""
        return self.distributed_agents.get(agent_id)

    def add_active_task(self, agent_id: str, task_id: str) -> None:
        """Add an active task to an agent and record its assignment timestamp.

        Issue #2109: records assigned_at for stale-detection.
        """
        if agent_id in self.distributed_agents:
            self.distributed_agents[agent_id].active_tasks.add(task_id)
            self._task_assigned_at[task_id] = datetime.now(timezone.utc)

    def remove_active_task(self, agent_id: str, task_id: str) -> None:
        """Remove an active task from an agent and clean up tracking state.

        Issue #2109: clears assigned_at / progress / reassignment metadata.
        """
        if agent_id in self.distributed_agents:
            self.distributed_agents[agent_id].active_tasks.discard(task_id)
        self._task_assigned_at.pop(task_id, None)
        self._task_last_progress.pop(task_id, None)
        self._task_reassignment_count.pop(task_id, None)

    def report_task_progress(self, task_id: str) -> None:
        """Record that a task has made progress, resetting its stale timer.

        Call this from the agent when partial results arrive so the
        work-stealer does not reclaim an actively-running task.

        Issue #2109: progress-protection guard rail.
        """
        self._task_last_progress[task_id] = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Work-stealing helpers (Issue #2109)
    # ------------------------------------------------------------------

    def _is_task_stale(self, task_id: str, now: datetime) -> bool:
        """Return True when a task has exceeded the stale timeout.

        Guards:
        - grace period: task assigned less than grace_period_seconds ago → not stale
        - progress protection: task reported progress within progress_ttl_seconds → not stale
        - max reassignments exceeded → not stale (stop trying)

        Issue #2109.
        """
        assigned_at = self._task_assigned_at.get(task_id)
        if assigned_at is None:
            return False

        age_seconds = (now - assigned_at).total_seconds()
        if age_seconds < self.grace_period_seconds:
            return False

        if self._task_reassignment_count.get(task_id, 0) >= self.max_reassignments:
            return False

        last_progress = self._task_last_progress.get(task_id)
        if last_progress is not None:
            progress_age = (now - last_progress).total_seconds()
            if progress_age < self.progress_ttl_seconds:
                return False

        return age_seconds >= self.stale_task_timeout_seconds

    def _collect_stale_tasks(self, now: datetime) -> List[Tuple[str, str]]:
        """Return list of (agent_id, task_id) pairs where the task is stale.

        Issue #2109: extracted helper keeps _detect_stale_tasks short.
        """
        stale: List[Tuple[str, str]] = []
        for agent_id, agent_info in self.distributed_agents.items():
            for task_id in list(agent_info.active_tasks):
                if self._is_task_stale(task_id, now):
                    stale.append((agent_id, task_id))
        return stale

    async def _reassign_task(
        self,
        source_agent_id: str,
        task_id: str,
        event_emitter: Optional[Any] = None,
    ) -> bool:
        """Remove task from stale agent, mark agent degraded, emit event.

        The task is disassociated from the source agent so that the
        TaskQueue's own retry / scheduling logic can pick it up on the
        next cycle.  We intentionally do not push directly into the queue
        here to avoid a circular dependency — the caller owns the queue.

        Returns True when the reassignment bookkeeping succeeds.

        Issue #2109.
        """
        if source_agent_id not in self.distributed_agents:
            return False

        agent_info = self.distributed_agents[source_agent_id]
        agent_info.active_tasks.discard(task_id)

        # Increment reassignment counter before clearing assigned_at so the
        # counter survives the next add_active_task call.
        count = self._task_reassignment_count.get(task_id, 0) + 1
        self._task_reassignment_count[task_id] = count
        self._task_assigned_at.pop(task_id, None)
        self._task_last_progress.pop(task_id, None)

        # Mark source agent degraded in its health record so the router
        # prefers other agents until the next successful health check.
        if agent_info.health is not None:
            try:
                agent_info.health.status = type(agent_info.health.status)("degraded")
            except Exception:
                pass  # Health status type may not support arbitrary values; best-effort.

        logger.warning(
            "Work-stealing: reassigning task %s from agent %s (attempt %d/%d)",
            task_id,
            source_agent_id,
            count,
            self.max_reassignments,
        )

        if event_emitter is not None:
            try:
                await event_emitter(
                    "global",
                    "task_reassigned",
                    {
                        "task_id": task_id,
                        "source_agent_id": source_agent_id,
                        "reassignment_count": count,
                        "max_reassignments": self.max_reassignments,
                    },
                )
            except Exception as exc:
                logger.debug("Failed to emit task_reassigned event: %s", exc)

        return True

    async def _detect_and_steal_stale_tasks(
        self, event_emitter: Optional[Any] = None
    ) -> int:
        """Scan all active tasks and steal those that are stale.

        Returns the number of tasks reassigned in this cycle.

        Issue #2109: called once per health-monitor cycle.
        """
        now = datetime.now(timezone.utc)
        stale_pairs = self._collect_stale_tasks(now)
        if not stale_pairs:
            return 0

        reassigned = 0
        for agent_id, task_id in stale_pairs:
            success = await self._reassign_task(agent_id, task_id, event_emitter)
            if success:
                reassigned += 1

        if reassigned:
            logger.info(
                "Work-stealing: reassigned %d stale task(s) this cycle", reassigned
            )
        return reassigned

    def get_statistics(self) -> Dict[str, Any]:
        """Get distributed agent statistics, including work-stealing counters.

        Issue #2109: reassignment_counts added to per-agent task entries.
        """
        stats: Dict[str, Any] = {}
        for agent_id, agent_info in self.distributed_agents.items():
            task_list = list(agent_info.active_tasks)
            stats[agent_id] = {
                "agent_type": agent_info.agent.agent_type,
                "health_status": agent_info.health.status.value,
                "last_health_check": agent_info.last_health_check.isoformat(),
                "active_tasks": len(task_list),
                "active_task_list": task_list,
                "task_reassignment_counts": {
                    t: self._task_reassignment_count.get(t, 0) for t in task_list
                },
            }
        stats["_work_stealing"] = {
            "stale_task_timeout_seconds": self.stale_task_timeout_seconds,
            "grace_period_seconds": self.grace_period_seconds,
            "max_reassignments": self.max_reassignments,
            "progress_ttl_seconds": self.progress_ttl_seconds,
            "total_tracked_tasks": len(self._task_assigned_at),
        }
        return stats
