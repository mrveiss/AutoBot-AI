# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Distributed Agent Management Module

Issue #381: Extracted from agent_orchestrator.py god class refactoring.
Contains distributed agent registration, health monitoring, and lifecycle management.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

from constants.threshold_constants import TimingConstants, WorkStealingConfig
from services.task_claim import claim_task, is_claim_alive, release_claim, renew_claim

from .state_persistence import (
    delete_task_state,
    delete_task_timing_state,
    load_task_state,
    persist_task_assigned,
    persist_task_progress,
    persist_task_reassignment,
)
from .types import CircuitState, DistributedAgentInfo

if TYPE_CHECKING:
    from agents.base_agent import AgentHealth, BaseAgent

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)


class DistributedAgentManager:
    """Manages distributed agent lifecycle and health monitoring.

    Scope (#6828): dynamic registration with circuit-breaker health checks and
    work-stealing (#2109, #4694).  This is the **distributed-runtime** registry
    — it handles multi-node agent membership and task reassignment.  It does
    not hold database state or static capability profiles.  See also:
    - orchestration.agent_registry.AgentRegistry — static profile/capability registry
    - agents.agent_client.AgentRegistry — health-tracking runtime registry
    - services.agent_registry_service.AgentRegistryService — DB-backed CRUD
    """

    def __init__(
        self,
        builtin_agents: Dict[str, Callable],
        health_check_interval: float = 30.0,
        stale_task_timeout_seconds: int = WorkStealingConfig.STALE_TASK_TIMEOUT_SECONDS,
        grace_period_seconds: int = WorkStealingConfig.GRACE_PERIOD_SECONDS,
        max_reassignments: int = WorkStealingConfig.MAX_REASSIGNMENTS,
        progress_ttl_seconds: int = WorkStealingConfig.PROGRESS_TTL_SECONDS,
        circuit_failure_threshold: int = 3,
        circuit_recovery_timeout_seconds: int = 300,
        deployment_id: str = "autobot",
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
            circuit_failure_threshold: Consecutive unhealthy results before opening circuit
            circuit_recovery_timeout_seconds: Seconds before a half-open probe is attempted

        Issue #2109: work-stealing parameters added.
        Issue #4694: circuit breaker parameters added.
        """
        self.distributed_agents: Dict[str, DistributedAgentInfo] = {}
        self.builtin_distributed_agents = builtin_agents
        self.health_check_interval = health_check_interval
        self.health_monitor_task: asyncio.Task | None = None
        self.is_running = False

        # Work-stealing configuration (Issue #2109)
        self.stale_task_timeout_seconds = stale_task_timeout_seconds
        self.grace_period_seconds = grace_period_seconds
        self.max_reassignments = max_reassignments
        self.progress_ttl_seconds = progress_ttl_seconds

        # Circuit breaker configuration (Issue #4694)
        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_recovery_timeout_seconds = circuit_recovery_timeout_seconds

        # Redis-scoped deployment identifier (Issue #6479)
        self._deployment_id = deployment_id

        # task_id -> assigned_at (UTC) — write-through cache; persisted in Redis (#6479)
        self._task_assigned_at: Dict[str, datetime] = {}
        # task_id -> last_progress_at (UTC) — write-through cache; persisted in Redis (#6479)
        self._task_last_progress: Dict[str, datetime] = {}
        # task_id -> reassignment_count — write-through cache; persisted in Redis (#6479)
        self._task_reassignment_count: Dict[str, int] = {}

    async def start(self, event_emitter: Any | None = None) -> bool:
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

            # Rehydrate stale-detection state from Redis so grace periods survive restarts.
            await self._rehydrate_from_redis()

            # Initialize built-in distributed agents
            await self._initialize_distributed_agents()

            # Start health monitoring (includes work-stealing cycle)
            self.health_monitor_task = asyncio.create_task(self._health_monitor_loop(event_emitter))

            logger.info("Distributed agent mode started successfully")
            return True

        except Exception as e:
            logger.error("Failed to start distributed mode: %s", e)
            self.is_running = False
            return False

    async def _rehydrate_from_redis(self) -> None:
        """Populate in-memory dicts from Redis on startup (Issue #6479)."""
        assigned, progress, reassign = await load_task_state(self._deployment_id)
        self._task_assigned_at.update(assigned)
        self._task_last_progress.update(progress)
        self._task_reassignment_count.update(reassign)
        total = len(assigned)
        if total:
            logger.info(
                "Distributed manager rehydrated %d task(s) from Redis (deployment=%s)",
                total,
                self._deployment_id,
            )

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
                logger.error(f"Failed to initialize distributed agent {agent_type}: {e}")

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
                last_health_check=datetime.now(tz=timezone.utc),
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
    ) -> Tuple[str, "AgentHealth" | None, Exception | None]:
        """Check health of single agent (Issue #334 - extracted helper)."""
        try:
            health = await agent_info.agent.health_check()
            return (agent_id, health, None)
        except Exception as e:
            return (agent_id, None, e)

    def _process_health_result(
        self,
        agent_id: str,
        health: "AgentHealth" | None,
        error: Exception | None,
    ) -> None:
        """Process a single health check result and update circuit breaker state.

        Issue #334: extracted helper.
        Issue #4694: circuit breaker transitions added.

        State machine:
        - CLOSED  → OPEN      when circuit_failure_count reaches circuit_failure_threshold
        - OPEN    → HALF_OPEN when circuit_recovery_timeout_seconds has elapsed
        - HALF_OPEN → CLOSED  on a healthy result
        - HALF_OPEN → OPEN    on an unhealthy result (reset opened_at for new backoff)
        """
        agent_info = self.distributed_agents.get(agent_id)
        if not agent_info:
            return

        now = datetime.now(tz=timezone.utc)

        if error:
            logger.error("Health check failed for distributed agent %s: %s", agent_id, error)
            self._on_agent_failure(agent_id, agent_info, now)
            return

        if not health:
            return

        agent_info.health = health
        agent_info.last_health_check = now

        is_healthy = health.status.value == "healthy"

        if is_healthy:
            self._on_agent_success(agent_id, agent_info)
        else:
            logger.warning("Distributed agent %s health issue: %s", agent_id, health.status.value)
            self._on_agent_failure(agent_id, agent_info, now)

    def _on_agent_success(self, agent_id: str, agent_info: DistributedAgentInfo) -> None:
        """Handle a successful health check — reset failure counter and close circuit."""
        prev_state = agent_info.circuit_state
        agent_info.circuit_failure_count = 0
        agent_info.circuit_state = CircuitState.CLOSED
        agent_info.circuit_opened_at = None
        agent_info.circuit_probe_dispatched_at = None

        if prev_state != CircuitState.CLOSED:
            logger.info(
                "Circuit breaker CLOSED for agent %s (recovered from %s)",
                agent_id,
                prev_state.value,
            )

    def _on_agent_failure(self, agent_id: str, agent_info: DistributedAgentInfo, now: datetime) -> None:
        """Handle an unhealthy health check — increment failure count; open if threshold met."""
        agent_info.circuit_failure_count += 1

        if agent_info.circuit_state == CircuitState.HALF_OPEN:
            # Probe failed → extend backoff, re-open circuit.
            agent_info.circuit_state = CircuitState.OPEN
            agent_info.circuit_opened_at = now
            agent_info.circuit_probe_dispatched_at = None
            logger.warning(
                "Circuit breaker re-OPENED for agent %s (half-open probe failed, " "failure count=%d)",
                agent_id,
                agent_info.circuit_failure_count,
            )
            return

        if (
            agent_info.circuit_state == CircuitState.CLOSED
            and agent_info.circuit_failure_count >= self.circuit_failure_threshold
        ):
            agent_info.circuit_state = CircuitState.OPEN
            agent_info.circuit_opened_at = now
            logger.warning(
                "Circuit breaker OPENED for agent %s after %d consecutive failures",
                agent_id,
                agent_info.circuit_failure_count,
            )

    async def _run_health_checks(self, agents_snapshot: list) -> None:
        """Run parallel health checks on agents (Issue #334 - extracted helper)."""
        results = await asyncio.gather(
            *[self._check_single_agent_health(aid, ainfo) for aid, ainfo in agents_snapshot],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.error("Health check task failed: %s", result)
                continue
            agent_id, health, error = result
            self._process_health_result(agent_id, health, error)

    async def _health_monitor_loop(self, event_emitter: Any | None = None) -> None:
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
        """Return agents available for task routing, respecting circuit breaker state.

        Issue #4694: circuit breaker — OPEN agents are excluded; HALF_OPEN agents
        are included for a single probe dispatch then re-excluded until the probe
        resolves (tracked via circuit_probe_dispatched_at).
        """
        now = datetime.now(tz=timezone.utc)
        available = []
        for agent_id, info in self.distributed_agents.items():
            if info.circuit_state == CircuitState.OPEN:
                # Promote to HALF_OPEN once the recovery timeout has elapsed.
                if (
                    info.circuit_opened_at is not None
                    and (now - info.circuit_opened_at).total_seconds() >= self.circuit_recovery_timeout_seconds
                ):
                    info.circuit_state = CircuitState.HALF_OPEN
                    info.circuit_probe_dispatched_at = None
                    logger.info(
                        "Circuit breaker HALF_OPEN for agent %s — probe allowed",
                        agent_id,
                    )
                else:
                    # Still in backoff window — skip agent entirely.
                    continue

            if info.circuit_state == CircuitState.HALF_OPEN:
                # Allow only one probe task at a time.
                if info.circuit_probe_dispatched_at is not None:
                    continue
                info.circuit_probe_dispatched_at = now
                logger.info("Circuit breaker half-open probe dispatched for agent %s", agent_id)
                available.append(info.agent)
                continue

            # CLOSED: include only if underlying health status is healthy.
            if info.health.status.value == "healthy":
                available.append(info.agent)

        return available

    def get_agent_info(self, agent_id: str) -> DistributedAgentInfo | None:
        """Get info for a specific agent."""
        return self.distributed_agents.get(agent_id)

    async def add_active_task(self, agent_id: str, task_id: str) -> bool:
        """Add an active task to an agent if the atomic Redis claim is granted.

        Returns True when the claim was granted and the task was added.
        Returns False when another agent already holds the claim — the caller
        must not proceed with the task (double-pickup guard, GH#6468).

        Issue #2109: records assigned_at for stale-detection.
        Issue #6479: persists assigned_at to Redis (write-through cache).
        Issue #6468: atomic claim via Redis SET NX EX.
        """
        claimed = await claim_task(task_id, agent_id)
        if not claimed:
            logger.warning(
                "add_active_task: task %s already claimed by another agent — agent %s skipping",
                task_id,
                agent_id,
            )
            return False

        if agent_id in self.distributed_agents:
            self.distributed_agents[agent_id].active_tasks.add(task_id)
            assigned_at = now_utc()
            self._task_assigned_at[task_id] = assigned_at
            await persist_task_assigned(self._deployment_id, task_id, assigned_at)
        return True

    async def remove_active_task(self, agent_id: str, task_id: str) -> None:
        """Remove an active task from an agent and clean up tracking state.

        Issue #2109: clears assigned_at / progress / reassignment metadata.
        Issue #6479: deletes Redis hash entries for the task.
        Issue #6468: releases the atomic Redis claim.
        """
        if agent_id in self.distributed_agents:
            self.distributed_agents[agent_id].active_tasks.discard(task_id)
        self._task_assigned_at.pop(task_id, None)
        self._task_last_progress.pop(task_id, None)
        self._task_reassignment_count.pop(task_id, None)
        await delete_task_state(self._deployment_id, task_id)
        await release_claim(task_id, agent_id)

    async def report_task_progress(self, task_id: str, agent_id: str = "") -> None:
        """Record that a task has made progress, resetting its stale timer.

        Also renews the Redis claim TTL so the task is not freed while the
        agent is actively working.

        Issue #2109: progress-protection guard rail.
        Issue #6479: persists last_progress to Redis.
        Issue #6468: renews claim TTL on each progress heartbeat.
        """
        progress_at = now_utc()
        self._task_last_progress[task_id] = progress_at
        await persist_task_progress(self._deployment_id, task_id, progress_at)
        if agent_id:
            await renew_claim(task_id, agent_id)

    # ------------------------------------------------------------------
    # Work-stealing helpers (Issue #2109)
    # ------------------------------------------------------------------

    def _is_task_stale(self, task_id: str, now: datetime) -> bool:
        """Return True when a task has exceeded the stale timeout.

        Guards (checked in order):
        - grace period: task assigned less than grace_period_seconds ago → not stale
        - max reassignments exceeded → not stale (stop trying)
        - progress protection: task reported progress within progress_ttl_seconds → not stale
        - falls through to time-based check (age >= stale_task_timeout_seconds)

        Issue #2109.
        Issue #6468: Redis claim TTL expiry is checked asynchronously via
        _collect_stale_tasks to supplement in-memory timestamps.
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

    async def _collect_stale_tasks(self, now: datetime) -> List[Tuple[str, str]]:
        """Return list of (agent_id, task_id) pairs where the task is stale.

        A task is stale when either:
        - its in-memory timestamps breach the timeout thresholds, or
        - its Redis claim key has expired (agent died without releasing).

        Issue #2109: extracted helper keeps _detect_stale_tasks short.
        Issue #6468: Redis claim TTL expiry supplements in-memory timestamps.
        """
        stale: List[Tuple[str, str]] = []
        for agent_id, agent_info in self.distributed_agents.items():
            for task_id in list(agent_info.active_tasks):
                if self._is_task_stale(task_id, now):
                    stale.append((agent_id, task_id))
                    continue
                # Also reclaim tasks whose Redis claim key has expired but
                # whose in-memory timestamp has not yet breached the threshold
                # (e.g. agent crashed mid-grace-period).
                if not await is_claim_alive(task_id):
                    logger.info(
                        "task_claim: Redis claim expired for task=%s agent=%s — marking stale",
                        task_id,
                        agent_id,
                    )
                    stale.append((agent_id, task_id))
        return stale

    async def _reassign_task(
        self,
        source_agent_id: str,
        task_id: str,
        event_emitter: Any | None = None,
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
        # Persist incremented count; clear only timing entries so count survives
        # the next add_active_task call (Issue #6479).
        await persist_task_reassignment(self._deployment_id, task_id, count)
        await delete_task_timing_state(self._deployment_id, task_id)

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

    async def _detect_and_steal_stale_tasks(self, event_emitter: Any | None = None) -> int:
        """Scan all active tasks and steal those that are stale.

        Returns the number of tasks reassigned in this cycle.

        Issue #2109: called once per health-monitor cycle.
        """
        now = now_utc()
        stale_pairs = await self._collect_stale_tasks(now)
        if not stale_pairs:
            return 0

        reassigned = 0
        for agent_id, task_id in stale_pairs:
            success = await self._reassign_task(agent_id, task_id, event_emitter)
            if success:
                reassigned += 1

        if reassigned:
            logger.info("Work-stealing: reassigned %d stale task(s) this cycle", reassigned)
        return reassigned

    def get_statistics(self) -> Dict[str, Any]:
        """Get distributed agent statistics, including work-stealing and circuit breaker state.

        Issue #2109: reassignment_counts added to per-agent task entries.
        Issue #4694: circuit breaker fields added per agent.
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
                "task_reassignment_counts": {t: self._task_reassignment_count.get(t, 0) for t in task_list},
                # Circuit breaker state (Issue #4694)
                "circuit_state": agent_info.circuit_state.value,
                "circuit_failure_count": agent_info.circuit_failure_count,
                "circuit_opened_at": (
                    agent_info.circuit_opened_at.isoformat() if agent_info.circuit_opened_at else None
                ),
            }
        stats["_work_stealing"] = {
            "stale_task_timeout_seconds": self.stale_task_timeout_seconds,
            "grace_period_seconds": self.grace_period_seconds,
            "max_reassignments": self.max_reassignments,
            "progress_ttl_seconds": self.progress_ttl_seconds,
            "total_tracked_tasks": len(self._task_assigned_at),
        }
        stats["_circuit_breaker"] = {
            "failure_threshold": self.circuit_failure_threshold,
            "recovery_timeout_seconds": self.circuit_recovery_timeout_seconds,
        }
        return stats
